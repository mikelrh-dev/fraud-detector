"""Monitoring service — drift detection, performance metrics, retraining triggers.

Provides model monitoring capabilities:
- Data drift detection by comparing reference vs current distributions
- Prediction drift quantification
- Performance metric computation (precision, recall, F1, AUC-ROC)
- Retraining trigger evaluation
"""

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sklearn.metrics import (  # type: ignore[import-untyped]
    precision_recall_fscore_support,
    roc_auc_score,
)

from src.models.ml_model_run import MLModelRun, MLModelStatus

logger = logging.getLogger(__name__)


class MonitoringService:
    """Monitors model performance, data drift, and retraining conditions.

    Computes drift between reference and current data distributions, tracks
    model performance metrics, and evaluates whether retraining is needed.
    """

    DRIFT_THRESHOLD = 30.0

    def compute_drift(
        self,
        reference_data: list[float],
        current_data: list[float],
    ) -> dict[str, Any]:
        """Compare reference vs current data distributions for drift.

        Uses population stability index (PSI) to quantify distribution shift.
        Returns a report with per-feature drift, overall drift score,
        and drift_detected flag.

        Args:
            reference_data: Historical data as a flat list of values.
            current_data: Recent data as a flat list of values.

        Returns:
            Dict with keys: feature_drift (list), prediction_drift (dict),
            drift_detected (bool), drift_score (float 0-100).
        """
        if not reference_data or not current_data:
            return {
                "feature_drift": [],
                "prediction_drift": {
                    "reference_mean": 0.0,
                    "current_mean": 0.0,
                    "shift": 0.0,
                },
                "drift_detected": False,
                "drift_score": 0.0,
            }

        ref = np.array(reference_data, dtype=float)
        cur = np.array(current_data, dtype=float)

        ref_mean = float(np.mean(ref))
        cur_mean = float(np.mean(cur))

        # PSI-based feature drift score (simplified for testing)
        # Compute by binning data into 10 bins and measuring distribution shift
        psi = self._compute_psi(ref, cur)

        # Overall drift score 0-100
        drift_score = min(float(psi * 10), 100.0)

        # Feature-level drift (simulated for v1)
        feature_drift = []
        if drift_score > self.DRIFT_THRESHOLD:
            feature_drift.append({
                "feature": "value",
                "psi": round(psi, 4),
                "reference_mean": round(ref_mean, 4),
                "current_mean": round(cur_mean, 4),
            })

        return {
            "feature_drift": feature_drift,
            "prediction_drift": {
                "reference_mean": round(ref_mean, 4),
                "current_mean": round(cur_mean, 4),
                "shift": round(cur_mean - ref_mean, 4),
            },
            "drift_detected": drift_score > self.DRIFT_THRESHOLD,
            "drift_score": round(drift_score, 2),
        }

    def _compute_psi(self, reference: np.ndarray, current: np.ndarray) -> float:
        """Compute population stability index between two distributions.

        PSI = sum((P_i - Q_i) * ln(P_i / Q_i)) for each bin i.
        A PSI < 0.1 = no significant shift, 0.1-0.25 = moderate, > 0.25 = significant.
        """
        all_vals = np.concatenate([reference, current])
        if np.all(all_vals == all_vals[0]):
            return 0.0

        bins = np.histogram_bin_edges(all_vals, bins=10)
        ref_hist, _ = np.histogram(reference, bins=bins)
        cur_hist, _ = np.histogram(current, bins=bins)

        # Convert to proportions, add small epsilon to avoid log(0)
        ref_pct = ref_hist / (len(reference) or 1) + 1e-10
        cur_pct = cur_hist / (len(current) or 1) + 1e-10

        psi = float(np.sum((ref_pct - cur_pct) * np.log(ref_pct / cur_pct)))
        return psi

    def compute_metrics(
        self,
        predictions: np.ndarray,
        actuals: np.ndarray,
    ) -> dict[str, Any]:
        """Compute classification performance metrics.

        Args:
            predictions: Model prediction array (binary: 0/1).
            actuals: Ground truth labels array (binary: 0/1).

        Returns:
            Dict with precision, recall, f1, auc_roc, and timestamp.
        """
        if len(predictions) == 0 or len(actuals) == 0:
            return {
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "auc_roc": 0.0,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }

        precision, recall, f1, _ = precision_recall_fscore_support(
            actuals, predictions, average="binary", zero_division=0,
        )

        try:
            auc_roc = float(roc_auc_score(actuals, predictions))
        except (ValueError, Exception):
            auc_roc = 0.0

        return {
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
            "auc_roc": round(float(auc_roc), 4),
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    async def track_model_run(
        self,
        db: Any,
        model_version: str,
        metrics: dict[str, Any],
        drift_detected: bool,
        _run_instance: Any = None,
    ) -> Any:
        """Persist a model run record with metrics and drift status.

        Args:
            db: Async database session.
            model_version: Version identifier for the model.
            metrics: Dict with performance metrics.
            drift_detected: Whether drift was detected.
            _run_instance: Optional injected instance for testing.

        Returns:
            The created MLModelRun instance.
        """
        run = _run_instance or MLModelRun(
            model_version=model_version,
            metrics=metrics,
            status=MLModelStatus.READY,
            drift_detected=drift_detected,
        )
        if _run_instance is not None:
            run.drift_detected = drift_detected
        db.add(run)
        await db.flush()
        return run

    def check_retraining_trigger(
        self,
        recent_metrics: dict[str, Any],
    ) -> bool:
        """Evaluate whether model retraining should be triggered.

        Retraining is recommended when:
        - F1 score drops below 0.7, OR
        - Drift score exceeds 30

        Args:
            recent_metrics: Dict with model performance metrics, may include
                'f1' and 'drift_score'.

        Returns:
            True if retraining should be triggered, False otherwise.
        """
        f1 = recent_metrics.get("f1")
        drift_score = recent_metrics.get("drift_score")

        if f1 is not None and f1 < 0.7:
            return True
        if drift_score is not None and drift_score > self.DRIFT_THRESHOLD:
            return True
        return False
