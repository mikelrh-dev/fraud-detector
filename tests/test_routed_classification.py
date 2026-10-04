"""Routed classification in `ScoringService` — the layer scores route the verdict.

WHAT THIS FILE IS FOR
--------------------
The decision used to be `EnsembleScorer.classify(ensemble_score, threshold)`:
one number, one line, one threshold. That let either layer veto the other
through the ensemble. A 400,000 USD transfer whose rules scored 100 and whose
model scored 18 still had to clear 40 *after* the 0.60/0.25 weighting had
diluted both, and an ML-only signal could never win: the model holds 0.25 of
the weight, so ml_score 85 against a quiet rule layer produced an ensemble of
21.25 and classified `legitimate` (measured — see
`TestMlStrongRuleQuietIsNotVetoed`).

`compute_scores` now routes on the layers themselves:

    fraud      : ml > threshold, OR (rule > threshold AND amount >= AMOUNT_FLOOR
                                                AND ml_score >= ML_FLOOR)
    review     : not fraud, and (rule > threshold OR ml > threshold * 0.75)
    legitimate : otherwise

`AMOUNT_FLOOR` is the `min_amount` of the last (critical) tier in
`settings.threshold_tiers`, read from settings rather than repeated here: the
floor IS that tier boundary, so a tier edit moves both together or the
"critical" and the floor disagree by construction. Note it is **50000.01**,
not 50000 - the tiers are half-open `[min, max)` and the high tier reaches
50000.01 inclusive.

`ML_FLOOR` (5.0, `settings.ml_floor`) is the second brake on that same branch,
and it guards the rule branch ONLY - `ml > threshold` alone still blocks. The
argument is the same one the amount floor makes, applied to the model instead of
the amount: the amount floor says a pattern firing on a small purchase is not
evidence for a block, and the ML floor says neither is a block that overrides
the model calling the transaction ordinary. It is a "has the model spoken" bar
rather than a confidence bar - 5 out of 100 is a weak signal and counts as an
opinion. Measured: `acme`/`retail` at 50,001 EUR is rule 48.59 / ml 0.13, and
before this gate the rules alone blocked it.

Two routed cases changed verdict when the floor landed, both because their model
score is under it, and both re-expressed in place with the old expectation and
the reason recorded:

- `test_case_b_the_same_wire_in_daylight` (ml 0.19): `fraud` -> `review`.
- `test_the_floor_boundary_at_49999_and_50001` (ml 0.13): the 50,001 parameter
  can no longer use the deployed model, because the ML gate would close before
  the amount boundary was reached and the pair would stop testing a boundary. It
  now stubs the model above the floor so the amount stays the only variable.

THAT POLICY ONLY APPLIES WHEN THE MODEL IS UP. With `ml_score is None` there
is no ML layer to route against, so `_classify_routed` returns the shipped
ensemble's verdict instead - `combine` over the layers that produced a value
(A15), then `EnsembleScorer.classify` against the same threshold. Degraded
behaviour is therefore bit-for-bit what it was before the routing existed. The
alternative - running the routed policy with the ML layer treated as silence -
would be a second scoring policy that only executes when the system is already
broken, and `TestAnAbsentModelLayerKeepsTheShippedEnsemble` pins two cases where
the two policies disagree so that second policy cannot creep back in.

WHAT THIS FILE IS NOT
---------------------
It does not touch `ensemble_score`. That number is still computed with
`EnsembleScorer.combine` and still persisted; it just no longer decides the
verdict. Anything downstream that reads `classification` — friction, alerts,
the graph mutation, SHAP staging, the API — is untouched and still sees the
same three strings.

The H-type case is asserted as `review` because the policy says so: a
rule-strong transaction BELOW the critical floor is downgraded rather than
blocked. That is the intended trade — the rules cannot buy a `fraud` on a
900 EUR purchase. Measured against the shipped ensemble, that particular case
was already `review`, so this file does not turn a block into a challenge;
what it pins is that the policy routes it to review regardless of what the
ensemble arithmetic happened to produce.
"""

from __future__ import annotations

import asyncio
import math
import os
from pathlib import Path

import pytest

from src.core.config import settings
from src.services.ensemble import EnsembleScorer
from src.services.ml_model import MLModelService
from src.services.scoring_service import ScoringService

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The deployed artifact, same override convention as
#: ``tests/test_fusion_constraints.py``. These are classification assertions
#: about real layer scores, so they need the real model or they are measuring
#: a different ensemble than the one in production.
MODEL_PATH = Path(
    os.environ.get("FRAUD_MODEL_PATH", REPO_ROOT / "models" / "xgboost_paysim_v1.joblib")
)

#: 03:00 UTC fires `unusual_hours` and, for an adversarial merchant,
#: `off_hours_crypto`. Fixed because both move the rule score.
NIGHT_0300 = "2026-10-03T03:00:00+00:00"
#: 14:00 UTC is deliberately dull, so a case can isolate one signal.
DAY_1400 = "2026-10-03T14:00:00+00:00"

#: No spend history: the deviation features read these, so a case that does not
#: care about them says so once here instead of at every call site.
_NO_HISTORY: dict[str, float] = {"avg_amount": 0.0, "std_amount": 0.0}


def _context(recent_transactions: int = 0) -> dict:
    return {
        "recent_transactions": recent_transactions,
        "merchant_blacklist": [],
        "known_cards": [],
        "home_country": "ES",
        "graph_features": None,
    }


def critical_floor() -> float:
    """The amount at or above which a rule-strong transaction is fraud.

    Read from the last tier rather than written down, so the floor and the
    threshold it guards are the same boundary by construction.
    """
    return float(settings.threshold_tiers[-1]["min_amount"])


def ml_floor() -> float:
    """The ml_score at or above which the model is allowed to agree with rules.

    Read at call time, like ``critical_floor`` above, so an env override of
    ``ML_FLOOR`` takes effect instead of being frozen at import.
    """
    return float(settings.ml_floor)


@pytest.fixture(scope="module")
def scoring() -> ScoringService:
    """A service with the deployed model, or skip.

    Built once: the model is a several-hundred-MB artifact and these cases all
    read the same layer scores.
    """
    if not MODEL_PATH.exists():
        pytest.skip(f"model artifact absent at {MODEL_PATH}")
    ml = MLModelService(model_path=str(MODEL_PATH))
    if not ml.load_model():
        pytest.skip(f"model artifact at {MODEL_PATH} failed to load")
    return ScoringService(ml_service=ml)


def _score(
    service: ScoringService,
    tx: dict,
    context: dict | None = None,
    history: dict | None = None,
):
    """One scoring pass through the real pipeline."""
    return asyncio.run(
        service.compute_scores(
            tx,
            context if context is not None else _context(),
            history if history is not None else _NO_HISTORY,
        )
    )


class TestTheFloorComesFromTheTiers:
    """The floor is configuration, so it cannot silently disagree with it."""

    def test_it_is_the_last_tiers_min_amount(self) -> None:
        assert critical_floor() == pytest.approx(
            float(settings.threshold_tiers[-1]["min_amount"])
        )

    def test_the_last_tier_is_the_unbounded_one(self) -> None:
        """Which tier is "last" is a claim about the table's shape, not its values.

        `get_threshold` picks a tier by scanning for `min <= amount < max`, so
        an amount above every `max_amount` would match nothing and fall through
        to the low tier. The floor is only meaningful if the last tier is the
        one with no upper bound.
        """
        assert math.isinf(float(settings.threshold_tiers[-1]["max_amount"])), (
            "the last tier is not unbounded, so `critical_floor()` is not the "
            "critical tier's boundary"
        )

    def test_the_floor_is_the_tier_boundary_not_a_rounded_amount(self) -> None:
        """Pinned because the half-open intervals make it 50000.01, not 50000.

        The high tier is `[10000.01, 50000.01)`, so 50000.00 is a high-tier
        amount and 50000.01 is the first critical one. A floor written as
        50000 would promote exactly one amount into fraud that the tier table
        does not consider critical.
        """
        assert critical_floor() == pytest.approx(50000.01)


class TestRuleStrongIsFraudOnlyAboveTheFloor:
    """The 400k cases: rule evidence plus a critical amount is a block."""

    def test_case_a_quarter_bitcoin_at_three_in_the_morning(
        self, scoring: ScoringService
    ) -> None:
        """400,000 USD to `binance` at 03:00 with no velocity.

        rule 100, ml 17.96, threshold 40. The model alone would never carry this
        — 17.96 is nowhere near 40 — so under the routed policy it is the rule
        layer plus the critical amount that blocks it. That is the whole point:
        the decision is no longer at the mercy of a weighted average that
        diluted 100 down to 64.49.
        """
        result = _score(
            scoring,
            {
                "amount": 400_000.0,
                "merchant_name": "binance",
                "merchant_category": "retail",
                "timestamp": NIGHT_0300,
            },
            history={"avg_amount": 200.0, "std_amount": 150.0,
                     "tx_count_last_5min": 0, "tx_count_last_1h": 0},
        )
        assert result.classification == "fraud", (
            f"rule {result.rule_score:.2f} against threshold "
            f"{result.threshold:.2f} on a critical-tier amount produced "
            f"{result.classification!r} (ensemble {result.ensemble_score:.2f})"
        )
        assert result.rule_score > result.threshold
        assert result.threshold == 40.0

    def test_case_b_the_same_wire_in_daylight(self, scoring: ScoringService) -> None:
        """The reported transaction: rule 75.82, no night-hour bonus.

        RE-EXPRESSED: was `fraud`, now `review`.

        Old expectation: `fraud`. The rule layer cleared the critical threshold of
        40 on a 400,000 USD amount, and the amount was critical, so the rule
        branch blocked on rules alone.

        New expectation: `review`. The rule evidence is unchanged — 75.82, and it
        still clears the threshold — but the model reads 0.19, below the
        `ML_FLOOR` of 5.0. So the model is reporting the transaction as ordinary
        and the rule branch is no longer allowed to overrule it.

        This downgrade is the ACCEPTED cost of the floor, and it is why the
        expectation moved rather than the policy being weakened. `review` is not
        a soft no: the transaction still reaches a human through the analyst
        queue, which is what a 400,000 USD wire to a crypto exchange deserves
        even when the model is uninformative about it. The full rationale lives
        in `TestTheRuleBranchNeedsTheModelToAgree.test_case_b_is_reviewed_because_the_model_did_not_agree`;
        this entry keeps the historical pin that the case was once a block.
        """
        result = _score(
            scoring,
            {
                "amount": 400_000.0,
                "merchant_name": "binance",
                "merchant_category": "retail",
                "timestamp": DAY_1400,
            },
        )
        assert result.rule_score == pytest.approx(75.82, abs=0.05), (
            f"rule score moved to {result.rule_score:.2f}; this case was chosen "
            f"because 75.82 clears the critical threshold of 40"
        )
        assert result.ml_score < ml_floor(), (
            f"ml is {result.ml_score:.2f}, at or above the floor of "
            f"{ml_floor():.2f}; the rule branch would block again and this "
            f"expectation would need re-examining for a real reason"
        )
        assert result.classification == "review", (
            f"rule {result.rule_score:.2f} / ml {result.ml_score:.2f} on a "
            f"critical-tier amount came out {result.classification!r}. A model "
            f"scoring under the floor must downgrade the rule branch to `review`, "
            f"not let it block."
        )


class TestRuleStrongBelowTheFloorIsReview:
    """The H-type downgrade, and the boundary it is defined against."""

    def test_a_night_casino_purchase_is_reviewed_not_blocked(
        self, scoring: ScoringService
    ) -> None:
        """900 EUR, gambling, 03:00, two recent transactions.

        rule 85: `velocity_burst` 30 + `unusual_merchant` 20 +
        `unusual_hours` 10 + `off_hours_crypto` 25. Threshold at 900 EUR is 70,
        so the rules beat the threshold — and because 900 is below the critical
        floor that is a REVIEW, not a fraud. This is the intended downgrade: a
        rule-strong small purchase gets an analyst, not a block.

        The counterfactual is the reason the floor exists at all. Without it,
        `rule > threshold` alone would block a 900 EUR purchase on rule evidence
        the model scored at 0.18.
        """
        result = _score(
            scoring,
            {
                "amount": 900.0,
                "merchant_name": "Grand Casino",
                "merchant_category": "gambling",
                "timestamp": NIGHT_0300,
            },
            _context(recent_transactions=2),
            {"avg_amount": 200.0, "std_amount": 100.0},
        )
        assert result.rule_score == pytest.approx(85.0, abs=0.05), (
            f"rule score is {result.rule_score:.2f}, not the 85 this case was "
            f"built from; one of the four rules stopped firing"
        )
        assert result.rule_score > result.threshold, (
            "the case is only meaningful if the rules actually beat the threshold"
        )
        assert result.classification == "review", (
            f"rule {result.rule_score:.2f} > threshold {result.threshold:.2f} but "
            f"amount 900 is below the floor {critical_floor():,.2f}, so this must "
            f"be `review`; got {result.classification!r}"
        )

    @pytest.mark.parametrize(
        ("amount", "expected"),
        [
            (49_999.0, "review"),
            (50_001.0, "fraud"),
        ],
    )
    def test_the_floor_boundary_at_49999_and_50001(
        self, amount: float, expected: str
    ) -> None:
        """One rule score, two amounts, two different verdicts.

        RE-EXPRESSED: the 50,001 case no longer runs against the deployed model.

        Old expectation: 49,999 -> `review`, 50,001 -> `fraud`, both measured
        through the real model.

        New expectation: the same pair, but with a STUBBED model scoring 10.0 —
        above the `ML_FLOOR` of 5.0 — instead of the deployed artifact.

        Why the model had to change. This pair exists to prove one thing: that
        the AMOUNT floor is what separates the two verdicts. With the deployed
        model the case cannot demonstrate that any more. The real ml score for
        `acme`/`retail` is 0.13, which is below the ML floor, so the ML gate now
        closes BEFORE the amount is ever consulted and both amounts come out
        `review`. That would have satisfied a lazy re-expression — change the
        expectation to `review`, stay green — while deleting the guard entirely:
        a boundary that pins `review` on both sides is not pinning a boundary.

        Stubbing the model restores exactly the property the test was built on.
        The model now has an opinion, so it stops being the variable, and the
        amount becomes the only thing left that can differ. Everything else is
        still production: the rule engine, the feature engine, the tier lookup
        and the routing are all the real ones, so 48.59 is still measured rather
        than asserted. `_StubML` is used for the same reason in
        `TestMlStrongRuleQuietIsNotVetoed` — no corpus row produces the layer
        combination a boundary test needs, and inventing a transaction to get
        there would test the corpus instead of the routing.

        The 10.0 is not arbitrary: it is low enough to be a weak opinion (so the
        test cannot accidentally pass because the model turned out loud) and
        high enough to clear the floor. If `ML_FLOOR` ever moves above it, both
        parameters fail as `review` and the pair stops being a boundary test —
        which is the correct outcome, because the guard really would be gone.
        """
        result = _score(
            ScoringService(ml_service=_StubML(10.0)),
            {
                "amount": amount,
                "merchant_name": "acme",
                "merchant_category": "retail",
                "timestamp": DAY_1400,
            },
            history={"avg_amount": 100.0, "std_amount": 10.0},
        )
        assert result.rule_score == pytest.approx(48.59, abs=0.05)
        assert result.ml_score >= ml_floor(), (
            f"the stubbed model reads {result.ml_score:.2f}, below the floor of "
            f"{ml_floor():.2f}, so the ML gate closes first and this pair stops "
            f"testing the AMOUNT boundary at all"
        )
        assert result.ml_score < result.threshold * 0.75, (
            "the case isolates the rule layer; a loud model would confound it"
        )
        assert result.classification == expected, (
            f"{amount:,.2f} scored rule {result.rule_score:.2f} / ml "
            f"{result.ml_score:.2f} against threshold {result.threshold:.2f} with "
            f"floor {critical_floor():,.2f} and came out "
            f"{result.classification!r}, not {expected!r}"
        )


class TestTheRuleBranchNeedsTheModelToAgree:
    """Rules plus a critical amount block only if the model said something too.

    THE ML FLOOR. Before this, the rule branch was `rule > threshold AND amount
    >= FLOOR`, and the model had no say in it at all. That made the floor the
    only thing standing between the rules and a block — so a transaction the
    model scored at 0.13 out of 100, on no evidence it could find, was blocked on
    the rules' word alone. Measured: `acme`/`retail` at 50,001 EUR scores rule
    48.59 and ml 0.13.

    That is the shape of a disagreement, and the policy has to be able to see it.
    The model is not required to *confirm* — 5.0 out of 100 is a very weak signal
    and it is enough. It is required to have *spoken*: below the floor the model
    is asserting the transaction is ordinary, and a block that overrides a flat
    "ordinary" is a block on the rules' authority alone, which is the situation
    the whole routed policy was built to end.

    The floor is a floor and NOT a second threshold. It does not scale with the
    amount tier, it does not change the review band, and it does not touch the
    ML branch: `ml > threshold` alone still blocks, because that IS the model
    speaking loudly and the floor exists precisely to ignore a model that has
    nothing to say.

    It is also a property of the ROUTED policy only. A degraded pass
    (`ml_score is None`) has no model to agree or disagree, so it keeps the
    shipped ensemble verdict — pinned by `TestTheFloorDoesNotLeakIntoDegraded`.
    """

    #: rule 100 against a critical threshold of 40 on a critical-tier amount:
    #: the rule gate is open and the amount gate is open, which leaves
    #: `ml_score` as the ONLY remaining condition on the fraud branch. That makes
    #: these the cleanest available probes of the floor — nothing else can
    #: produce a `fraud` here, so a `fraud` means the floor let it through and a
    #: `review` means the floor stopped it.
    _AMOUNT_GATE_OPEN = {
        "rule_score": 100.0,
        "context_score": 0.0,
        "threshold": 40.0,
        "amount": 400_000.0,
    }

    @pytest.mark.parametrize(
        ("offset", "expected"),
        [(-0.01, "review"), (0.0, "fraud")],
        ids=["just-below-the-floor", "exactly-at-the-floor"],
    )
    def test_the_floor_boundary_is_inclusive(self, offset: float, expected: str) -> None:
        """Both sides of the line, one hundredth apart.

        `>=` and `>` differ on exactly one value, `ML_FLOOR` itself, so a suite
        that only tests 4.99 and 6.0 cannot tell which one the policy uses. A
        `>` where `>=` was meant would quietly reclassify every transaction whose
        model score lands exactly on the floor, which is the one row a boundary
        test exists to protect.

        The upper case is also the control for the whole class: if the floor were
        implemented as a hard block on the rule branch, `exactly-at-the-floor`
        would come out `review` too, and the two would be indistinguishable from
        a floor that is simply stuck shut.
        """
        ml_score = ml_floor() + offset
        verdict = ScoringService()._classify_routed(
            ml_score=ml_score, **self._AMOUNT_GATE_OPEN
        )
        assert verdict == expected, (
            f"ml {ml_score:.2f} against a floor of {ml_floor():.2f} (rule 100, "
            f"threshold 40, 400,000 EUR) produced {verdict!r}, not {expected!r}. "
            f"The floor is inclusive: a model scoring exactly the floor has "
            f"spoken, and one point below it has not."
        )

    def test_a_floor_that_blocked_everything_would_not_be_caught_above(
        self,
    ) -> None:
        """The floor gates the rule branch and only the rule branch.

        ml 85 against a threshold of 70 with a completely silent rule layer is
        the model speaking loudly on its own, and the amount here is 500 EUR —
        nowhere near the critical floor. Neither gate is open, so a floor
        applied to the ML branch instead of the rule branch would turn this into
        `review`, and the class above would still be green.
        """
        verdict = ScoringService()._classify_routed(
            rule_score=0.0,
            ml_score=85.0,
            context_score=0.0,
            threshold=70.0,
            amount=500.0,
        )
        assert verdict == "fraud", (
            f"ml 85 against a threshold of 70 produced {verdict!r}. The ML "
            f"branch is the model overruling the rules, and the floor is a "
            f"condition on the RULES agreeing with the model, not the reverse."
        )

    def test_case_a_clears_the_floor_with_margin(self, scoring: ScoringService) -> None:
        """The quarter-bitcoin case must not come within 13 points of the line.

        CASE_A: rule 100, ml 17.96, threshold 40. This is the transaction the
        whole routed policy exists to protect, and it is also the case most
        exposed to a floor — it is rule-driven, so the floor is aimed straight at
        it. It clears by 12.96.

        Asserted as a margin rather than as a verdict, because a verdict is a
        knife edge: any retrain that moved this model score from 17.96 to 4.99
        would leave the assertion above still passing for every other case while
        quietly downgrading the flagship fraud to a review. A margin fails loudly
        and early, and it fails on the retrain rather than on the transaction.
        """
        result = _score(
            scoring,
            {
                "amount": 400_000.0,
                "merchant_name": "binance",
                "merchant_category": "retail",
                "timestamp": NIGHT_0300,
            },
            history={"avg_amount": 200.0, "std_amount": 150.0,
                     "tx_count_last_5min": 0, "tx_count_last_1h": 0},
        )
        margin = result.ml_score - ml_floor()
        assert result.classification == "fraud", (
            f"rule {result.rule_score:.2f} / ml {result.ml_score:.2f} on a "
            f"critical-tier amount came out {result.classification!r} against a "
            f"floor of {ml_floor():.2f}"
        )
        assert margin >= 10.0, (
            f"CASE_A clears the ML floor by only {margin:.2f} points "
            f"(ml {result.ml_score:.2f} vs floor {ml_floor():.2f}). Under 10 the "
            f"flagship rule-driven fraud is one retrain away from being "
            f"downgraded to a review, and nothing else in the suite would say so."
        )

    def test_case_b_is_reviewed_because_the_model_did_not_agree(
        self, scoring: ScoringService
    ) -> None:
        """The reported transaction, and the cost this policy knowingly pays.

        CASE_B: the same 400,000 USD wire to `binance`, in daylight. The rules
        read 75.82 — they still clear the critical threshold of 40 — but the
        model reads 0.19 out of 100 and the amount is critical. Before the floor
        this was `fraud`; now it is `review`.

        That downgrade is ACCEPTED and is the point of the change, so the test
        asserts it rather than defending against it. It is worth being explicit
        about what is being traded: this is a 400,000 USD transfer to a crypto
        exchange, and `review` means an analyst sees it instead of the pipeline
        blocking it automatically. The floor buys precision at the price of
        recall, and this case is what that costs.

        What makes it acceptable is that the case stays VISIBLE and stays
        CHALLENGED. It does not become `legitimate`, so it still reaches a human
        through the same channel `review` reaches a human through, and the alert
        row it creates is the analyst-visible one. A transaction that is merely
        downgraded to review has lost a block, not lost a review.
        """
        result = _score(
            scoring,
            {
                "amount": 400_000.0,
                "merchant_name": "binance",
                "merchant_category": "retail",
                "timestamp": DAY_1400,
            },
        )
        assert result.rule_score > result.threshold, (
            f"rule score is {result.rule_score:.2f} against threshold "
            f"{result.threshold:.2f}; the case only means anything while the "
            f"rules still clear the threshold on their own"
        )
        assert result.ml_score < ml_floor(), (
            f"ml is {result.ml_score:.2f}, which clears the floor of "
            f"{ml_floor():.2f}; this case no longer exercises the floor"
        )
        assert result.classification == "review", (
            f"rule {result.rule_score:.2f} on a critical-tier amount with the "
            f"model at {result.ml_score:.2f} came out "
            f"{result.classification!r}, not 'review'. A rule-driven block on a "
            f"model that scored the transaction near zero is exactly what the "
            f"floor exists to stop, and it must downgrade to `review` — never to "
            f"`legitimate`, which would drop the transaction from the queue."
        )

    def test_a_quiet_model_does_not_promote_a_below_floor_purchase_to_fraud(
        self, scoring: ScoringService
    ) -> None:
        """The control on the H-type case: two gates, and the new one is the second.

        900 EUR of gambling at 03:00: rule 85 against a threshold of 70, model
        0.18. It was already `review` before the floor, for the amount reason —
        900 is nowhere near 50,000.01 — so this is not a test of the floor. It is
        here to pin that the floor did not become the ONLY thing holding this back
        and that the amount gate still works, since the two gates now sit side by
        side and a future edit could easily disturb one while fixing the other.
        """
        result = _score(
            scoring,
            {
                "amount": 900.0,
                "merchant_name": "Grand Casino",
                "merchant_category": "gambling",
                "timestamp": NIGHT_0300,
            },
            _context(recent_transactions=2),
            {"avg_amount": 200.0, "std_amount": 100.0},
        )
        assert result.classification == "review"


class TestTheFloorDoesNotLeakIntoDegraded:
    """The floor belongs to the routed policy, not to the fallback.

    When the artifact fails to load there is no model, so there is nothing to
    agree or disagree with anything. Applying the floor then would be a second
    scoring policy that only ever executes while the system is broken — and it
    would be a *silent* one, because the degraded path is precisely the path
    nobody is watching.

    The dangerous direction is the one that loses fraud. CASE_B degraded is the
    exact transaction the floor downgrades in the healthy path, and with no model
    to consult the shipped ensemble still calls it `fraud` at 60.66 against a
    threshold of 40. If the floor leaked in, that would become `review` and a
    400,000 USD crypto transfer would stop blocking on precisely the night the
    model artifact is missing.
    """

    def test_a_degraded_case_b_is_still_fraud(self) -> None:
        """The same transaction, the model absent: the ensemble verdict stands."""
        result = _score(
            ScoringService(ml_service=_UnavailableML()),
            {
                "amount": 400_000.0,
                "merchant_name": "binance",
                "merchant_category": "retail",
                "timestamp": DAY_1400,
            },
        )
        assert "ml" not in result.layers_used
        assert result.classification == "fraud", (
            f"degraded CASE_B came out {result.classification!r} (ensemble "
            f"{result.ensemble_score:.2f} against threshold "
            f"{result.threshold:.2f}). The shipped ensemble calls this fraud; "
            f"the ML floor is a condition of the ROUTED policy and there is no "
            f"model score for it to judge when the layer is absent."
        )

    def test_the_floor_never_touches_a_degraded_pass(self) -> None:
        """Structural: no `ml_score`, no floor. Stated over the whole fallback.

        The equivalence test in
        `TestAnAbsentModelLayerKeepsTheShippedEnsemble` already pins the fallback
        against the ensemble over a spread of inputs; this re-states it at the
        seam, so that an edit which moved the floor check ABOVE the `None` guard
        would fail here with a clear message instead of only failing as a changed
        verdict somewhere further down.
        """
        service = ScoringService()
        scorer = EnsembleScorer()
        for rule_score, context_score, threshold, amount in (
            (100.0, 0.0, 40.0, 400_000.0),
            (75.82, 0.0, 40.0, 400_000.0),
            (48.59, 0.0, 40.0, 50_001.0),
            (85.0, 20.0, 70.0, 900.0),
        ):
            expected = scorer.classify(
                scorer.combine(
                    rule_score=rule_score,
                    ml_score=None,
                    context_score=context_score,
                ),
                threshold,
            )
            routed = service._classify_routed(
                rule_score=rule_score,
                ml_score=None,
                context_score=context_score,
                threshold=threshold,
                amount=amount,
            )
            assert routed == expected, (
                f"degraded rule={rule_score} threshold={threshold} routed to "
                f"{routed!r} but the shipped ensemble says {expected!r}. The "
                f"floor guard must stay behind the `ml_score is None` early "
                f"return."
            )


class TestMlStrongRuleQuietIsNotVetoed:
    """The other direction: the model alone can now block."""

    def test_ml_85_with_a_silent_rule_layer_is_fraud(self) -> None:
        """The case the old arithmetic could not express.

        A 500 EUR cafe purchase at 14:00 with no velocity fires no rule at all,
        so `rule_score` is a true 0.0 rather than a stub — the only thing mocked
        here is the model, because no corpus row produces ml 85 with a silent
        rule layer and inventing a transaction to get there would test the
        corpus instead of the routing.

        Measured under the shipped logic this came out `legitimate`: the
        ensemble is 0.25 * 85 = 21.25 against a threshold of 70, so the model's
        veto was multiplied down by the weight it holds and then compared
        against a threshold calibrated for a single number. The routed policy
        compares the layer to the threshold directly.
        """
        result = _score(
            ScoringService(ml_service=_StubML(85.0)),
            {
                "amount": 500.0,
                "merchant_name": "Cafe Central",
                "merchant_category": "grocery",
                "timestamp": DAY_1400,
            },
        )
        assert result.rule_score == 0.0, (
            "the rule layer must be genuinely silent, or this is not the case"
        )
        assert result.threshold == 70.0
        assert result.classification == "fraud", (
            f"ml 85 against a threshold of 70 produced "
            f"{result.classification!r} (ensemble {result.ensemble_score:.2f}); "
            f"the model's veto is being multiplied by its ensemble weight "
            f"instead of compared to the threshold"
        )

    def test_a_quiet_model_still_cannot_manufacture_fraud(
        self, scoring: ScoringService
    ) -> None:
        """The veto is not a blanket win for the model layer.

        The 1,100 EUR grocery scores 35.33 on the rules and 0.12 on the model
        against a threshold of 50. Neither route reaches fraud and neither
        reaches review, so the routine purchase has to stay `legitimate`. If the
        ML branch ever went permissive this is the transaction that catches it.
        """
        result = _score(
            scoring,
            {
                "amount": 1_100.0,
                "merchant_name": "Supermercado del Barrio",
                "merchant_category": "grocery",
                "timestamp": DAY_1400,
            },
        )
        assert result.threshold == 50.0
        assert result.classification == "legitimate", (
            f"a routine 1,100 EUR grocery came out {result.classification!r} "
            f"(rule {result.rule_score:.2f}, ml {result.ml_score:.2f})"
        )


class TestTheSmallOrdinaryCasesStayLegitimate:
    """The routes must not be a blunt instrument."""

    def test_a_night_pharmacy_purchase_is_legitimate(
        self, scoring: ScoringService
    ) -> None:
        """45 EUR, pharmacy, 03:00.

        rule 30 — `unusual_hours` 10 plus `unusual_merchant` 20 as a regulated
        merchant with a night hour as corroboration. The night hour buys 10,
        not the 35 a pharmacy used to score, because `unusual_hours` and
        `off_hours_crypto` were double-charging it. At a threshold of 70 this is
        far from either boundary and must be left alone: a rule firing is not
        the same as a transaction being risky.
        """
        result = _score(
            scoring,
            {
                "amount": 45.0,
                "merchant_name": "Farmacia Central",
                "merchant_category": "pharmacy",
                "timestamp": NIGHT_0300,
            },
            history={"avg_amount": 50.0, "std_amount": 10.0},
        )
        assert result.rule_score < result.threshold
        assert result.classification == "legitimate"


class TestAnAbsentModelLayerKeepsTheShippedEnsemble:
    """A degraded pass must return the verdict the ensemble shipped, not a new one.

    When the model is down there is no ML layer to route on, so there is nothing
    for the routed policy to route *between*. Inventing a verdict for that case
    would mean the fallback is a second, untested scoring policy that only ever
    runs when the system is already broken - the worst place to put logic that
    nothing else exercises. So an absent layer falls back to exactly the shipped
    path: the A15 ensemble (`combine` over the layers that produced a value,
    then `classify` against the same threshold).

    That is a claim about behaviour, not about code shape, so it is pinned two
    ways: by equivalence against the ensemble itself, and by two cases where the
    fallback and the routed policy disagree. The second matters more than the
    first - a fallback that merely agreed with the routed policy everywhere would
    pass an equivalence test on the cases anyone thought to try, while quietly
    changing verdicts in the direction nobody sampled.
    """

    def test_it_is_the_ensemble_verdict_for_any_degraded_inputs(self) -> None:
        """Equivalence, stated once, over a spread of degraded layer scores.

        The claim "degraded behaviour is unchanged" is only worth anything if it
        holds for the arithmetic and not just for a hand-picked example, so this
        compares the routing decision to the shipped decision directly.
        """
        service = ScoringService()
        scorer = EnsembleScorer()
        degraded_cases = (
            # (rule_score, context_score, threshold, amount)
            (0.0, 0.0, 70.0, 500.0),
            (35.33, 0.0, 50.0, 1_100.0),
            (45.0, 20.0, 50.0, 5_000.0),
            (65.59, 50.0, 50.0, 5_000.0),
            (49.23, 0.0, 40.0, 60_000.0),
            (100.0, 0.0, 40.0, 400_000.0),
            (0.0, 100.0, 70.0, 900.0),
            (85.0, 20.0, 70.0, 900.0),
        )
        for rule_score, context_score, threshold, amount in degraded_cases:
            shipped = scorer.classify(
                scorer.combine(
                    rule_score=rule_score,
                    ml_score=None,
                    context_score=context_score,
                ),
                threshold,
            )
            routed = service._classify_routed(
                rule_score=rule_score,
                ml_score=None,
                context_score=context_score,
                threshold=threshold,
                amount=amount,
            )
            assert routed == shipped, (
                f"degraded rule={rule_score} context={context_score} "
                f"threshold={threshold} amount={amount:,.2f} routed to "
                f"{routed!r} but the shipped ensemble says {shipped!r}. With no "
                f"ML layer there is nothing to route between, so this case has "
                f"to return the verdict the ensemble already produced."
            )

    def test_a_degraded_velocity_burst_is_not_downgraded_to_review(self) -> None:
        """The direction that would LOSE fraud.

        5,000 EUR with five transactions in the last five minutes: the rules
        score 65.59 and the context layer 50, so the shipped ensemble reads 62.47
        against a threshold of 50 - `fraud`. The routed policy would call this
        `review`: the rules DO clear the threshold, but 5,000 is nowhere near the
        50,000.01 floor, so the rule branch cannot reach `fraud` and the review
        branch takes it. The two policies disagree, and the fallback has to be
        the one that was in production.
        """
        result = _score(
            ScoringService(ml_service=_UnavailableML()),
            {
                "amount": 5_000.0,
                "merchant_name": "acme",
                "merchant_category": "retail",
                "timestamp": DAY_1400,
            },
            _context(recent_transactions=5),
            {"avg_amount": 100.0, "std_amount": 10.0},
        )
        assert "ml" not in result.layers_used
        assert result.classification == "fraud", (
            f"degraded rule {result.rule_score:.2f} against threshold "
            f"{result.threshold:.2f} (ensemble {result.ensemble_score:.2f}) came "
            f"out {result.classification!r}. The shipped ensemble calls this "
            f"fraud; a degraded pass that downgraded it would be silently "
            f"dropping fraud precisely when the model is unavailable."
        )

    def test_a_degraded_critical_amount_is_not_promoted_to_fraud(self) -> None:
        """The direction that would GAIN fraud.

        60,000 EUR with a quiet context layer: the rules score 49.23 against a
        critical threshold of 40, so the routed policy alone would block on rule
        evidence. The shipped ensemble reads 39.38 - just under the threshold,
        and inside the review band - and calls it `review`. The fallback has to
        be that one, so a degraded pass cannot start blocking on rule evidence
        the production path was reviewing.
        """
        result = _score(
            ScoringService(ml_service=_UnavailableML()),
            {
                "amount": 60_000.0,
                "merchant_name": "acme",
                "merchant_category": "retail",
                "timestamp": DAY_1400,
            },
            history={"avg_amount": 100.0, "std_amount": 10.0},
        )
        assert "ml" not in result.layers_used
        assert result.classification == "review", (
            f"degraded rule {result.rule_score:.2f} against threshold "
            f"{result.threshold:.2f} (ensemble {result.ensemble_score:.2f}) came "
            f"out {result.classification!r}. The shipped ensemble calls this "
            f"review; the amount floor is part of the ROUTED policy and must "
            f"not be applied to a degraded pass."
        )

    def test_a_missing_model_cannot_raise_or_block(self) -> None:
        """With the model down, `ml_score` is None and must be treated as silent.

        `None` is not a number. `None > threshold` raises `TypeError` in Python
        3, so the comparison has to be guarded — and the guard has to mean "this
        layer has nothing to say", not "this layer is maximally confident". An
        absent layer asserting `fraud` would block every transaction the moment
        the artifact failed to load, which is the worst possible moment to
        change behaviour.
        """
        result = _score(
            ScoringService(ml_service=_UnavailableML()),
            {
                "amount": 1_100.0,
                "merchant_name": "Supermercado del Barrio",
                "merchant_category": "grocery",
                "timestamp": DAY_1400,
            },
        )
        assert "ml" not in result.layers_used
        assert result.ml_score == 0.0, (
            "the persisted value stays a float; the absence is recorded in "
            "layers_used, not by nulling a non-nullable column"
        )
        assert result.classification == "legitimate", (
            f"a silent model layer produced {result.classification!r} for a "
            f"routine purchase"
        )

    def test_a_rule_strong_transaction_still_blocks_without_the_model(self) -> None:
        """A strong rule layer still blocks when the model is absent.

        400,000 USD to `binance` with the model down: the rules read 75.82, which
        at the rule weight is 60.66 ensemble points against a critical threshold
        of 40, so the shipped ensemble calls it `fraud` and the degraded fallback
        returns that. The verdict does not depend on which layers happened to
        come up.
        """
        result = _score(
            ScoringService(ml_service=_UnavailableML()),
            {
                "amount": 400_000.0,
                "merchant_name": "binance",
                "merchant_category": "retail",
                "timestamp": DAY_1400,
            },
        )
        assert result.classification == "fraud", (
            f"rule {result.rule_score:.2f} on a critical-tier amount with no "
            f"model produced {result.classification!r}"
        )


class TestAnUnusableAmountCannotTakeThePolicyBranch:
    """A broken amount must not be able to open the `fraud` branch.

    The amount comparison is the one place the routing reads a value the schema
    does not fully own: `amount >= FLOOR` raises `TypeError` on a string and
    evaluates meaninglessly on NaN. The HTTP schema is the real gate, but the
    rule engine reads the same field and fires `high_amount` on an amount it
    cannot parse — so the service cannot assume "an amount that got this far is
    a float" just because a Pydantic model sat upstream of one of its callers.

    An amount that cannot be compared must therefore make the gate evaluate
    False, which means the rule branch cannot reach `fraud`. The route that
    remains is `review` via `rule > threshold` alone: the rules fired on the
    transaction, so it gets an analyst. That is the same fail-closed stance
    `EnsembleScorer.get_threshold` already takes for a non-finite amount, and it
    is deliberately *not* "the gate passes": an unusable amount is missing
    evidence for blocking, and treating it as a critical-tier amount would block
    a transaction on a value nobody could read.
    """

    # rule 100 against threshold 40 with a warm-but-quiet model: the ONLY thing
    # that can turn this into `fraud` is the amount gate. If the guard works,
    # every one of these lands on `review`.
    _RULE_STRONG = {"rule_score": 100.0, "ml_score": 5.0, "context_score": 0.0,
                    "threshold": 40.0}

    @pytest.mark.parametrize(
        "amount",
        [
            pytest.param(float("nan"), id="nan"),
            pytest.param(float("inf"), id="posinf"),
            pytest.param(float("-inf"), id="neginf"),
            pytest.param("not-a-number", id="str"),
            pytest.param(None, id="none"),
        ],
    )
    def test_it_routes_to_review_without_raising(self, amount: object) -> None:
        verdict = ScoringService()._classify_routed(amount=amount, **self._RULE_STRONG)
        assert verdict == "review", (
            f"amount={amount!r} with rule 100 against threshold 40 produced "
            f"{verdict!r}. An amount that cannot be compared must leave the "
            f"policy branch closed; the rules fired, so the transaction is a "
            f"review and not a block."
        )

    def test_a_healthy_amount_still_takes_the_policy_branch(self) -> None:
        """The control: the guard rejects broken amounts, not large ones.

        Without this the class above would also pass if the gate were simply
        stuck shut, which is the opposite failure and just as silent.
        """
        verdict = ScoringService()._classify_routed(
            amount=400_000.0, **self._RULE_STRONG
        )
        assert verdict == "fraud", (
            f"a real 400,000 EUR amount with rule 100 against threshold 40 came "
            f"out {verdict!r}; the amount guard has swallowed a genuine policy "
            f"block"
        )

    def test_a_broken_amount_does_not_invent_a_verdict_on_its_own(self) -> None:
        """A quiet, rule-free transaction stays `legitimate`.

        The guard must not become a third route. With no rule evidence and a
        quiet model there is nothing to review, whatever the amount says.
        """
        verdict = ScoringService()._classify_routed(
            rule_score=0.0,
            ml_score=0.0,
            context_score=0.0,
            threshold=70.0,
            amount=float("nan"),
        )
        assert verdict == "legitimate", (
            f"a silent transaction with an unreadable amount came out {verdict!r}; "
            f"the guard is routing on the amount instead of only gating the "
            f"policy branch"
        )


class _StubML:
    """An ML layer with a fixed score.

    Only `predict` is stubbed. The rule engine, the feature engine, the tier
    lookup and the routing are all the production ones, so what is under test
    is the decision and not a fixture's opinion of it.
    """

    is_available = True
    n_features = 10
    model_path = "stub"

    def __init__(self, score: float) -> None:
        self._score = score

    def predict(self, features) -> float:
        return self._score


class _UnavailableML:
    """A model layer that produced no signal, which is not the same as 0.0."""

    is_available = False
    n_features = 10
    model_path = "absent"

    def predict(self, features) -> float:
        return 0.0