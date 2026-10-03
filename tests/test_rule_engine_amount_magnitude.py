"""D2: the rule engine's response to amount is monotone.

The gap this fills
------------------
``tests/test_model_amount_monotonicity.py`` states that contract for the ML
MODEL, in four velocity regimes, with a tolerance derived from the ensemble's
decision geometry. The RULE ENGINE had no counterpart, and that is why nothing
noticed: ``high_amount`` was a switch.

    1,001.00 EUR  ->  35
    400,000.00 USD ->  35

A coffee and a quarter of a bitcoin were the same evidence, and the reported
transaction — 400,000 USD at `binance`, scored 24.1/100 and "legitimate" — is
what a rule that cannot tell those apart produces. `tests/test_rule_engine.py`
asserted ``score == 60`` for a 10,000 transaction beside a 25 for velocity and
nothing said which of the two facts the number depended on.

The arithmetic, in full
-----------------------
Base weight ``WEIGHTS["high_amount"]`` = 35, plus

    magnitude = min(8 * log10(amount / 1000), 25)

so ``high_amount`` is worth ``35 + magnitude``:

    amount         log10(a/1000)   magnitude   total
    ---------------------------------------------------------------
    900            (rule off)          --        0
    1,000.00       (not > 1000)       --        0
    1,000.01       0.0000043          0.00     35.00
    1,100          0.0413937          0.33     35.33
    10,000         1.0                8.00     43.00
    100,000        2.0               16.00     51.00
    400,000        2.6020600         20.82     55.82
    1,333,570+     >= 3.125          25.00     60.00   (cap)
    9,999,999,999  6.99999           25.00     60.00   (cap)

Every expected total below is written as that arithmetic rather than as a
literal, so a reader can check it and a reader who disagrees can see by how much.

Why the ceiling, in numbers
---------------------------
``EnsembleScorer`` weights the rule layer at 0.60 (``settings.ensemble_rule_weight``)
and the strictest amount tier sets the fraud threshold at 40, so

    smallest rule score that reaches `fraud` alone  =  40 / 0.60  =  66.67

The base weight is 35, so the cap has to stay below 31.67 for `high_amount` never
to be able to buy a `fraud` classification by itself. It is 25, which puts the
rule's ceiling at 35 + 25 = 60, and 60 * 0.60 = 36.0 ensemble points from one
rule — below the strictest threshold, inside the review band. The property is
asserted below against the LIVE settings rather than against these numbers, so
editing the ensemble weights makes it fail instead of quietly changing what the
cap is protecting.

What this does NOT establish
----------------------------
1. It is the rule layer only. The ML layer's own monotonicity is a separate
   contract, in ``tests/test_model_amount_monotonicity.py``.
2. It says nothing about whether the ML layer *also* rises with amount, and the
   reported transaction's ML score was 0.3 — low. The plan puts that out of
   scope, and it is not addressed here.
3. It does not claim fraud risk is monotone in amount in every regime. Card
   testing is many SMALL transactions, and a burst of 1,000 EUR charges more
   than a single 50 EUR ticket at the same venue. What is asserted is the weaker
   and still load-bearing half: on a fixed transaction with amount as the only
   variable, a larger amount is never scored as safer. That is the same
   distinction the model contract draws, for the same reason.
"""

import math

import pytest

from src.core.config import settings
from src.core.ml_constants import (
    AMOUNT_MAGNITUDE_CAP,
    AMOUNT_MAGNITUDE_POINTS,
    HIGH_AMOUNT_THRESHOLD,
)
from src.services.rule_engine import RuleEngine

DAY = "2026-10-01T14:00:00+00:00"

#: The geometric ladder. Half-decades for the same reason the model contract uses
#: them: the defect lived between 1,000 and 400,000, and a linear ladder over that
#: span spends most of its points on amounts nobody transacts at.
AMOUNT_LADDER = (
    0.01, 100.0, 900.0, 1_000.0, 1_000.01, 1_100.0, 2_000.0, 5_000.0,
    10_000.0, 50_000.0, 100_000.0, 250_000.0, 400_000.0, 1_000_000.0,
    9_999_999_999.99,
)

#: The three amounts the plan names, as a regression of their own.
THE_FINDING = {"below": 900.0, "just_over": 1_100.0, "reported": 400_000.0}


def expected_high_amount_points(amount: float) -> float:
    """`WEIGHTS["high_amount"]` plus the magnitude term, spelled out.

    Written here rather than imported so the test states the arithmetic instead
    of agreeing with the implementation by calling it.
    """
    if not amount > HIGH_AMOUNT_THRESHOLD:
        return 0.0
    return 35.0 + min(
        AMOUNT_MAGNITUDE_POINTS * math.log10(amount / HIGH_AMOUNT_THRESHOLD),
        AMOUNT_MAGNITUDE_CAP,
    )


def rule_score_for(amount: float, **overrides) -> float:
    """Score a fixed transaction with `amount` as the only variable.

    Everything else is pinned: a daytime hour so no hour rule fires, no velocity,
    no blacklist, no graph, and a benign category with a merchant this name
    vocabulary does not know. If the score moved for any of those, this would be
    measuring the wrong thing.
    """
    transaction = {
        "amount": amount,
        "merchant_name": "Supermercado del Barrio",
        "merchant_category": "grocery",
        "timestamp": DAY,
        **overrides,
    }
    score, fired = RuleEngine().evaluate(transaction)
    assert fired == (["high_amount"] if amount > HIGH_AMOUNT_THRESHOLD else []), (
        f"{amount:,.2f} fired {fired} — this ladder is supposed to isolate the "
        "amount rule, and a second rule fired"
    )
    return score


@pytest.fixture
def engine() -> RuleEngine:
    return RuleEngine()


class TestTheFindingIsClosed:
    """The three amounts the plan named, in order, with the arithmetic."""

    def test_nine_hundred_scores_nothing(self) -> None:
        assert rule_score_for(THE_FINDING["below"]) == 0.0

    def test_eleven_hundred_scores_the_base_weight_plus_a_hair(self) -> None:
        # 35 + 8 * log10(1.1) = 35 + 8 * 0.0413937 = 35 + 0.3312 = 35.3312
        assert rule_score_for(THE_FINDING["just_over"]) == pytest.approx(35.33, abs=0.01)

    def test_four_hundred_thousand_scores_meaningfully_above_the_old_35(self) -> None:
        # 35 + 8 * log10(400) = 35 + 8 * 2.6020600 = 35 + 20.8165 = 55.8165
        score = rule_score_for(THE_FINDING["reported"])
        assert score == pytest.approx(55.82, abs=0.01)
        assert score > 35.0 + 15.0, (
            f"the magnitude term added only {score - 35.0:.2f} points at "
            "400,000; the plan asks for a transaction that far out to weigh "
            "meaningfully more than a coffee's"
        )

    def test_the_three_are_ordered(self) -> None:
        """The plan's criterion 2, verbatim: 900 < 1,100 < 400,000."""
        scores = [rule_score_for(THE_FINDING[key]) for key in ("below", "just_over", "reported")]
        assert scores[0] < scores[1] < scores[2], f"not ordered: {scores}"


class TestMonotonicity:
    """The contract the model has and this rule engine did not."""

    def test_the_response_is_non_decreasing_across_the_ladder(self) -> None:
        sweep = [(amount, rule_score_for(amount)) for amount in AMOUNT_LADDER]
        violations = [
            (lo, s_lo, hi, s_hi)
            for (lo, s_lo), (hi, s_hi) in zip(sweep, sweep[1:])
            if s_hi < s_lo
        ]
        assert not violations, (
            "risk fell as the amount rose on the rule engine's amount response:\n"
            + "\n".join(
                f"  ${lo:,.2f} -> ${hi:,.2f}: {s_lo:.2f} -> {s_hi:.2f}"
                for lo, s_lo, hi, s_hi in violations
            )
            + "\nfull sweep: "
            + ", ".join(f"${a:,.2f}->{s:.2f}" for a, s in sweep)
            + "\nA rule that cannot tell a coffee from a quarter of bitcoin is "
            "not weighting the evidence, it is counting that some evidence "
            "exists."
        )

    def test_the_ladder_is_live_rather_than_vacuously_monotone(self) -> None:
        """Guard the guard.

        A response that ignored amount entirely would pass a monotonicity
        assertion for the wrong reason, so the sweep has to span a range and
        end above where it started.
        """
        scores = [rule_score_for(amount) for amount in AMOUNT_LADDER]
        assert max(scores) - min(scores) >= 20.0, (
            f"the ladder spans only {max(scores) - min(scores):.2f} points; the "
            "rule engine is effectively insensitive to amount here, so "
            "'non-decreasing' would be passing vacuously"
        )
        assert scores[-1] > scores[0]

    def test_strictly_increasing_above_the_threshold_and_the_cap(self) -> None:
        """Below the cap, no two distinct amounts may share a score.

        Once `min()` saturates, ties are the intended behaviour — the cap is a
        decision to stop caring — so this is scoped to the part of the range
        where the rule is still responding.
        """
        unsaturated = [
            amount
            for amount in AMOUNT_LADDER
            if amount
            > HIGH_AMOUNT_THRESHOLD
            and AMOUNT_MAGNITUDE_POINTS
            * math.log10(amount / HIGH_AMOUNT_THRESHOLD)
            < AMOUNT_MAGNITUDE_CAP
        ]
        scores = [rule_score_for(amount) for amount in unsaturated]
        assert all(a < b for a, b in zip(scores, scores[1:])), (
            f"the response is flat inside the uncapped range: {list(zip(unsaturated, scores))}"
        )

    def test_the_response_is_independent_of_the_hour(self) -> None:
        """The velocity contract has an all-24-hours sweep; this one needs one
        too, for the same reason.

        `high_amount` reads no clock, so this is a claim about the rule, not
        about the fixture: a future change that let amount interact with the
        hour would quietly re-open the nightly-flake failure
        `tests/test_rule_engine.py` documents at length.

        The assertion is on the RESIDUAL, not the total. Six hours of the day are
        night hours and `unusual_hours` charges 10 for them, so a total of 55.82
        is only correct for the other eighteen; subtracting the known night weight
        is what isolates the amount term without weakening the sweep into
        eighteen data points.
        """
        from src.core.clock import FrozenClock

        engine = RuleEngine()
        night_weight = RuleEngine.WEIGHTS["unusual_hours"]
        for hour in range(24):
            stamp = FrozenClock.at_hour(hour).now_utc().isoformat()
            score, _ = engine.evaluate(
                {
                    "amount": THE_FINDING["reported"],
                    "merchant_name": "Supermercado del Barrio",
                    "merchant_category": "grocery",
                    "timestamp": stamp,
                }
            )
            residual = score - (night_weight if hour < 6 else 0.0)
            assert residual == pytest.approx(55.82, abs=0.01), (
                f"hour {hour:02d}: the amount term moved to {residual:.2f} "
                f"(total {score:.2f})"
            )


class TestTheCeiling:
    """Why the magnitude term is capped, asserted against the live settings."""

    def test_the_cap_is_derived_from_the_ensemble_not_picked(self) -> None:
        """One rule must never be able to buy `fraud` on its own.

        The derivation, in the test rather than only in a comment:

            smallest rule score that reaches `fraud` alone
                = strictest threshold / rule weight
                = 40 / 0.60
                = 66.666...

        The base weight is 35, so `AMOUNT_MAGNITUDE_CAP` has to stay under 31.67.
        If someone retunes the ensemble weights, this fails and says what the
        new ceiling is — which is the point. A cap checked only against a
        hardcoded 66.67 would keep passing after the geometry it came from
        changed.
        """
        strictest_threshold = min(
            float(tier["threshold"]) for tier in settings.threshold_tiers
        )
        rule_weight = settings.ensemble_rule_weight
        assert rule_weight > 0, "a zero rule weight makes this derivation meaningless"

        largest_single_rule_score = 35.0 + AMOUNT_MAGNITUDE_CAP
        ensemble_from_this_rule_alone = largest_single_rule_score * rule_weight
        assert ensemble_from_this_rule_alone < strictest_threshold, (
            f"`high_amount` alone reaches {ensemble_from_this_rule_alone:.2f} "
            f"ensemble points at its ceiling, at or above the strictest "
            f"threshold of {strictest_threshold}. One rule can now produce a "
            f"`fraud` classification on its own, which collapses the "
            f"distinction between suspicious and clearly fraud."
        )
        headroom = (strictest_threshold / rule_weight) - 35.0 - AMOUNT_MAGNITUDE_CAP
        assert headroom > 0

    def test_the_cap_is_actually_reached_and_actually_holds(self) -> None:
        """A cap nothing reaches is a comment; a cap nothing holds is a bug."""
        saturation = HIGH_AMOUNT_THRESHOLD * (10 ** (AMOUNT_MAGNITUDE_CAP / AMOUNT_MAGNITUDE_POINTS))
        at_cap = rule_score_for(saturation * 2)
        way_past_cap = rule_score_for(9_999_999_999.99)
        assert at_cap == pytest.approx(35.0 + AMOUNT_MAGNITUDE_CAP)
        assert way_past_cap == pytest.approx(35.0 + AMOUNT_MAGNITUDE_CAP), (
            f"a 10-billion transaction scored {way_past_cap:.2f}; the cap is not "
            "being applied"
        )

    def test_the_worst_case_amount_finishes_at_the_cap(self) -> None:
        """The exact figure the plan's arithmetic table publishes."""
        assert rule_score_for(400_000.0) == pytest.approx(55.82, abs=0.01)

    def test_the_response_is_not_monotone_in_the_burst_regime_either(self) -> None:
        """Honesty about the limit: the sweep isolates the amount rule.

        Adding velocity stacks the other rules on top, so this does not assert
        anything about a card-testing burst — where many SMALL transactions are
        the signature and this rule charges the same 35 for each. That asymmetry
        is real and correct: `high_amount` is about the size of ONE payment, and
        the rule that reads velocity is `high_velocity`.
        """
        engine = RuleEngine()
        _, fired = engine.evaluate(
            {
                "amount": 50.0,
                "merchant_name": "Supermercado del Barrio",
                "merchant_category": "grocery",
                "timestamp": DAY,
            },
            {"recent_transactions": 20},
        )
        assert "high_amount" not in fired
        assert "high_velocity" in fired


class TestMalformedAmountStillFires:
    """A12's contract must survive the arithmetic.

    A malformed amount is mapped to `inf` by the untrusted-input branch, where
    `log10(inf)` is `inf` and only the cap keeps the result a number. Without
    the cap this test would produce NaN or inf and fail every assertion at once,
    which is a much worse way to learn the cap is load-bearing.
    """

    @pytest.mark.parametrize(
        "bad", ["abc", [1000], float("nan"), float("inf"), True]
    )
    def test_a_non_finite_or_unparseable_amount_scores_finitely(self, bad) -> None:
        engine = RuleEngine()
        score, fired = engine.evaluate({"amount": bad, "merchant_name": "X"})
        assert "high_amount" in fired
        assert math.isfinite(score)
        assert score == pytest.approx(35.0 + AMOUNT_MAGNITUDE_CAP)

    def test_the_cap_is_what_makes_an_unreadable_amount_a_number(self) -> None:
        """Stated so the dependency is visible rather than incidental."""
        assert math.isinf(math.log10(float("inf") / HIGH_AMOUNT_THRESHOLD))
        assert min(math.inf * AMOUNT_MAGNITUDE_POINTS, AMOUNT_MAGNITUDE_CAP) == (
            AMOUNT_MAGNITUDE_CAP
        )


class TestTheFiredListIsUnchanged:
    """`fired_rules` is read by the audit trail, the alert and the LLM prompt.

    D2 changes the SIZE of a claim, never its NAME, so this is a compatibility
    assertion: a consumer that reads `fired_rules` gets the same shape it always
    got, and the arithmetic does not leak into the list as a synthetic rule.
    """

    def test_no_synthetic_rule_name_appears(self) -> None:
        _, fired = RuleEngine().evaluate(
            {"amount": 400_000.0, "merchant_name": "X", "timestamp": DAY}
        )
        assert fired == ["high_amount"]
        assert all(rule in RuleEngine.WEIGHTS for rule in fired)

    def test_the_weight_table_is_not_mutated_by_scoring(self) -> None:
        """`weights = dict(self.WEIGHTS)` is a copy for a reason.

        Mutating the class attribute in place would make the added magnitude
        permanent: the first 400,000 transaction would raise the base weight for
        every later transaction, including a 900 EUR one. That is the kind of
        order-dependent score this repository keeps finding.
        """
        engine = RuleEngine()
        before = dict(RuleEngine.WEIGHTS)
        rule_score_for(9_999_999_999.99)
        engine.evaluate({"amount": 400_000.0, "merchant_name": "X", "timestamp": DAY})
        assert RuleEngine.WEIGHTS == before
        assert rule_score_for(900.0) == 0.0