"""Non-finite input must never whitelist a transaction (C2 / C3 regressions).

Every comparison against NaN is False in Python, so a single non-finite value
propagating through the ensemble used to fall through ``classify`` to
``'legitimate'``. These tests pin the fail-closed behaviour.
"""

import math

import numpy as np
import pytest

from src.schemas.transaction import TransactionCreate
from src.services.ensemble import EnsembleScorer
from src.services.feature_engine import FeatureEngine
from src.services.scoring_service import ScoringService, _to_finite_float

NON_FINITE = [float("nan"), float("inf"), float("-inf")]


class TestEnsembleRejectsNonFinite:
    """combine() and classify() must fail closed, never open."""

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_non_finite_context_does_not_classify_legitimate(self, bad: float):
        """The C2 bug: a NaN context whitelisted a high-value transaction."""
        scorer = EnsembleScorer()
        score = scorer.combine(rule_score=35.0, ml_score=0.012, context_score=bad)
        assert math.isfinite(score), "combine() must never return a non-finite score"
        assert score == 100.0, "non-finite input must fail closed to 100.0"
        assert scorer.classify(score, scorer.get_threshold(60000.0)) == "fraud"

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_non_finite_rule_score_fails_closed(self, bad: float):
        scorer = EnsembleScorer()
        assert scorer.combine(rule_score=bad, ml_score=10.0) == 100.0

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_non_finite_ml_score_fails_closed(self, bad: float):
        scorer = EnsembleScorer()
        assert scorer.combine(rule_score=10.0, ml_score=bad) == 100.0

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_classify_non_finite_score_is_fraud(self, bad: float):
        scorer = EnsembleScorer()
        assert scorer.classify(bad, 70.0) == "fraud"

    def test_healthy_input_still_works(self):
        """Guard against over-correcting into always-fraud."""
        scorer = EnsembleScorer()
        score = scorer.combine(rule_score=0.0, ml_score=0.0, context_score=0.0)
        assert score == 0.0
        assert scorer.classify(score, 70.0) == "legitimate"

        score = scorer.combine(rule_score=100.0, ml_score=100.0, context_score=100.0)
        assert score == 100.0
        assert scorer.classify(score, 70.0) == "fraud"


class TestGetThresholdNonFinite:
    """An unknown amount must pick the strictest tier, not fall through."""

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_non_finite_amount_uses_strictest_tier(self, bad: float):
        scorer = EnsembleScorer()
        threshold = scorer.get_threshold(bad)
        assert math.isfinite(threshold)
        # Strictest = the lowest configured threshold = easiest to flag.
        from src.core.config import settings

        assert threshold == min(float(t["threshold"]) for t in settings.threshold_tiers)

    def test_inf_no_longer_silently_uses_the_default(self):
        """Before the fix get_threshold(inf) returned 70.0 by accident."""
        scorer = EnsembleScorer()
        assert scorer.get_threshold(float("inf")) != 70.0

    def test_real_boundaries_unchanged(self):
        """The finite path must be untouched."""
        scorer = EnsembleScorer()
        assert scorer.get_threshold(0.0) == 70.0
        assert scorer.get_threshold(1000.0) == 70.0
        assert scorer.get_threshold(1000.01) == 50.0
        assert scorer.get_threshold(10000.01) == 45.0
        assert scorer.get_threshold(50000.01) == 40.0
        assert scorer.get_threshold(1e12) == 40.0


class TestTransactionAmountBounds:
    """The API must reject values the scoring pipeline cannot handle."""

    def _payload(self, amount):
        return {
            "amount": amount,
            "currency": "USD",
            "merchant_name": "Test",
            "card_last4": "1234",
        }

    def test_infinite_amount_is_rejected(self):
        """The C3 bug: inf was accepted and scored as legitimate."""
        with pytest.raises(ValueError):
            TransactionCreate(**self._payload(float("inf")))

    def test_nan_amount_is_rejected(self):
        with pytest.raises(ValueError):
            TransactionCreate(**self._payload(float("nan")))

    def test_negative_amount_is_rejected(self):
        with pytest.raises(ValueError):
            TransactionCreate(**self._payload(-1.0))

    def test_zero_amount_is_rejected(self):
        with pytest.raises(ValueError):
            TransactionCreate(**self._payload(0.0))

    def test_ordinary_amount_is_accepted(self):
        model = TransactionCreate(**self._payload(1234.56))
        assert model.amount == 1234.56

    def test_amount_above_column_precision_is_rejected(self):
        """Numeric(12,2) tops out at 9_999_999_999.99."""
        with pytest.raises(ValueError):
            TransactionCreate(**self._payload(1e13))


class TestToFiniteFloat:
    """The arithmetic guard used by the context score."""

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_maps_non_finite_to_zero(self, bad: float):
        assert _to_finite_float(bad) == 0.0

    def test_preserves_finite_values(self):
        assert _to_finite_float(5) == 5.0
        assert _to_finite_float("2.5") == 2.5
        assert _to_finite_float(None) == 0.0
        assert _to_finite_float("abc") == 0.0


class TestFeatureVectorAlwaysFinite:
    """The model contract is 10 finite floats. Always."""

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_non_finite_amount_yields_finite_vector(self, bad: float):
        engine = FeatureEngine()
        vector = engine.transform(
            {"amount": bad, "timestamp": "2024-06-15T14:30:00+00:00"}
        )
        assert vector.shape == (10,)
        assert np.isfinite(vector).all()

    def test_non_finite_history_yields_finite_vector(self):
        engine = FeatureEngine()
        vector = engine.transform(
            {"amount": 500.0, "timestamp": "2024-06-15T14:30:00+00:00"},
            user_history={"avg_amount": float("nan"), "std_amount": float("inf")},
        )
        assert vector.shape == (10,)
        assert np.isfinite(vector).all()


class TestScoringServiceContextIsFinite:
    """The reachable producer of the NaN must be fixed at the source."""

    @pytest.mark.asyncio
    async def test_nan_recent_transactions_does_not_poison_the_score(self):
        from unittest.mock import MagicMock

        rule_engine = MagicMock()
        rule_engine.evaluate.return_value = (35.0, ["high_amount"])
        feature_engine = MagicMock()
        feature_engine.transform.return_value = np.zeros(10)
        ml_service = MagicMock()
        ml_service.predict.return_value = 0.012
        ensemble = MagicMock()
        ensemble.get_threshold.return_value = 40.0
        ensemble.combine.return_value = 21.0
        ensemble.classify.return_value = "review"

        service = ScoringService(
            rule_engine=rule_engine,
            feature_engine=feature_engine,
            ml_service=ml_service,
            ensemble_scorer=ensemble,
        )

        await service.compute_scores(
            tx_data={"amount": 60000},
            context={"recent_transactions": float("nan")},
            user_history={},
        )

        context_score = ensemble.combine.call_args.kwargs["context_score"]
        assert math.isfinite(context_score), (
            f"context_score must be finite, got {context_score!r}"
        )
        assert context_score == 0.0
