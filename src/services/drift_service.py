"""Data Drift Detection Service using PSI (Population Stability Index).

Monitors if the distribution of fraud transaction features drifts from a
reference dataset. If drift is detected, it indicates the model may be
becoming obsolete and needs retraining.

Reference data is persisted to the database so it survives Redis flushes
and service restarts.
"""

import logging
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.drift_reference import DriftReferenceData

logger = logging.getLogger(__name__)


class DataDriftService:
    """Detects concept drift in fraud detection features.

    The drift metric is a Population Stability Index computed with numpy
    against a reference window. This class does not use Evidently: that
    package had no import anywhere in the project and was removed from
    requirements.txt, having only constrained the scikit-learn resolver.

    Compares current transaction features against a reference distribution
    to identify if fraud patterns have shifted.
    
    Reference data is persisted to the database for durability.
    """
    
    def __init__(
        self,
        reference_data: pd.DataFrame | None = None,
        db: AsyncSession | None = None,
    ):
        """Initialize drift service with optional reference dataset.
        
        Args:
            reference_data: Baseline dataset (e.g., first 500 transactions).
                           If None, will be loaded from the database or set on first use.
            db: Optional async database session for persistence.
        """
        self._db = db
        self.reference_data = reference_data
        self.is_initialized = reference_data is not None

    async def load_reference_from_db(self) -> bool:
        """Load reference data from the database if available.
        
        Returns:
            True if reference data was loaded, False otherwise.
        """
        if self._db is None or self.is_initialized:
            return False
        try:
            result = await self._db.execute(
                select(DriftReferenceData).order_by(DriftReferenceData.created_at.desc()).limit(1)
            )
            record = result.scalar_one_or_none()
            if record is None:
                return False
            self.reference_data = pd.DataFrame(record.data, columns=record.columns)
            self.is_initialized = True
            logger.info(
                "Loaded drift reference from DB: %d rows, %d cols",
                len(record.data), len(record.columns),
            )
            return True
        except Exception as exc:
            logger.warning("Failed to load drift reference from DB: %s", exc)
            return False

    async def save_reference_to_db(
        self,
        data: pd.DataFrame,
        description: str | None = None,
    ) -> None:
        """Save reference data to the database.
        
        Args:
            data: DataFrame with features (amount, merchant_category, velocity_5min, etc.)
            description: Optional description of the reference dataset.
        """
        if self._db is None:
            return
        try:
            record = DriftReferenceData(
                columns=list(data.columns),
                data=data.values.tolist(),
                description=description,
                version="v1",
            )
            self._db.add(record)
            await self._db.flush()
            logger.info("Saved drift reference to DB: %d rows", len(data))
        except Exception as exc:
            logger.warning("Failed to save drift reference to DB: %s", exc)

    def set_reference_data(self, data: pd.DataFrame, description: str | None = None) -> None:
        """Set the reference baseline dataset for drift comparison.
        
        Args:
            data: DataFrame with features (amount, merchant_category, velocity_5min, etc.)
            description: Optional description of the reference dataset.
        """
        self.reference_data = data
        self.is_initialized = True
        logger.info("Reference dataset set: %d rows", len(data))

    def _compute_psi(self, reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
        """Compute Population Stability Index between two distributions.

        PSI = sum((P_i - Q_i) * ln(P_i / Q_i)) for each bin i.
        A PSI < 0.1 = no significant shift, 0.1-0.25 = moderate, > 0.25 = significant.
        """
        all_vals = np.concatenate([reference, current])
        if np.all(all_vals == all_vals[0]):
            return 0.0

        edges = np.unique(np.quantile(all_vals, np.linspace(0, 1, bins + 1)))
        edges[0], edges[-1] = -np.inf, np.inf
        ref_pct = np.histogram(reference, bins=edges)[0] / len(reference)
        cur_pct = np.histogram(current, bins=edges)[0] / len(current)
        eps = 1e-6
        return float(np.sum((cur_pct - ref_pct) * np.log((cur_pct + eps) / (ref_pct + eps))))

    def evaluate_drift(self, current_data: pd.DataFrame) -> dict[str, Any]:
        """Evaluate data drift between current and reference data using PSI.

        Args:
            current_data: DataFrame with current transaction features.

        Returns:
            Dict with keys:
                - drift_detected: bool
                - features_drifted: list of feature names with drift
                - drift_share: float (0-1) of features that drifted
                - report: dict with per-feature PSI values
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
            # Compute PSI for each feature
            drifted_features = []
            psi_values = {}

            for col in self.reference_data.columns:
                if col not in current_data.columns:
                    continue
                ref_vals = self.reference_data[col].dropna().values
                cur_vals = current_data[col].dropna().values
                if len(ref_vals) == 0 or len(cur_vals) == 0:
                    continue
                psi = self._compute_psi(ref_vals, cur_vals)
                psi_values[col] = round(psi, 4)
                if psi > 0.25:
                    drifted_features.append(col)

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
                "report": {"psi_values": psi_values},
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
