"""ML model tests — scoring with serialized mock model, missing model,
score range 0-100, anomaly score normalization.

These tests verify the second scoring layer: anomaly detection via
Isolation Forest.
"""

import os
import tempfile
from unittest.mock import patch

import joblib
import numpy as np
import pytest
from sklearn.ensemble import IsolationForest

from src.services.ml_model import MLModelService


@pytest.fixture(scope="module")
def mock_model_path():
    """Create a temporary IsolationForest model for testing.

    Uses 10 features matching the FeatureEngine output dimensionality.
    """
    # Train a tiny IsolationForest on dummy 10-feature data
    rng = np.random.RandomState(42)
    # Normal transactions (50 samples)
    X_normal = rng.normal(loc=50, scale=10, size=(50, 10))
    # Anomalous transactions (10 samples)
    X_anomaly = rng.normal(loc=500, scale=100, size=(10, 10))
    X = np.vstack([X_normal, X_anomaly])
    model = IsolationForest(
        n_estimators=10,
        random_state=42,
        contamination=0.1,
    )
    model.fit(X)

    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as f:
        path = f.name
        joblib.dump(model, path)

    yield path

    # Cleanup
    os.unlink(path)


class TestMLModelScore:
    """ML model scoring behavior."""

    def test_predict_returns_float_between_0_and_100(self, mock_model_path):
        """Predict should return a float in range 0-100 for any input."""
        service = MLModelService(model_path=mock_model_path)
        service.load_model()

        features = np.array([100.0, 0.0, 0.0, 0.0, 0.0, 14.0, 0.0, 0.0, 0.0, 0.0])
        score = service.predict(features)
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_anomaly_gets_high_score(self, mock_model_path):
        """An anomaly (-1) should map to a high score (> 50)."""
        service = MLModelService(model_path=mock_model_path)
        service.load_model()

        # A very large amount (100000) should be anomalous
        features = np.array([100000.0, 5.0, 3.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 1.0])
        score = service.predict(features)
        # Anomalous features should score higher
        assert score > 50

    def test_normal_gets_low_score(self, mock_model_path):
        """A normal transaction should map to a lower score."""
        service = MLModelService(model_path=mock_model_path)
        service.load_model()

        # Normal values near the training data mean
        normal_features = np.array([50.0, 0.0, 0.0, 0.0, 0.0, 14.0, 0.0, 0.0, 0.0, 0.0])
        normal_score = service.predict(normal_features)

        # Anomalous values far from training distribution
        anomaly_features = np.array([100000.0, 5.0, 3.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 1.0])
        anomaly_score = service.predict(anomaly_features)

        # Normal should score lower than the anomaly
        assert normal_score < anomaly_score

    def test_predict_without_loading_returns_zero(self, mock_model_path):
        """Predict should return 0 if model hasn't been loaded."""
        service = MLModelService(model_path=mock_model_path)
        # load_model not called
        features = np.array([100.0, 0.0, 0.0, 0.0, 0.0, 14.0, 0.0, 0.0, 0.0, 0.0])
        score = service.predict(features)
        assert score == 0.0


class TestMLModelAvailability:
    """Model availability checks."""

    def test_is_available_true_after_load(self, mock_model_path):
        """is_available should return True after loading a model."""
        service = MLModelService(model_path=mock_model_path)
        service.load_model()
        assert service.is_available is True

    def test_is_available_false_before_load(self, mock_model_path):
        """is_available should return False before loading a model."""
        service = MLModelService(model_path=mock_model_path)
        assert service.is_available is False

    def test_is_available_false_no_model(self):
        """is_available should return False when no model file exists."""
        service = MLModelService(model_path="/nonexistent/path.joblib")
        service.load_model()
        assert service.is_available is False


class TestMLModelMissingModel:
    """Graceful handling when model file is missing."""

    def test_load_missing_model_returns_false(self):
        """load_model should return False when model file doesn't exist."""
        service = MLModelService(model_path="/nonexistent/model.joblib")
        result = service.load_model()
        assert result is False

    def test_predict_with_missing_model_returns_zero(self):
        """predict should return 0 when model is unavailable."""
        service = MLModelService(model_path="/nonexistent/model.joblib")
        service.load_model()
        features = np.array([100.0, 0.0, 0.0, 0.0, 0.0, 14.0, 0.0, 0.0, 0.0, 0.0])
        score = service.predict(features)
        assert score == 0.0


class TestMLModelScoreRange:
    """Score normalization — the model must always return 0-100."""

    def test_score_capped_at_100(self, mock_model_path):
        """Score should not exceed 100 even for extreme anomalies."""
        service = MLModelService(model_path=mock_model_path)
        service.load_model()

        # Extreme values
        features = np.array([1e9, 100.0, 100.0, 100.0, 100.0, 3.0, 0.0, 0.0, 0.0, 1.0])
        score = service.predict(features)
        assert score <= 100.0

    def test_score_floor_at_0(self, mock_model_path):
        """Score should not go below 0."""
        service = MLModelService(model_path=mock_model_path)
        service.load_model()

        features = np.array([50.0, 0.0, 0.0, 0.0, 0.0, 14.0, 0.0, 1.0, 1.0, 0.0])
        score = service.predict(features)
        assert score >= 0.0
