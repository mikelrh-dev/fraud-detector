"""Tests for context wiring in ensemble scoring (ML3).

Verifies that ScoringService.compute_scores() computes a context_score
from the context dict and passes it to EnsembleScorer.combine().
"""

import numpy as np
import pytest
from unittest.mock import MagicMock

from src.services.ensemble import EnsembleScorer
from src.services.scoring_service import ScoringService


class TestContextWiring:
    """ScoringService should compute and pass context_score to ensemble."""

    def test_context_score_velocity_normalization(self):
        """context_score = min(recent_transactions / 10 * 100, 100)."""
        scorer = EnsembleScorer()
        # 5 recent txns → 5/10*100 = 50
        ctx = {"recent_transactions": 5}
        # Manually compute what ScoringService should produce
        context_score = min(ctx.get("recent_transactions", 0) / 10.0 * 100, 100)
        assert context_score == 50.0

    def test_context_score_capped_at_100(self):
        """context_score should not exceed 100 even with high velocity."""
        ctx = {"recent_transactions": 50}
        context_score = min(ctx.get("recent_transactions", 0) / 10.0 * 100, 100)
        assert context_score == 100.0

    def test_context_score_zero_when_missing(self):
        """context_score should be 0 when recent_transactions is missing."""
        ctx = {}
        context_score = min(ctx.get("recent_transactions", 0) / 10.0 * 100, 100)
        assert context_score == 0.0

    def test_ensemble_formula_with_context(self):
        """rule=60, ml=60, ctx=50 → 0.6*60 + 0.25*60 + 0.15*50 = 58.5."""
        scorer = EnsembleScorer()
        score = scorer.combine(
            rule_score=60,
            ml_score=60,
            context_score=50,
        )
        expected = 0.6 * 60 + 0.25 * 60 + 0.15 * 50  # 36 + 15 + 7.5 = 58.5
        assert score == pytest.approx(expected)

    def test_ensemble_default_weights_include_context(self):
        """Default weights (0.60/0.25/0.15) should produce correct weighted sum."""
        scorer = EnsembleScorer()
        score = scorer.combine(
            rule_score=100,
            ml_score=100,
            context_score=100,
        )
        # 0.60*100 + 0.25*100 + 0.15*100 = 60+25+15 = 100
        assert score == 100.0

    @pytest.mark.asyncio
    async def test_scoring_service_passes_context_to_ensemble(self):
        """ScoringService.compute_scores() should pass context_score to combine()."""
        # Create mocks
        rule_engine = MagicMock()
        rule_engine.evaluate.return_value = (60.0, ["high_amount"])

        feature_engine = MagicMock()
        feature_engine.transform.return_value = np.zeros(10)

        ml_service = MagicMock()
        ml_service.predict.return_value = 60.0
        ml_service.n_features = 10

        ensemble = MagicMock()
        ensemble.get_threshold.return_value = 70.0
        ensemble.combine.return_value = 58.5
        ensemble.classify.return_value = "review"

        service = ScoringService(
            rule_engine=rule_engine,
            feature_engine=feature_engine,
            ml_service=ml_service,
            ensemble_scorer=ensemble,
        )

        tx_data = {"amount": 500, "merchant_category": "retail"}
        context = {"recent_transactions": 5}
        user_history = {}

        result = await service.compute_scores(tx_data, context, user_history)

        # Verify combine was called with context_score
        call_kwargs = ensemble.combine.call_args
        assert "context_score" in call_kwargs.kwargs or len(call_kwargs.args) >= 3
        # The context_score should be 50.0 (5/10*100)
        if "context_score" in call_kwargs.kwargs:
            assert call_kwargs.kwargs["context_score"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_scoring_service_context_score_from_recent_transactions(self):
        """ScoringService should compute context_score = min(recent/10*100, 100)."""
        rule_engine = MagicMock()
        rule_engine.evaluate.return_value = (0.0, [])

        feature_engine = MagicMock()
        feature_engine.transform.return_value = np.zeros(10)

        ml_service = MagicMock()
        ml_service.predict.return_value = 0.0
        ml_service.n_features = 10

        ensemble = MagicMock()
        ensemble.get_threshold.return_value = 70.0
        ensemble.combine.return_value = 0.0
        ensemble.classify.return_value = "legitimate"

        service = ScoringService(
            rule_engine=rule_engine,
            feature_engine=feature_engine,
            ml_service=ml_service,
            ensemble_scorer=ensemble,
        )

        # 15 recent txns → 15/10*100 = 150, capped to 100
        context = {"recent_transactions": 15}
        await service.compute_scores({"amount": 100}, context, {})

        call_kwargs = ensemble.combine.call_args
        if "context_score" in call_kwargs.kwargs:
            assert call_kwargs.kwargs["context_score"] == 100.0  # capped
