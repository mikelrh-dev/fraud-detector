"""Monitoring service tests — drift detection, performance metrics, retraining triggers.

Tests for the monitoring service that tracks model drift, computes performance
metrics, and triggers retraining recommendations.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from src.services.monitoring import MonitoringService


class TestComputeDrift:
    """Drift detection logic — compares reference vs current data distributions."""

    def test_drift_detected_when_distributions_differ(self):
        """Significantly different distributions should detect drift."""
        service = MonitoringService()
        reference = [10.0, 12.0, 11.0, 13.0, 10.5, 11.5, 12.5, 9.0, 14.0, 11.0]
        # Current data with mean much higher than reference
        current = [10.0, 100.0, 90.0, 110.0, 95.0, 105.0, 85.0, 115.0, 92.0, 108.0]

        report = service.compute_drift(reference, current)

        assert report["drift_detected"] is True
        assert report["drift_score"] > 30
        assert "feature_drift" in report
        assert "prediction_drift" in report

    def test_no_drift_when_distributions_similar(self):
        """Similar distributions should not detect drift."""
        service = MonitoringService()
        reference = [10.0, 12.0, 11.0, 13.0, 10.5, 11.5, 12.5, 9.0, 14.0, 11.0]
        # Current data similar to reference
        current = [11.0, 11.5, 12.0, 10.5, 13.0, 10.0, 12.5, 11.5, 14.0, 9.0]

        report = service.compute_drift(reference, current)

        assert report["drift_detected"] is False
        assert report["drift_score"] < 10
        assert report["feature_drift"] == []
        assert isinstance(report["prediction_drift"], dict)

    def test_drift_with_empty_current_data(self):
        """Empty current data should not crash."""
        service = MonitoringService()
        reference = [10.0, 12.0, 11.0]
        current: list[float] = []

        report = service.compute_drift(reference, current)

        assert report["drift_detected"] is False
        assert report["drift_score"] == 0.0

    def test_drift_with_empty_reference_data(self):
        """Empty reference data should not crash."""
        service = MonitoringService()
        reference: list[float] = []
        current = [10.0, 12.0, 11.0]

        report = service.compute_drift(reference, current)

        assert report["drift_detected"] is False
        assert report["drift_score"] == 0.0

    def test_prediction_drift_quantified(self):
        """Prediction drift should quantify mean and std deviation shift."""
        service = MonitoringService()
        reference = [20.0, 22.0, 21.0, 23.0]
        current = [80.0, 82.0, 81.0, 83.0]

        report = service.compute_drift(reference, current)

        assert "prediction_drift" in report
        pd = report["prediction_drift"]
        assert "reference_mean" in pd
        assert "current_mean" in pd
        assert pd["current_mean"] > pd["reference_mean"]


class TestComputeMetrics:
    """Performance metric computation: precision, recall, F1, AUC-ROC."""

    def test_perfect_predictions(self):
        """All correct predictions should give perfect metrics."""
        service = MonitoringService()
        predictions = np.array([1, 0, 1, 0, 1])
        actuals = np.array([1, 0, 1, 0, 1])

        metrics = service.compute_metrics(predictions, actuals)

        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1"] == 1.0
        assert metrics["auc_roc"] == 1.0
        assert "timestamp" in metrics

    def test_no_true_positives(self):
        """No true positives should give zero precision and recall."""
        service = MonitoringService()
        predictions = np.array([1, 1, 1])
        actuals = np.array([0, 0, 0])

        metrics = service.compute_metrics(predictions, actuals)

        assert metrics["precision"] == 0.0
        assert metrics["recall"] == 0.0
        assert metrics["f1"] == 0.0

    def test_partial_performance(self):
        """Partial correct predictions should give intermediate metrics."""
        service = MonitoringService()
        predictions = np.array([1, 1, 0, 0, 1])
        actuals = np.array([1, 0, 0, 1, 1])
        # TP=2 (idx 0, 4), FP=1 (idx 1), TN=1 (idx 2), FN=1 (idx 3)
        # precision=2/3≈0.667, recall=2/3≈0.667, f1=2/3≈0.667

        metrics = service.compute_metrics(predictions, actuals)

        assert metrics["precision"] == pytest.approx(2 / 3, abs=0.01)
        assert metrics["recall"] == pytest.approx(2 / 3, abs=0.01)
        assert metrics["f1"] == pytest.approx(2 / 3, abs=0.01)

    def test_empty_predictions(self):
        """Empty predictions should return zero metrics."""
        service = MonitoringService()
        predictions = np.array([])
        actuals = np.array([])

        metrics = service.compute_metrics(predictions, actuals)

        assert metrics["precision"] == 0.0
        assert metrics["recall"] == 0.0
        assert metrics["f1"] == 0.0
        assert metrics["auc_roc"] == 0.0

    def test_single_class_predictions(self):
        """Single class predictions should still compute AUC-ROC."""
        service = MonitoringService()
        predictions = np.array([1, 1, 1, 1])
        actuals = np.array([1, 1, 1, 1])

        metrics = service.compute_metrics(predictions, actuals)

        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1"] == 1.0


class TestTrackModelRun:
    """Model run persistence — stores metrics and drift status."""

    @pytest.mark.asyncio
    async def test_track_model_run_creates_record(self):
        """track_model_run should add an MLModelRun and flush."""
        service = MonitoringService()
        mock_db = AsyncMock()
        mock_run = MagicMock()
        mock_run.id = "run-uuid-123"
        mock_db.add = MagicMock()

        # Patch MLModelRun constructor
        result = await service.track_model_run(
            db=mock_db,
            model_version="v1.0",
            metrics={"f1": 0.85, "precision": 0.80, "recall": 0.90},
            drift_detected=False,
            _run_instance=mock_run,
        )

        assert result is mock_run
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_model_run_with_drift_detected(self):
        """track_model_run with drift should set drift_detected=True."""
        service = MonitoringService()
        mock_db = AsyncMock()

        # Use a real MLModelRun-like object for meaningful assertions
        class FakeRun:
            def __init__(self):
                self.id = "run-uuid-456"
                self.drift_detected = None
                self.model_version = None
                self.metrics = None
                self.status = None

        fake_run = FakeRun()

        result = await service.track_model_run(
            db=mock_db,
            model_version="v2.0",
            metrics={"f1": 0.65, "precision": 0.60},
            drift_detected=True,
            _run_instance=fake_run,
        )

        assert result.drift_detected is True


class TestCheckRetrainingTrigger:
    """Retraining trigger logic — F1 < 0.7 or drift_score > 30."""

    def test_trigger_when_f1_below_threshold(self):
        """F1 score below 0.7 should trigger retraining."""
        service = MonitoringService()
        metrics = {"f1": 0.65, "precision": 0.60, "recall": 0.70}
        assert service.check_retraining_trigger(metrics) is True

    def test_no_trigger_when_f1_above_threshold(self):
        """F1 score above 0.7 with no drift should not trigger."""
        service = MonitoringService()
        metrics = {"f1": 0.85, "precision": 0.80, "recall": 0.90}
        assert service.check_retraining_trigger(metrics) is False

    def test_trigger_when_drift_score_high(self):
        """Drift score above 30 should trigger retraining."""
        service = MonitoringService()
        metrics = {"f1": 0.85, "drift_score": 45}
        assert service.check_retraining_trigger(metrics) is True

    def test_trigger_at_f1_boundary(self):
        """F1 exactly 0.7 should NOT trigger (threshold is < 0.7)."""
        service = MonitoringService()
        metrics = {"f1": 0.7, "precision": 0.70, "recall": 0.70}
        assert service.check_retraining_trigger(metrics) is False

    def test_no_trigger_with_missing_f1(self):
        """Missing F1 should not trigger (can't measure)."""
        service = MonitoringService()
        metrics = {"precision": 0.80, "recall": 0.90}
        assert service.check_retraining_trigger(metrics) is False

    def test_no_trigger_with_no_metrics(self):
        """Empty metrics should not trigger."""
        service = MonitoringService()
        assert service.check_retraining_trigger({}) is False
