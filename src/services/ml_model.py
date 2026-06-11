"""ML model service — loads and runs IsolationForest for anomaly detection.

Provides a consistent scoring interface: load_model() loads a serialized
IsolationForest via joblib, predict() converts the anomaly score (-1/1)
to a 0-100 risk score. If the model file is missing, returns 0 silently.
"""

import logging
from pathlib import Path

import joblib  # type: ignore[import-untyped]
import numpy as np
from sklearn.ensemble import IsolationForest  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class MLModelService:
    """Service for ML-based anomaly detection scoring.

    Wraps a serialized IsolationForest model and provides a predict()
    method that normalizes the raw model output to a 0-100 risk score.

    The service handles missing model files gracefully — if the model
    is not available, predict() returns 0 and logs a warning.
    """

    def __init__(self, model_path: str = "models/isolation_forest_v1.joblib") -> None:
        """Initialize the service with a model path.

        The model is NOT loaded until load_model() is called explicitly.
        """
        self._model_path: str = model_path
        self._model: IsolationForest | None = None

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
        """Score a feature vector using the loaded model.

        Converts the IsolationForest output:
            - Internal anomaly score (lower = more anomalous) is inverted
              and normalized to 0-100.
            - If no model is loaded, returns 0.0.

        Args:
            features: NumPy array of shape (10,) containing the feature vector.

        Returns:
            Risk score between 0 (normal) and 100 (highly anomalous).
        """
        if self._model is None:
            return 0.0

        # IsolationForest.decision_function returns lower scores for anomalies
        raw_score = self._model.decision_function([features])[0]

        # Normalize: raw_score range is typically [-0.5, 0.5] for contamination=0.1
        # We map: raw_score → ml_score where lower raw = higher risk
        # Normalize to 0-100 using a sigmoid-like mapping
        # raw_score > 0 → normal (low risk), raw_score < 0 → anomaly (high risk)
        normalized = 100.0 * (1.0 - (raw_score + 0.5))
        normalized = max(0.0, min(100.0, normalized))
        return normalized

    @property
    def is_available(self) -> bool:
        """Check if the model is loaded and ready for predictions."""
        return self._model is not None
