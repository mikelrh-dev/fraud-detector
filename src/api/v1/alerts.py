"""Alert endpoints — list alerts, review, false-positive, revert actions."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.rate_limit import check_rate_limit
from src.core.dependencies import get_current_user, get_db
from src.models.fraud_alert import AlertStatus, FraudAlert
from src.schemas.alert import AlertActionRequest, AlertListResponse, AlertResponse
from src.services.audit import AuditService

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(check_rate_limit)],
)

_audit_service = AuditService()


@router.get("", response_model=AlertListResponse)
async def list_alerts_endpoint(
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AlertListResponse:
    """List fraud alerts with optional filters."""
    skip = (page - 1) * page_size

    query = select(FraudAlert)

    if status_filter:
        query = query.where(FraudAlert.status == status_filter)
    if date_from:
        query = query.where(FraudAlert.created_at >= date_from)
    if date_to:
        query = query.where(FraudAlert.created_at <= date_to)

    count_query = select(FraudAlert.id)
    if status_filter:
        count_query = count_query.where(FraudAlert.status == status_filter)
    if date_from:
        count_query = count_query.where(FraudAlert.created_at >= date_from)
    if date_to:
        count_query = count_query.where(FraudAlert.created_at <= date_to)

    total_result = await db.execute(count_query)
    total = len(total_result.all())

    query = query.order_by(FraudAlert.created_at.desc()).offset(skip).limit(page_size)
    result = await db.execute(query)
    alerts = list(result.scalars().all())

    items = [
        AlertResponse(
            id=a.id,
            transaction_id=a.transaction_id,
            status=a.status.value if hasattr(a.status, "value") else a.status,
            score=a.score,
            threshold=a.threshold,
            classification=a.classification,
            reviewed_by=a.reviewed_by,
            reviewed_at=a.reviewed_at,
            created_at=a.created_at,
        )
        for a in alerts
    ]

    return AlertListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/{alert_id}/review", response_model=AlertResponse)
async def review_alert_endpoint(
    alert_id: uuid.UUID,
    payload: AlertActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AlertResponse:
    """Mark an alert as reviewed."""
    result = await db.execute(select(FraudAlert).where(FraudAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    previous_status = alert.status.value if hasattr(alert.status, "value") else alert.status
    alert.status = AlertStatus.REVIEWED
    alert.reviewed_by = uuid.UUID(current_user["user_id"])
    alert.reviewed_at = datetime.now(tz=timezone.utc)
    await db.flush()

    await _audit_service.create_entry(
        db=db,
        action_type="review",
        transaction_id=alert.transaction_id,
        user_id=uuid.UUID(current_user["user_id"]),
        previous_status=previous_status,
        new_status="reviewed",
        details={"alert_id": str(alert.id), "reason": payload.reason},
    )

    return AlertResponse(
        id=alert.id,
        transaction_id=alert.transaction_id,
        status=alert.status.value,
        score=alert.score,
        threshold=alert.threshold,
        classification=alert.classification,
        reviewed_by=alert.reviewed_by,
        reviewed_at=alert.reviewed_at,
        created_at=alert.created_at,
    )


@router.post("/{alert_id}/false-positive", response_model=AlertResponse)
async def false_positive_alert_endpoint(
    alert_id: uuid.UUID,
    payload: AlertActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AlertResponse:
    """Mark an alert as a false positive (resolved)."""
    result = await db.execute(select(FraudAlert).where(FraudAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    previous_status = alert.status.value if hasattr(alert.status, "value") else alert.status
    alert.status = AlertStatus.RESOLVED
    alert.reviewed_by = uuid.UUID(current_user["user_id"])
    alert.reviewed_at = datetime.now(tz=timezone.utc)
    await db.flush()

    await _audit_service.create_entry(
        db=db,
        action_type="false_positive",
        transaction_id=alert.transaction_id,
        user_id=uuid.UUID(current_user["user_id"]),
        previous_status=previous_status,
        new_status="resolved",
        details={"alert_id": str(alert.id), "reason": payload.reason},
    )

    return AlertResponse(
        id=alert.id,
        transaction_id=alert.transaction_id,
        status=alert.status.value,
        score=alert.score,
        threshold=alert.threshold,
        classification=alert.classification,
        reviewed_by=alert.reviewed_by,
        reviewed_at=alert.reviewed_at,
        created_at=alert.created_at,
    )


@router.post("/{alert_id}/revert", response_model=AlertResponse)
async def revert_alert_endpoint(
    alert_id: uuid.UUID,
    payload: AlertActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AlertResponse:
    """Revert a reviewed/false-positive alert back to open."""
    result = await db.execute(select(FraudAlert).where(FraudAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    previous_status = alert.status.value if hasattr(alert.status, "value") else alert.status
    alert.status = AlertStatus.OPEN
    alert.reviewed_by = uuid.UUID(current_user["user_id"])
    alert.reviewed_at = datetime.now(tz=timezone.utc)
    await db.flush()

    await _audit_service.create_entry(
        db=db,
        action_type="revert",
        transaction_id=alert.transaction_id,
        user_id=uuid.UUID(current_user["user_id"]),
        previous_status=previous_status,
        new_status="open",
        details={"alert_id": str(alert.id), "reason": payload.reason},
    )

    return AlertResponse(
        id=alert.id,
        transaction_id=alert.transaction_id,
        status=alert.status.value,
        score=alert.score,
        threshold=alert.threshold,
        classification=alert.classification,
        reviewed_by=alert.reviewed_by,
        reviewed_at=alert.reviewed_at,
        created_at=alert.created_at,
    )
