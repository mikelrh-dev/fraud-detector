"""ML model tests — scoring with serialized XGBoost model, missing model,
score range 0-100, probability normalization.
"""

import os
import tempfile

import joblib
import numpy as np
import pytest
import xgboost as xgb

from src.services.ml_model import MLModelService


@pytest.fixture(scope="module")
def mock_model_path():
    """Create a temporary XGBoost model for testing.

    Trains a tiny XGBClassifier on synthetic 10-feature data so that
    predict() can return meaningful scores in [0, 100].
    """
    rng = np.random.RandomState(42)
    # Class 0 — low values around 50
    X0 = rng.normal(loc=50, scale=10, size=(50, 10))
    # Class 1 — high values around 500
    X1 = rng.normal(loc=500, scale=100, size=(50, 10))
    X = np.vstack([X0, X1])
    y = np.array([0] * 50 + [1] * 50)

    model = xgb.XGBClassifier(
        n_estimators=20,
        max_depth=3,
        random_state=42,
        use_label_encoder=False,
    )
    model.fit(X, y)

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

    def test_high_value_gets_higher_score(self, mock_model_path):
        """A feature vector near class 1 should score higher than one near class 0."""
        service = MLModelService(model_path=mock_model_path)
        service.load_model()

        # Values near class 0 (mean ~50)
        low_features = np.array([50.0, 0.0, 0.0, 0.0, 0.0, 14.0, 0.0, 0.0, 0.0, 0.0])
        low_score = service.predict(low_features)

        # Values near class 1 (mean ~500)
        high_features = np.array([500.0, 5.0, 3.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 1.0])
        high_score = service.predict(high_features)

        assert low_score < high_score

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
        """Score should not exceed 100."""
        service = MLModelService(model_path=mock_model_path)
        service.load_model()

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
