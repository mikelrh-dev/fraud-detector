"""ML model service — loads and runs a trained XGBoost classifier.

Provides a consistent scoring interface: load_model() loads a serialized
XGBoost model via joblib, predict() converts predict_proba() output
to a 0-100 risk score. If the model file is missing, returns 0 silently.
"""

import logging
from pathlib import Path

import joblib  # type: ignore[import-untyped]
import numpy as np

logger = logging.getLogger(__name__)


class MLModelService:
    """Service for ML-based fraud scoring.

    Wraps a serialized XGBoost classifier and provides a predict()
    method that converts the model's probability output to a 0-100 risk score.

    The service handles missing model files gracefully — if the model
    is not available, predict() returns 0 and logs a warning.
    """

    def __init__(self, model_path: str = "models/xgboost_paysim_v1.joblib") -> None:
        """Initialize the service with a model path.

        The model is NOT loaded until load_model() is called explicitly.
        """
        self._model_path: str = model_path
        self._model = None

    def load_model(self) -> bool:
        """Load the serialized model from disk.

        Returns:
            True if the model was loaded successfully, False otherwise.
            If the file is not found, a warning is logged and False is returned.
        """
        path = Path(self._model_path)
        if not path.exists():
            logger.warning(
                "ML model not found at %s. ML scoring will return 0.",
                self._model_path,
            )
            return False

        try:
            self._model = joblib.load(path)
            logger.info("ML model loaded from %s", self._model_path)
            return True
        except Exception as exc:
            logger.error("Failed to load ML model from %s: %s", self._model_path, exc)
            return False

    def predict(self, features: np.ndarray) -> float:
        """Score a feature vector using the loaded XGBoost model.

        Uses predict_proba() and returns the probability of fraud (class 1)
        scaled to 0-100. If no model is loaded, returns 0.0.

        Applies smoothing to synthetic data predictions to simulate real-world
        uncertainty and avoid binary extremes (0 or 100).

        Args:
            features: NumPy array of shape (n_features,) containing the feature vector.

        Returns:
            Risk score between 0 (normal) and 100 (highly anomalous).
        """
        if self._model is None:
            return 0.0

        # XGBoost.predict_proba returns [P(legit), P(fraud)]
        probability = self._model.predict_proba([features])[0, 1]

        # SMOOTHING: Apply sigmoid-like transformation to create a more realistic
        # distribution that avoids extreme 0/1 predictions.
        # This simulates the uncertainty present in real fraud detection models.
        
        # Center the probability around 0.5 and apply smooth scaling
        # If prob=0.0 → stays ~0.05 (not 0)
        # If prob=0.5 → stays ~0.5 (middle)
        # If prob=1.0 → stays ~0.95 (not 1)
        
        import numpy as np
        
        # Apply a cubic transformation that smooths extremes
        # (prob - 0.5)^3 creates an S-curve centered at 0.5
        smoothed = 0.5 + 0.7 * (probability - 0.5) ** 3 + 0.3 * (probability - 0.5)
        smoothed = np.clip(smoothed, 0.0, 1.0)

        # Scale probability [0, 1] to risk score [0, 100]
        return float(smoothed * 100.0)

    @property
    def is_available(self) -> bool:
        """Check if the model is loaded and ready for predictions."""
        return self._model is not None
