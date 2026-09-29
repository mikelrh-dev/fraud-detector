"""Tests for context wiring in ensemble scoring (ML3).

Verifies that ScoringService.compute_scores() computes a context_score
from the context dict and passes it to EnsembleScorer.combine().

D1-2. The three `context_score` tests this file used to hold re-implemented the
formula in the test body:

    context_score = min(ctx.get("recent_transactions", 0) / 10.0 * 100, 100)
    assert context_score == 50.0

That asserts Python arithmetic, not the service. Change the divisor in
`scoring_service.py:143` from `/10.0` to `/20.0` and all three stay green --
they were computing the right answer from a copy of the formula nobody edits.
They also constructed an `EnsembleScorer` they never used, which is the tell
that the test was not about the ensemble at all.

Every test below now goes through `compute_scores` and asserts on what the
service passed to `combine`. `context_score_for` is a spy, not a mock: a
MagicMock accepts any call and asserts nothing about the argument.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.services.ensemble import EnsembleScorer
from src.services.scoring_service import ScoringService


def _service_with_captured_context_score() -> tuple[ScoringService, MagicMock]:
    """A service whose ensemble records the context_score it was handed.

    The ensemble is a MagicMock because the tests here are about the value the
    SERVICE produced, not about the combination. What matters is that
    `combine` was called with the number the service computed, so the call is
    asserted unconditionally -- the old
    `if "context_score" in call_kwargs.kwargs:` guard silently passed when the
    keyword was absent altogether.
    """
    rule_engine = MagicMock()
    rule_engine.evaluate.return_value = (0.0, [])

    feature_engine = MagicMock()
    feature_engine.transform.return_value = np.zeros(10)

    ml_service = MagicMock()
    ml_service.is_available = False
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
    return service, ensemble


async def context_score_for(context: dict) -> float:
    """The context_score `compute_scores` actually passed to the ensemble."""
    service, ensemble = _service_with_captured_context_score()
    await service.compute_scores({"amount": 100}, context, {})
    return ensemble.combine.call_args.kwargs["context_score"]


class TestContextWiring:
    """ScoringService should compute and pass context_score to ensemble."""

    @pytest.mark.asyncio
    async def test_context_score_velocity_normalization(self):
        """5 recent transactions is half of the saturation velocity.

        The constant this pins is 10 transactions: 5/10 saturates at half
        scale, 5/20 would be a quarter. Asserted through the service, so
        changing the divisor in scoring_service.py fails HERE.
        """
        assert await context_score_for({"recent_transactions": 5}) == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_context_score_capped_at_100(self):
        """High velocity saturates rather than exceeding the 0-100 range.

        50 recent transactions is 5x the saturation velocity, so the cap is
        what is under test and not the arithmetic.
        """
        assert await context_score_for({"recent_transactions": 50}) == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_context_score_zero_when_missing(self):
        """Absent recent_transactions is 0, not an error.

        Absent means "no velocity context was gathered", which is a normal
        state for a first transaction. It is not the same claim as a
        non-finite value, which IS sanitized and logged.
        """
        assert await context_score_for({}) == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_context_score_is_monotonic_in_velocity(self):
        """The property the three cases above are instances of.

        A test that pins one value passes when the formula is replaced by a
        different one that happens to agree at that value. Monotonicity plus
        the cap is what "velocity feeds a bounded 0-100 signal" means.
        """
        scores = [
            await context_score_for({"recent_transactions": n})
            for n in (0, 1, 2, 5, 8, 10, 11, 25)
        ]
        assert scores == sorted(scores)
        assert scores[0] == pytest.approx(0.0)
        assert scores[-1] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_non_finite_velocity_is_sanitized_not_propagated(self):
        """NaN in, zero out.

        Every comparison against NaN is False, so a NaN that reached the
        ensemble would classify the transaction as legitimate -- the
        worst direction for a fraud system to fail in.
        """
        assert await context_score_for({"recent_transactions": float("nan")}) == pytest.approx(0.0)
        # +inf maps to 0, not to the 100 the cap would give it. That is the
        # sanitizer's documented behaviour (`_to_finite_float`), and the
        # distinction matters: +inf here is a corrupt count, not a very active
        # user, and the two claims must not be conflated.
        assert await context_score_for({"recent_transactions": float("inf")}) == pytest.approx(0.0)


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

        await service.compute_scores(tx_data, context, user_history)

        # Unconditional. This used to be
        #     if "context_score" in call_kwargs.kwargs: assert ...
        # which passes for free when the service stops passing the argument at
        # all -- the assertion is exactly the thing that had gone missing.
        assert ensemble.combine.call_args.kwargs["context_score"] == pytest.approx(50.0)

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

        assert ensemble.combine.call_args.kwargs["context_score"] == pytest.approx(100.0)
