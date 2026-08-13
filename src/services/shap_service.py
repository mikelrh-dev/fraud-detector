"""SHAP feature attribution service.

Computes feature contributions with ``shap.TreeExplainer`` over the
joblib-serialized XGBoost model. ``shap`` is imported lazily (SHP-005):
when shap or the model file is unavailable, ``explain()`` raises
``ShapUnavailableError`` and callers skip computation instead of crashing.

The explainer is a process-wide singleton built lazily under a lock —
init costs 100-500ms, and the worker's BRPOP loop is a single consumer,
so ``asyncio.to_thread`` calls serialize anyway.
"""

import importlib
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np

logger = logging.getLogger(__name__)

TOP_K = 5
DEFAULT_MODEL_PATH = "models/xgboost_paysim_v1.joblib"


class ShapUnavailableError(RuntimeError):
    """Raised when shap or the ML model cannot be loaded (SHP-005).

    Callers treat this as a permanent, environmental failure: skip the
    message, do NOT retry, and keep the loop alive.
    """


@dataclass(frozen=True)
class ShapContribution:
    """A single feature contribution returned by ``explain()``."""

    feature: str
    contribution: float


class ShapService:
    """Lazy, thread-safe wrapper around ``shap.TreeExplainer``.

    The service loads its own model file (same default path as
    MLModelService) instead of reusing ``MLModelService._model`` — the
    worker runs in a separate process and the private attribute is not
    a stable contract.
    """

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH) -> None:
        self._model_path = model_path
        self._explainer: Any = None
        self._lock = threading.Lock()

    def _ensure_ready(self) -> None:
        """Load shap + the model and build the explainer exactly once.

        Thread-safe: concurrent callers block on the lock and only the
        first one performs the (expensive) load.
        """
        with self._lock:
            if self._explainer is not None:
                return

            try:
                shap = importlib.import_module("shap")
            except ImportError as exc:
                logger.warning(
                    "shap is not installed — SHAP attribution disabled: %s",
                    exc,
                )
                raise ShapUnavailableError(
                    "shap is not installed"
                ) from exc

            path = Path(self._model_path)
            if not path.exists():
                logger.warning(
                    "ML model not found at %s — SHAP attribution disabled",
                    self._model_path,
                )
                raise ShapUnavailableError(
                    f"ML model not found at {self._model_path}"
                )

            try:
                model = joblib.load(path)
                self._explainer = shap.TreeExplainer(model)
            except Exception as exc:
                logger.error(
                    "Failed to initialize SHAP explainer from %s: %s",
                    self._model_path,
                    exc,
                )
                raise ShapUnavailableError(
                    f"Failed to initialize SHAP explainer: {exc}"
                ) from exc

    def explain(
        self,
        features: list[float],
        feature_names: list[str] | None = None,
    ) -> list[ShapContribution]:
        """Compute the top-5 feature contributions for one feature vector.

        Args:
            features: The scored feature vector (queue snapshot).
            feature_names: Optional names aligned with the vector; falls
                back to ``feature_{i}`` when absent or length-mismatched.

        Returns:
            Top-5 ``ShapContribution`` entries ordered by absolute
            contribution descending, values signed.

        Raises:
            ShapUnavailableError: when shap or the model file is missing
                (SHP-005 — callers skip, never retry).
        """
        self._ensure_ready()
        values = self._explainer.shap_values(features)
        vector = self._normalize_shap_values(values)
        return self._top_k(vector, feature_names)

    def _normalize_shap_values(self, values: Any) -> list[float]:
        """Reduce ``shap_values`` to a flat (n_features,) fraud-margin vector.

        Binary XGBoost output shape varies across shap versions:
        - list of per-class arrays     -> fraud class index 1
        - 3D (samples, features, classes) -> sample 0, fraud class 1
        - 2D / 1D                      -> already the fraud margin
        """
        if isinstance(values, list):
            vector = values[1]
        else:
            arr = np.asarray(values)
            if arr.ndim == 3:
                vector = arr[0, :, 1]
            else:
                vector = arr
        return [float(x) for x in np.asarray(vector).reshape(-1)]

    def _top_k(
        self,
        vector: list[float],
        feature_names: list[str] | None,
    ) -> list[ShapContribution]:
        if feature_names is not None and len(feature_names) != len(vector):
            logger.warning(
                "feature_names length %d does not match %d SHAP values — "
                "falling back to feature_i",
                len(feature_names),
                len(vector),
            )
            feature_names = None

        ranked = sorted(
            range(len(vector)),
            key=lambda i: abs(vector[i]),
            reverse=True,
        )[:TOP_K]

        return [
            ShapContribution(
                feature=(
                    feature_names[i]
                    if feature_names is not None
                    else f"feature_{i}"
                ),
                contribution=vector[i],
            )
            for i in ranked
        ]

    def model_fingerprint(self) -> str:
        """Return ``"<size>:<mtime>"`` of the model file (no shap import).

        Used to snapshot which model version an attribution refers to.
        Empty string when the file is missing.
        """
        path = Path(self._model_path)
        try:
            stat = path.stat()
        except OSError:
            return ""
        return f"{stat.st_size}:{int(stat.st_mtime)}"
