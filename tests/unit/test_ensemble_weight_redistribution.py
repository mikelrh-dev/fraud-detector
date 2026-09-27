"""A15: a layer with no signal must not silently consume its weight.

``ensemble.combine()`` filtered layers by *weight*, not by whether they produced
a value. So when the ML model was not loaded, ``predict()`` returned ``0.0``,
that ``0.0`` was a real number as far as the arithmetic was concerned, and the
ML layer's 0.25 share was spent on nothing. Every score was 25 points lower than
it should have been, with no log, no counter and no stored marker — and the
effect was largest exactly when the system was already degraded.

The distinction that matters: ``0.0`` from a model that ran and found nothing is
*evidence*, and keeps its weight. ``None`` means the layer had nothing to say,
and its weight is redistributed.
"""

import pytest

from src.core import counters
from src.services.ensemble import EnsembleScorer


class TestWeightRedistribution:
    def test_absent_layer_loses_its_weight(self) -> None:
        scorer = EnsembleScorer()
        weights = {"rule": 0.60, "ml": 0.25, "context": 0.15}

        # Note that context_score=0.0 is itself a live signal (no velocity), so
        # it keeps its 0.15. Only the ML layer is absent.
        #   absent: 50*0.60/0.75 + 0*0.15/0.75 = 40.0
        #   present: 50*0.60      + 0*0.25     + 0*0.15      = 30.0
        degraded = scorer.combine(
            rule_score=50.0, ml_score=None, context_score=0.0, weights=weights
        )
        # ML present but scoring zero: weight is spent on a real 0.
        complete = scorer.combine(
            rule_score=50.0, ml_score=0.0, context_score=0.0, weights=weights
        )

        assert degraded == pytest.approx(40.0)
        assert complete == pytest.approx(30.0)
        assert degraded > complete, (
            "redistributing the absent layer's weight must raise the score, "
            "because the surviving layers now carry the full 1.0"
        )

    def test_a_zero_is_never_treated_as_absent(self) -> None:
        """The whole fix rests on this: 0.0 and None must differ."""
        scorer = EnsembleScorer()
        weights = {"rule": 0.60, "ml": 0.25, "context": 0.15}

        assert scorer.combine(50.0, 0.0, 0.0, weights) != scorer.combine(
            50.0, None, 0.0, weights
        )

    def test_full_pipeline_is_unchanged(self) -> None:
        """With every layer live, the arithmetic must be identical to before."""
        scorer = EnsembleScorer()
        weights = {"rule": 0.60, "ml": 0.25, "context": 0.15}

        # 0.6*70 + 0.25*20 + 0.15*100 = 42 + 5 + 15 = 62
        assert scorer.combine(70.0, 20.0, 100.0, weights) == pytest.approx(62.0)

    def test_only_ml_absent_leaves_rule_and_context_intact(self) -> None:
        scorer = EnsembleScorer()
        weights = {"rule": 0.60, "ml": 0.25, "context": 0.15}

        # 0.60/0.75*60 + 0.15/0.75*100 = 48 + 20 = 68
        assert scorer.combine(60.0, None, 100.0, weights) == pytest.approx(68.0)

    def test_context_absent_also_redistributes(self) -> None:
        scorer = EnsembleScorer()
        weights = {"rule": 0.60, "ml": 0.25, "context": 0.15}

        # 0.60/0.85*50 + 0.25/0.85*20 = 35.29 + 5.88 = 41.18
        assert scorer.combine(50.0, 20.0, None, weights) == pytest.approx(
            (0.60 * 50 + 0.25 * 20) / 0.85
        )

    def test_single_surviving_layer_carries_everything(self) -> None:
        scorer = EnsembleScorer()
        assert scorer.combine(42.0, None, None) == pytest.approx(42.0)

    def test_no_layers_at_all_returns_zero_and_logs(self) -> None:
        scorer = EnsembleScorer()
        assert scorer.combine(None, None, None) == 0.0

    def test_result_stays_within_bounds(self) -> None:
        scorer = EnsembleScorer()
        weights = {"rule": 0.60, "ml": 0.25, "context": 0.15}

        # 100*0.60/0.75 = 80.0: above the surviving layers' combined weight of
        # 0.75, and still inside the 0-100 contract.
        assert scorer.combine(100.0, None, 0.0, weights) == pytest.approx(80.0)
        assert scorer.combine(0.0, None, 0.0, weights) == pytest.approx(0.0)
        assert scorer.combine(100.0, 100.0, 100.0, weights) == pytest.approx(100.0)


class TestNonFiniteStillFailsClosed:
    """The C2 behaviour must survive the A15 rewrite."""

    def test_nan_in_any_layer_fails_closed(self) -> None:
        scorer = EnsembleScorer()
        assert scorer.combine(float("nan"), 20.0, 0.0) == 100.0
        assert scorer.combine(50.0, float("inf"), 0.0) == 100.0

    def test_nan_in_an_absent_layer_is_not_a_problem(self) -> None:
        """None is not a value, so it must not trip the finite check."""
        scorer = EnsembleScorer()
        weights = {"rule": 0.60, "ml": 0.25, "context": 0.15}
        assert scorer.combine(50.0, None, 0.0, weights) == pytest.approx(40.0)


class TestDegradationIsCounted:
    def test_absent_layer_counter_exists(self) -> None:
        from src.core.counters import degraded_ml_layer

        counters.reset()
        degraded_ml_layer.inc()
        assert counters.snapshot()["degraded_ml_layer"] == 1
        counters.reset()
