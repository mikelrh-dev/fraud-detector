"""Monitoring endpoints — drift reports, model metrics, dashboard, reference data."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db, require_role
from src.models.fraud_alert import FraudAlert, AlertStatus
from src.models.fraud_score import FraudScore
from src.models.ml_model_run import MLModelRun
from src.models.transaction import Transaction
from src.schemas.monitoring import (
    DashboardMetricsResponse,
    DriftReportResponse,
    FeatureDriftResponse,
    ModelRunResponse,
    PredictionDriftResponse,
    ReferenceDataRequest,
)
from src.services.monitoring import MonitoringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

_monitoring_service = MonitoringService()

# In-memory reference data for drift comparison (v1)
_reference_data: list[float] = []


@router.get("/drift", response_model=DriftReportResponse)
async def get_drift_report(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> DriftReportResponse:
    """Get the current drift report comparing recent scores to reference data.

    If no reference data is configured, compares the last 100 scores against
    the 100 before them as a self-reference baseline.
    """
    global _reference_data

    # Get recent scores
    result = await db.execute(
        select(FraudScore.ensemble_score)
        .order_by(FraudScore.created_at.desc())
        .limit(200)
    )
    all_scores = [float(r[0]) for r in result.all()]

    if not all_scores:
        return DriftReportResponse(
            drift_detected=False,
            drift_score=0.0,
            feature_drifts=[],
            evaluated_at=datetime.now(tz=timezone.utc),
        )

    if _reference_data:
        reference = _reference_data
        current = all_scores[: min(100, len(all_scores))]
    elif len(all_scores) >= 100:
        mid = len(all_scores) // 2
        reference = all_scores[mid:]
        current = all_scores[:mid]
    else:
        reference = all_scores
        current = all_scores

    report = _monitoring_service.compute_drift(reference, current)

    feature_drifts = [
        FeatureDriftResponse(**fd) for fd in report.get("feature_drift", [])
    ]
    pred_drift = report.get("prediction_drift", {})
    prediction_drift = PredictionDriftResponse(**pred_drift) if pred_drift else None

    return DriftReportResponse(
        model_version="latest",
        drift_detected=report["drift_detected"],
        drift_score=report["drift_score"],
        feature_drifts=feature_drifts,
        prediction_drift=prediction_drift,
        evaluated_at=datetime.now(tz=timezone.utc),
    )


@router.get("/metrics")
async def get_model_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get the latest model runs with performance metrics."""
    result = await db.execute(
        select(MLModelRun)
        .order_by(MLModelRun.created_at.desc())
        .limit(20)
    )
    runs = list(result.scalars().all())

    return {
        "runs": [
            ModelRunResponse(
                id=str(r.id),
                model_version=r.model_version,
                metrics=r.metrics,
                drift_detected=r.drift_detected,
                status=r.status.value if hasattr(r.status, "value") else r.status,
                created_at=r.created_at,
            )
            for r in runs
        ],
        "total": len(runs),
    }


@router.get("/dashboard", response_model=DashboardMetricsResponse)
async def get_dashboard_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> DashboardMetricsResponse:
    """Get summary dashboard metrics."""
    # Total transactions
    total_result = await db.execute(
        select(func.count(Transaction.id)).where(Transaction.deleted_at.is_(None))
    )
    total_transactions = total_result.scalar() or 0

    # Fraud transactions
    fraud_result = await db.execute(
        select(func.count(Transaction.id)).where(
            Transaction.status == "blocked",
            Transaction.deleted_at.is_(None),
        )
    )
    fraud_count = fraud_result.scalar() or 0
    fraud_pct = (fraud_count / total_transactions * 100) if total_transactions > 0 else 0.0

    # Average score
    avg_result = await db.execute(
        select(func.avg(FraudScore.ensemble_score))
    )
    avg_score = float(avg_result.scalar() or 0.0)

    # Active alerts
    alert_result = await db.execute(
        select(func.count(FraudAlert.id)).where(FraudAlert.status == AlertStatus.OPEN)
    )
    active_alerts = alert_result.scalar() or 0

    # Model status
    model_result = await db.execute(
        select(MLModelRun).order_by(MLModelRun.created_at.desc()).limit(1)
    )
    latest_run = model_result.scalar_one_or_none()
    model_status = latest_run.status.value if latest_run else "unknown"

    return DashboardMetricsResponse(
        total_transactions=total_transactions or 0,
        fraud_percentage=round(fraud_pct, 2),
        avg_score=round(avg_score, 2),
        active_alerts=active_alerts or 0,
        model_status=model_status,
    )


@router.post("/reference-data")
async def set_reference_data(
    payload: ReferenceDataRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
) -> dict:
    """Set the reference dataset for drift comparison (admin only).

    Replaces the current reference data with the new dataset.
    """
    global _reference_data
    _reference_data = payload.data
    logger.info(
        "Reference data updated by admin %s: %d values",
        current_user["user_id"],
        len(payload.data),
    )
    return {
        "status": "ok",
        "reference_count": len(payload.data),
        "description": payload.description,
    }
