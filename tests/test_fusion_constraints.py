"""Fusion constraints on the ensemble weights in `src/core/config.py`.

The three weights are the one knob that can silently re-classify real
transactions, and nothing about the arithmetic itself would complain. A weight
retune is a pure edit to three floats: every score moves, no test errors from
a shape mismatch, and the only visible effect is that some transactions start
landing in a different band. So the constraint has to be stated as a
*classification* on a named transaction, not as a formula.

Every expectation here goes through `EnsembleScorer` with **no `weights=`
argument**, so it reads whatever `settings` holds at call time. A test that
passed the weights explicitly would keep passing after the config changed and
would guard nothing — which is exactly the failure mode this file exists to
prevent.

Constraint 1 (the case that started this): 400,000 USD to `binance` at 03:00
with no velocity must classify as `fraud`. The unconstrained F1 optimum moves
most of the weight onto the ML layer, and that layer scores this transaction
low, so the unconstrained optimum classifies clear, textbook fraud as
`legitimate`. That is the regression this file pins.

Constraint 2 (the plan's done-criteria, `docs/plans/2026-10-01-comercio-magnitud-categoria.md`):
the rule score is monotone in amount with the published figures, and an
invented category is refused at the schema edge. The rule-score figures are
properties of the rule engine, not of the weights, so they are asserted here
as the geometry the weights are calibrated against: they are the input side of
the arithmetic constraint 1 is about.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.schemas.transaction import TransactionCreate
from src.services.ensemble import EnsembleScorer
from src.services.feature_engine import FeatureEngine
from src.services.ml_model import MLModelService
from src.services.rule_engine import RuleEngine

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The deployed artifact. Same override convention as
#: ``tests/test_model_amount_monotonicity.py``: the constraint must be
#: pointable at a historical artifact to prove it is a real guard.
MODEL_PATH = Path(
    os.environ.get("FRAUD_MODEL_PATH", REPO_ROOT / "models" / "xgboost_paysim_v1.joblib")
)

#: 03:00 UTC, and the user's normal spend is $200. Both fixed because both
#: move the rule score: the hour fires `unusual_hours`/`off_hours_crypto` and
#: the history drives the deviation features.
CASE_A = {
    "amount": 400000.0,
    "merchant_name": "binance",
    "merchant_category": "retail",
    "timestamp": "2026-10-03T03:00:00+00:00",
}

CASE_A_HISTORY = {
    "avg_amount": 200.0,
    "std_amount": 150.0,
    "tx_count_last_5min": 0,
    "tx_count_last_1h": 0,
}

CASE_A_CONTEXT = {
    "recent_transactions": 0,
    "merchant_blacklist": [],
    "known_cards": [],
    "home_country": "ES",
    "graph_features": None,
}


@pytest.fixture(scope="module")
def ml_service() -> MLModelService:
    """The deployed model, or skip: the constraint is about a real ml_score."""
    if not MODEL_PATH.exists():
        pytest.skip(f"model artifact absent at {MODEL_PATH}")
    service = MLModelService(model_path=str(MODEL_PATH))
    if not service.load_model():
        pytest.skip(f"model artifact at {MODEL_PATH} failed to load")
    return service


def case_a_layers(ml_service: MLModelService) -> tuple[float, float, float]:
    """(rule_score, ml_score, context_score) for CASE_A through the real engines."""
    rule_score, _fired = RuleEngine().evaluate(dict(CASE_A), context=dict(CASE_A_CONTEXT))
    features = FeatureEngine().transform(dict(CASE_A), user_history=dict(CASE_A_HISTORY))
    ml_score = float(ml_service.predict(features))
    # Same expression as ScoringService.compute_scores, so the context layer is
    # the production one and not a convenient stand-in for it.
    recent = float(CASE_A_CONTEXT["recent_transactions"])
    context_score = min(recent / 10.0 * 100, 100.0)
    return rule_score, ml_score, context_score


class TestCaseAStaysFraud:
    """Constraint 1: the transaction that motivated the weight question."""

    def test_classifies_as_fraud(self, ml_service: MLModelService) -> None:
        rule_score, ml_score, context_score = case_a_layers(ml_service)
        scorer = EnsembleScorer()
        threshold = scorer.get_threshold(CASE_A["amount"])
        score = scorer.combine(
            rule_score=rule_score,
            ml_score=ml_score,
            context_score=context_score,
        )
        classification = scorer.classify(score, threshold)
        assert classification == "fraud", (
            f"400k USD to `binance` at 03:00 scored {score:.2f} against a "
            f"threshold of {threshold:.2f} and was classified `{classification}`. "
            f"Layers: rule={rule_score:.2f} ml={ml_score:.2f} "
            f"context={context_score:.2f}. A quarter-bitcoin-sized transfer to a "
            f"crypto exchange is not a borderline case; the unconstrained F1 "
            f"optimum reclassifies it as `legitimate` and that is not an "
            f"acceptable trade."
        )

    def test_clears_the_threshold_with_margin(self, ml_service: MLModelService) -> None:
        """Not "equal to" — the constraint is a margin, not a knife edge.

        Asserting ``score > threshold`` alone would still pass on a weight set
        that lands 0.001 above the line, where a one-point change in any layer
        silently flips a real fraud case back to review.
        """
        rule_score, ml_score, context_score = case_a_layers(ml_service)
        scorer = EnsembleScorer()
        threshold = scorer.get_threshold(CASE_A["amount"])
        score = scorer.combine(
            rule_score=rule_score,
            ml_score=ml_score,
            context_score=context_score,
        )
        margin = score - threshold
        assert margin >= 10.0, (
            f"only {margin:.2f} points of headroom between the case-A score "
            f"({score:.2f}) and its threshold ({threshold:.2f}). The critical "
            f"tier's review band starts at {threshold * 0.75:.2f}, so less than "
            f"{threshold * 0.25:.2f} points of margin is what separates `fraud` "
            f"from `review` for this transaction."
        )

    def test_the_rule_layer_alone_cannot_be_silenced(self) -> None:
        """Structural form of the same constraint, independent of the artifact.

        CASE_A's rule score is 100 (four rules fire). At the shipped rule
        weight that is 60 ensemble points against a critical threshold of 40,
        so the transaction stays fraud even if the ML layer were to score it
        zero. Stated on the weight itself so it holds with any ml_score.
        """
        rule_score, _fired = RuleEngine().evaluate(dict(CASE_A), context=dict(CASE_A_CONTEXT))
        threshold = EnsembleScorer().get_threshold(CASE_A["amount"])
        from_rules_alone = rule_score * settings.ensemble_rule_weight
        assert from_rules_alone > threshold, (
            f"the rule layer alone contributes {from_rules_alone:.2f} ensemble "
            f"points at weight {settings.ensemble_rule_weight}, at or below the "
            f"critical threshold of {threshold:.2f}."
        )


class TestWeightsAreANormalisedTriple:
    """Why the three numbers are ratios and not three free parameters."""

    def test_they_sum_to_one(self) -> None:
        total = (
            settings.ensemble_rule_weight
            + settings.ensemble_ml_weight
            + settings.ensemble_context_weight
        )
        assert total == pytest.approx(1.0), (
            f"the weights sum to {total}, not 1.0. `EnsembleScorer.combine` "
            f"renormalises the *active* weights, so the sum is not load-bearing "
            f"for the arithmetic — it is the readability contract, and a triple "
            f"that does not sum to 1.0 misreports every published layer score."
        )

    def test_every_layer_carries_a_positive_weight(self) -> None:
        """A zero weight deletes the layer from the ensemble, not just from it.

        `combine` drops any layer whose weight is 0 from the active set, so a
        zeroed weight silently removes the layer's contribution entirely
        instead of merely discounting it.
        """
        for name in ("ensemble_rule_weight", "ensemble_ml_weight", "ensemble_context_weight"):
            value = float(getattr(settings, name))
            assert value > 0.0, f"{name} is {value}; that layer is now excluded from the ensemble"


class TestPlanRuleScoreGeometry:
    """Constraint 2: the rule-score ladder the plan publishes.

    These are the weights' input side. They belong to the rule engine rather
    than to the config, but a weight retune is the change most likely to be
    *justified* by these numbers, so they are pinned here together with the
    classification constraint they support: a geometry that moves would
    invalidate the calibration the weights were chosen against.
    """

    #: amount -> published rule score. 900 is under `HIGH_AMOUNT_THRESHOLD`
    #: (1000) so it scores nothing at all; 2M saturates `AMOUNT_MAGNITUDE_CAP`.
    LADDER = (
        (900.0, 0.0),
        (1100.0, 35.3),
        (5000.0, 40.6),
        (50_000.0, 48.6),
        (400_000.0, 55.8),
        (2_000_000.0, 60.0),
    )

    @pytest.mark.parametrize(("amount", "expected"), LADDER)
    def test_rule_score_at_published_amounts(self, amount: float, expected: float) -> None:
        score, _fired = RuleEngine().evaluate(
            {"amount": amount, "merchant_name": "acme", "merchant_category": "retail",
             "timestamp": "2026-10-03T14:00:00+00:00"},
            context={"recent_transactions": 0, "merchant_blacklist": [],
                     "known_cards": [], "home_country": "ES", "graph_features": None},
        )
        assert score == pytest.approx(expected, abs=0.05), (
            f"{amount:,.0f} scored {score:.2f}, the plan publishes {expected:.2f}"
        )

    def test_the_ladder_is_strictly_increasing(self) -> None:
        scores = [
            RuleEngine().evaluate(
                {"amount": amount, "merchant_name": "acme", "merchant_category": "retail",
                 "timestamp": "2026-10-03T14:00:00+00:00"},
                context={"recent_transactions": 0, "merchant_blacklist": [],
                         "known_cards": [], "home_country": "ES", "graph_features": None},
            )[0]
            for amount, _expected in self.LADDER
        ]
        for (low_amount, _), low, ((high_amount, _), high) in zip(
            zip(self.LADDER, scores), scores, zip(self.LADDER[1:], scores[1:])
        ):
            assert high > low, (
                f"rule score did not increase from {low_amount:,.0f} ({low:.2f}) "
                f"to {high_amount:,.0f} ({high:.2f})"
            )


class TestCategoryIsRefusedAtTheEdge:
    """Constraint 2: the field that picks the features is a closed vocabulary."""

    def test_an_invented_category_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            TransactionCreate(
                amount=10.0,
                currency="USD",
                merchant_name="acme",
                merchant_category="definitely-not-a-category",
                card_last4="1232",
            )
        message = str(excinfo.value)
        assert "not a known category" in message, (
            f"the rejection must name the problem and the vocabulary, got: {message}"
        )

    @pytest.mark.parametrize("value", ["retail", "cryptocurrency", "cripto", "crypto-exchange"])
    def test_known_categories_and_aliases_still_pass(self, value: str) -> None:
        """D3's edge must not become a new outage: aliases keep working."""
        accepted = TransactionCreate(
            amount=10.0,
            currency="USD",
            merchant_name="acme",
            merchant_category=value,
            card_last4="1232",
        )
        assert accepted.merchant_category == value, (
            "the edge must return what the client sent, not a canonical spelling — "
            "both engines normalize on their own, and rewriting here would make "
            "the stored row disagree with the request that created it"
        )