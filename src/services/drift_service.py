"""Data Drift Detection Service using Evidently AI.

Monitors if the distribution of fraud transaction features drifts from a
reference dataset. If drift is detected, it indicates the model may be
becoming obsolete and needs retraining.

Reference data is persisted to Redis (key ``drift:reference_data``) as
JSON so it survives process restarts. On startup, if the Redis key exists,
the reference baseline is restored automatically.
"""

import json
import logging
from typing import Any

import pandas as pd
from evidently.metric_preset import DataDriftPreset
from evidently.report import Report

logger = logging.getLogger(__name__)

REDIS_DRIFT_KEY = "drift:reference_data"


class DataDriftService:
    """Detects concept drift in fraud detection features using Evidently.
    
    Compares current transaction features against a reference distribution
    to identify if fraud patterns have shifted.
    """

    def __init__(
        self,
        reference_data: pd.DataFrame | None = None,
        redis_client: Any | None = None,
    ):
        """Initialize drift service with optional reference dataset.
        
        Args:
            reference_data: Baseline dataset (e.g., first 500 transactions).
                           If None, will be restored from Redis or set on first use.
            redis_client: Optional async Redis client for persistence.
        """
        self._redis = redis_client
        self.reference_data = reference_data
        self.is_initialized = reference_data is not None

        # Restore from Redis if available and no explicit reference provided
        if not self.is_initialized and self._redis is not None:
            self._restore_from_redis()

    def _restore_from_redis(self) -> None:
        """Load reference data from Redis if available (best-effort)."""
        if self._redis is None:
            return
        try:
            raw = self._redis.get(REDIS_DRIFT_KEY)
            if raw is None:
                return
            if isinstance(raw, bytes):
                raw = raw.decode()
            payload = json.loads(raw)
            columns = payload.get("columns", [])
            data = payload.get("data", [])
            if columns and data:
                self.reference_data = pd.DataFrame(data, columns=columns)
                self.is_initialized = True
                logger.info(
                    "Restored drift reference from Redis: %d rows, %d cols",
                    len(data), len(columns),
                )
        except Exception as exc:
            logger.warning("Failed to restore drift reference from Redis: %s", exc)

    def _persist_to_redis(self) -> None:
        """Save reference data to Redis as JSON (best-effort, fire-and-forget)."""
        if self._redis is None or self.reference_data is None:
            return
        try:
            payload = json.dumps({
                "columns": list(self.reference_data.columns),
                "data": self.reference_data.values.tolist(),
            })
            self._redis.set(REDIS_DRIFT_KEY, payload)
        except Exception as exc:
            logger.warning("Failed to persist drift reference to Redis: %s", exc)

    def set_reference_data(self, data: pd.DataFrame) -> None:
        """Set the reference baseline dataset for drift comparison.
        
        Also persists to Redis for crash recovery.
        
        Args:
            data: DataFrame with features (amount, merchant_category, velocity_5min, etc.)
        """
        self.reference_data = data
        self.is_initialized = True
        self._persist_to_redis()
        logger.info("Reference dataset set: %d rows", len(data))

    def evaluate_drift(self, current_data: pd.DataFrame) -> dict[str, Any]:
        """Evaluate data drift between current and reference data.
        
        Args:
            current_data: DataFrame with current transaction features.
        
        Returns:
            Dict with keys:
                - drift_detected: bool
                - features_drifted: list of feature names with drift
                - drift_share: float (0-1) of features that drifted
                - report: Evidently report dict
        """
        if not self.is_initialized or self.reference_data is None:
            logger.warning("Drift service not initialized with reference data")
            return {
                "drift_detected": False,
                "features_drifted": [],
                "drift_share": 0.0,
                "report": {},
                "message": "Reference data not available",
            }

        if len(current_data) == 0:
            return {
                "drift_detected": False,
                "features_drifted": [],
                "drift_share": 0.0,
                "report": {},
                "message": "No current data to evaluate",
            }

        try:
            # Run Evidently drift detection
            report = Report(metrics=[DataDriftPreset()])
            report.run(
                reference_data=self.reference_data,
                current_data=current_data,
            )

            # Extract drift results
            report_dict = report.as_dict()
            metrics = report_dict.get("metrics", [])

            # Collect drifted features
            drifted_features = []
            for metric in metrics:
                metric_result = metric.get("result", {})
                if metric_result.get("is_drift"):
                    feature_name = metric_result.get("feature_name")
                    if feature_name:
                        drifted_features.append(feature_name)

            drift_share = len(drifted_features) / max(len(self.reference_data.columns), 1)
            drift_detected = len(drifted_features) > 0

            logger.info(
                "Drift evaluation: drift_detected=%s, features_drifted=%s, share=%.2f%%",
                drift_detected,
                drifted_features,
                drift_share * 100,
            )

            return {
                "drift_detected": drift_detected,
                "features_drifted": drifted_features,
                "drift_share": drift_share,
                "report": report_dict,
            }

        except Exception as exc:
            logger.error("Failed to evaluate drift: %s", exc)
            return {
                "drift_detected": False,
                "features_drifted": [],
                "drift_share": 0.0,
                "report": {},
                "error": str(exc),
            }
