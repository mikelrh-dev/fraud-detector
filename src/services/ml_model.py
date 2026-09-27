"""ML model service — loads and runs a trained XGBoost classifier.

Provides a consistent scoring interface: load_model() loads a serialized
XGBoost model via joblib, predict() converts predict_proba() output
to a 0-100 risk score. If the model file is missing, returns 0 silently.

The model artifact can be either:
- A bare model object (legacy format) — feature count inferred from the model.
- A dict with keys "model" and "feature_names" (new format with contract stamp).
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
        self.feature_names: list[str] | None = None
        self.n_features: int | None = None

    def load_model(self) -> bool:
        """Load the serialized model from disk.

        Handles two artifact formats:
        - Dict with "model" and optionally "feature_names" keys (new format).
        - Bare model object (legacy/backward-compatible format).

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
            artifact = joblib.load(path)

            # New format: dict with "model" and optional "feature_names"
            if isinstance(artifact, dict) and "model" in artifact:
                self._model = artifact["model"]
                self.feature_names = artifact.get("feature_names")
            else:
                # Legacy format: bare model object
                self._model = artifact
                self.feature_names = None

            # Infer n_features from the model
            if self._model is not None and hasattr(self._model, "n_features_in_"):
                self.n_features = int(self._model.n_features_in_)
            elif self.feature_names is not None:
                self.n_features = len(self.feature_names)

            logger.info(
                "ML model loaded from %s (features=%s)",
                self._model_path,
                self.n_features,
            )
            return True
        except Exception as exc:
            logger.error("Failed to load ML model from %s: %s", self._model_path, exc)
            return False

    def predict(self, features: np.ndarray) -> float:
        """Score a feature vector using the loaded XGBoost model.

        Uses predict_proba() and returns the probability of fraud (class 1)
        scaled to 0-100. If no model is loaded, returns 0.0.

        Applies an explicit shape check: if the feature vector dimension
        doesn't match the expected count, raises ValueError instead of
        silently returning 0.

        Applies smoothing to synthetic data predictions to simulate real-world
        uncertainty and avoid binary extremes (0 or 100).

        Args:
            features: NumPy array of shape (n_features,) containing the feature vector.

        Returns:
            Risk score between 0 (normal) and 100 (highly anomalous).

        Raises:
            ValueError: If feature vector dimension doesn't match expected count.
        """
        if self._model is None:
            return 0.0

        # Explicit shape check — don't silently return 0 on mismatch
        if self.n_features is not None and features.shape[0] != self.n_features:
            raise ValueError(
                f"Feature shape mismatch: got {features.shape[0]}, "
                f"expected {self.n_features}"
            )

        # XGBoost.predict_proba returns [P(legit), P(fraud)]
        probability = self._model.predict_proba([features])[0, 1]

        # Scale probability [0, 1] to risk score [0, 100] directly.
        # The model's calibrated probability is the fraud risk score.
        return float(probability * 100.0)

    @property
    def is_available(self) -> bool:
        """Check if the model is loaded and ready for predictions."""
        return self._model is not None
