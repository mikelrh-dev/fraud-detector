"""Monitoring endpoints for fraud detection system health.

Includes data drift detection, model performance metrics, and system status.
"""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.rate_limit import check_rate_limit
from src.api.v1.transactions import _current_user_uuid, _is_admin
from src.core.dependencies import (
    get_current_user,
    get_db,
    require_any_role,
    require_role,
)
from src.models.fraud_alert import AlertStatus, FraudAlert
from src.models.fraud_score import FraudScore
from src.models.ml_model_run import MLModelRun
from src.models.transaction import Transaction, TransactionStatus
from src.schemas.monitoring import DashboardMetricsResponse
from src.services.drift_service import DataDriftService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/monitoring",
    tags=["monitoring"],
    dependencies=[Depends(check_rate_limit)],
)

# Initialize drift service (will be seeded with reference data on first use)
_drift_service = DataDriftService()

#: Smallest reference the drift monitor will accept (DRIFT-002).
#:
#: ``DataDriftService._compute_psi`` bins on 10 quantiles. Ten bins over a
#: handful of points is not a distribution comparison, it is a coin flip, and
#: the reference is then immortal: the module-level singleton above keeps it
#: for the process lifetime and ``save_reference_to_db`` writes it to a table
#: that every later call re-reads. A reference seeded from a demo dataset
#: therefore becomes a permanent source of false negatives and false
#: positives, with nothing to invalidate it.
#:
#: Measured on this repository's own database (11 fraud scores, from
#: ``seed_demo_data.py``), the old path took all 11 rows as the reference and
#: left an EMPTY current window, so the first call could never compare
#: anything. Later calls, given real traffic, produced PSI 0.09-0.11 against
#: a 0.25 threshold on those 11 points — the same number a genuinely stable
#: system produces, for no reason.
#:
#: 200 rows is 20 per bin. It is a floor, not a comfort: 10-bin PSI on 200
#: points is still noisy, and the honest fix for a production deployment is
#: to seed the reference from a known-good labelled window rather than from
#: live traffic. What this constant buys is that the monitor refuses to
#: pretend it has a baseline, instead of reporting confident nonsense.
MIN_DRIFT_REFERENCE_ROWS = 200


class DriftResponse(dict):
    """Response model for drift detection endpoint."""

    drift_detected: bool
    features_drifted: list[str]
    drift_share: float
    message: str | None = None


def _model_fingerprint() -> str:
    """Short identity of the loaded model artifact, or "unknown".

    The drift reference is a distribution of scores *produced by a model*, so
    a reference is only meaningful for the model that produced it. Nothing in
    the table records that, which is why the question "is the stored reference
    still valid?" could only be answered by remembering.

    Measured cost of getting it wrong: c1a4f6a recalibrated the model, and
    the PSI between the old and new artifact's ``ml_score`` on the *same*
    6,000 rows is 11.46, against a drift threshold of 0.25 — 45x. Two halves
    of one model's own scores give 0.0031, so that 11.46 is the model change
    and not sampling noise. A reference seeded before c1a4f6a would report
    catastrophic drift on completely unchanged traffic.

    Stamped into the free-text ``description`` rather than a new column: a
    migration is not justified for a diagnostic string, and this at least
    makes the invalidity visible to whoever reads the row. The real fix is a
    ``model_sha256`` column the loader can compare against, which is a schema
    change and is left as an open recommendation rather than smuggled in here.
    """
    try:
        import hashlib

        from src.api.v1.transactions import _ml_service

        path = Path(_ml_service._model_path)  # noqa: SLF001 - same package
        if not path.exists():
            return "unknown"
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except Exception as exc:  # noqa: BLE001 - a diagnostic must never raise
        logger.warning("Could not fingerprint the model artifact: %s", exc)
        return "unknown"


def _reference_description(reference_size: int) -> str:
    return (
        f"Auto-initialized from {reference_size} recent scores; "
        f"model_sha256_prefix={_model_fingerprint()}. "
        f"Columns are scores (rule/ml/ensemble/threshold), not model "
        f"features. A reference is valid only for the artifact that produced "
        f"it."
    )


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

    A7: all four aggregates used to run unscoped, guarded only by a valid JWT.
    Any authenticated caller — including a role with no analyst privileges —
    could read every user's totals, blocked counts and average score. The
    listing route in transactions.py already scopes non-admins to their own
    rows (R1-003); this now does the same, and keeps the cross-user view for
    admins, which is the operational purpose of a monitoring dashboard.
    """
    scope_user_id: uuid.UUID | None = None
    if not _is_admin(current_user):
        scope_user_id = _current_user_uuid(current_user)

    try:
        total_query = select(func.count(Transaction.id))
        blocked_query = select(func.count(Transaction.id)).where(
            Transaction.status == TransactionStatus.BLOCKED
        )
        score_query = select(func.avg(FraudScore.ensemble_score))
        alerts_query = select(func.count(FraudAlert.id)).where(
            FraudAlert.status.in_([AlertStatus.OPEN, AlertStatus.REVIEWED])
        )

        if scope_user_id is not None:
            total_query = total_query.where(Transaction.user_id == scope_user_id)
            blocked_query = blocked_query.where(Transaction.user_id == scope_user_id)
            # FraudScore has no user_id of its own: it is reached through the
            # transaction, so the scope is a join rather than a direct filter.
            score_query = score_query.join(
                Transaction, FraudScore.transaction_id == Transaction.id
            ).where(Transaction.user_id == scope_user_id)
            # FraudAlert likewise carries no user_id.
            alerts_query = alerts_query.join(
                Transaction, FraudAlert.transaction_id == Transaction.id
            ).where(Transaction.user_id == scope_user_id)

        total_result = await db.execute(total_query)
        total_transactions = int(total_result.scalar() or 0)

        blocked_result = await db.execute(blocked_query)
        blocked_count = int(blocked_result.scalar() or 0)

        avg_result = await db.execute(score_query)
        avg_score = float(avg_result.scalar() or 0.0)

        alerts_result = await db.execute(alerts_query)
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
        # A7: the window was global, so one analyst's drift view was built from
        # every user's scores. FraudScore has no user_id, so the scope is a join
        # through the transaction. Admins keep the cross-user window, which is
        # what a fleet-wide drift check is for.
        stmt = select(FraudScore).order_by(FraudScore.created_at.desc())

        if not _is_admin(current_user):
            stmt = stmt.join(
                Transaction, FraudScore.transaction_id == Transaction.id
            ).where(Transaction.user_id == _current_user_uuid(current_user))

        result = await db.execute(stmt.limit(window_size))
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
            # Try to load from DB first
            loaded = await _drift_service.load_reference_from_db()
            if not loaded:
                # Fall back to using first half as reference
                reference_size = max(len(recent_scores) // 2, 50)
                # DRIFT-002: refuse to persist a baseline too small to compare
                # against. See MIN_DRIFT_REFERENCE_ROWS for the measurement.
                # Note `max(..., 50)` above is already larger than the rows
                # this database has, so the old path took *every* score as
                # the reference and left nothing to compare it to.
                if reference_size < MIN_DRIFT_REFERENCE_ROWS:
                    logger.error(
                        "Refusing to seed a drift reference from %d rows "
                        "(minimum %d). %d scores are available; a 10-quantile "
                        "PSI over that many points is not a distribution "
                        "comparison, and persisting it would make it "
                        "permanent.",
                        reference_size, MIN_DRIFT_REFERENCE_ROWS,
                        len(recent_scores),
                    )
                    return {
                        "drift_detected": False,
                        "features_drifted": [],
                        "drift_share": 0.0,
                        "report": {},
                        "recent_transactions_count": len(current_data),
                        "reference_transactions_count": 0,
                        "message": (
                            f"No drift reference: only {len(recent_scores)} "
                            f"recent scores, and a reference needs at least "
                            f"{MIN_DRIFT_REFERENCE_ROWS} to support a "
                            f"10-quantile PSI. Re-run with a larger "
                            f"window_size, or seed a reference from a known "
                            f"good period."
                        ),
                    }
                reference_data = current_data.iloc[:reference_size]
                _drift_service.set_reference_data(reference_data)
                await _drift_service.save_reference_to_db(
                    reference_data,
                    description=_reference_description(reference_size),
                )
                current_data = current_data.iloc[reference_size:]
                logger.info(
                    "Initialized drift service with %d reference transactions",
                    reference_size,
                )

        # Evaluate drift without blocking the event loop. The PSI is computed
        # with numpy here, not by Evidently: that package had no import
        # anywhere in the project and was only ever pinning the scikit-learn
        # resolver, which is what broke collection in CI.
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

    except Exception:
        logger.error("Failed to evaluate drift status", exc_info=True)
        return {
            "drift_detected": False,
            "features_drifted": [],
            "drift_share": 0.0,
            "error": "Failed to evaluate drift",
            "message": "Failed to evaluate drift",
        }


@router.get(
    "/metrics",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def get_model_metrics(
    limit: int = Query(20, ge=1, le=100, description="Max runs to return"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_any_role("analyst", "admin")),
) -> dict[str, Any]:
    """Recent ML model training/evaluation runs (R3-002)."""
    result = await db.execute(
        select(MLModelRun).order_by(MLModelRun.created_at.desc()).limit(limit)
    )
    runs = [
        {
            "id": str(run.id),
            "model_version": run.model_version,
            "metrics": run.metrics,
            "status": run.status.value if hasattr(run.status, "value") else run.status,
            "drift_detected": run.drift_detected,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }
        for run in result.scalars().all()
    ]
    return {"runs": runs}


@router.post(
    "/reference-data",
    status_code=status.HTTP_200_OK,
)
async def set_reference_data(
    payload: dict[str, Any],
    current_user: dict = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Upload drift-reference data (admin-only, R3-002).

    Accepts ``{"data": [float, ...]}`` (flat samples) or
    ``{"data": [[...], [...]]}`` (rows). Stored in-memory as the drift
    baseline used by GET /monitoring/drift.
    """
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'data' must be a non-empty list",
        )

    if isinstance(data[0], list):
        columns = payload.get("columns") or [
            f"feature_{i}" for i in range(len(data[0]))
        ]
        reference = pd.DataFrame(data, columns=columns)
    else:
        reference = pd.DataFrame({"value": data})

    _drift_service.set_reference_data(reference)
    logger.info(
        "Reference data updated by %s: %d samples", current_user["user_id"], len(data)
    )
    return {"status": "ok", "samples": len(data)}
