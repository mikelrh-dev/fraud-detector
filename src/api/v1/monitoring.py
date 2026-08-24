"""Monitoring endpoints for fraud detection system health.

Includes data drift detection, model performance metrics, and system status.
"""

import asyncio
import logging
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db
from src.models.fraud_alert import AlertStatus, FraudAlert
from src.models.fraud_score import FraudScore
from src.models.transaction import Transaction, TransactionStatus
from src.schemas.monitoring import DashboardMetricsResponse
from src.services.drift_service import DataDriftService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/monitoring",
    tags=["monitoring"],
)

# Initialize drift service (will be seeded with reference data on first use)
_drift_service = DataDriftService()


class DriftResponse(dict):
    """Response model for drift detection endpoint."""

    drift_detected: bool
    features_drifted: list[str]
    drift_share: float
    message: str | None = None


@router.get(
    "/dashboard",
    response_model=DashboardMetricsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_dashboard_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> DashboardMetricsResponse:
    """Aggregate metrics for the monitoring dashboard.

    Returns total transaction count, fraud percentage (blocked transactions),
    average ensemble score across scored transactions, and open/reviewed alert count.
    """
    try:
        total_result = await db.execute(select(func.count(Transaction.id)))
        total_transactions = int(total_result.scalar() or 0)

        blocked_result = await db.execute(
            select(func.count(Transaction.id)).where(
                Transaction.status == TransactionStatus.BLOCKED
            )
        )
        blocked_count = int(blocked_result.scalar() or 0)

        avg_result = await db.execute(select(func.avg(FraudScore.ensemble_score)))
        avg_score = float(avg_result.scalar() or 0.0)

        alerts_result = await db.execute(
            select(func.count(FraudAlert.id)).where(
                FraudAlert.status.in_([AlertStatus.OPEN, AlertStatus.REVIEWED])
            )
        )
        active_alerts = int(alerts_result.scalar() or 0)

        return DashboardMetricsResponse(
            total_transactions=total_transactions,
            fraud_percentage=(blocked_count / total_transactions * 100.0)
            if total_transactions > 0
            else 0.0,
            avg_score=avg_score,
            active_alerts=active_alerts,
            model_status="operational",
        )
    except Exception as exc:
        logger.exception("Failed to compute dashboard metrics: %s", exc)
        raise


@router.get(
    "/drift",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def get_drift_status(
    window_size: int = Query(
        100, ge=10, le=1000, description="Number of recent transactions to evaluate"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Check for data drift in recent transactions.

    Compares the distribution of recent transactions against a reference baseline.
    High drift indicates that fraud patterns may have changed and the model
    should be retrained.

    Args:
        window_size: Number of recent transactions to evaluate (default: 100)
        db: Database session
        current_user: Authenticated user

    Returns:
        Dict with drift analysis results:
        - drift_detected: bool
        - features_drifted: list of feature names with detected drift
        - drift_share: proportion of features affected (0-1)
        - recent_transactions_count: number of transactions evaluated
        - reference_transactions_count: number of reference transactions
    """
    try:
        # Get recent transactions with scores
        stmt = (
            select(FraudScore).order_by(FraudScore.created_at.desc()).limit(window_size)
        )
        result = await db.execute(stmt)
        recent_scores = result.scalars().all()

        if len(recent_scores) < 10:
            return {
                "drift_detected": False,
                "features_drifted": [],
                "drift_share": 0.0,
                "recent_transactions_count": len(recent_scores),
                "reference_transactions_count": 0,
                "message": f"Insufficient data: only {len(recent_scores)} recent transactions",
            }

        # Build DataFrame from recent scores
        current_data = pd.DataFrame(
            {
                "rule_score": [float(s.rule_score) for s in recent_scores],
                "ml_score": [float(s.ml_score) for s in recent_scores],
                "ensemble_score": [float(s.ensemble_score) for s in recent_scores],
                "threshold": [float(s.threshold) for s in recent_scores],
            }
        )

        # If drift service not seeded yet, use first half as reference
        if not _drift_service.is_initialized:
            reference_size = max(len(recent_scores) // 2, 50)
            reference_data = current_data.iloc[:reference_size]
            _drift_service.set_reference_data(reference_data)
            current_data = current_data.iloc[reference_size:]
            logger.info(
                "Initialized drift service with %d reference transactions",
                reference_size,
            )

        # Evaluate drift using ThreadPoolExecutor to avoid blocking event loop
        # Evidently calculations are CPU-bound (500ms-2s), must run in thread
        drift_result = await asyncio.to_thread(
            _drift_service.evaluate_drift,
            current_data,
        )

        return {
            **drift_result,
            "recent_transactions_count": len(current_data),
            "reference_transactions_count": len(_drift_service.reference_data)
            if _drift_service.reference_data is not None
            else 0,
        }

    except Exception as exc:
        logger.error("Failed to evaluate drift status: %s", exc)
        return {
            "drift_detected": False,
            "features_drifted": [],
            "drift_share": 0.0,
            "error": str(exc),
            "message": "Failed to evaluate drift",
        }
