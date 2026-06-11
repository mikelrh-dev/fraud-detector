"""Audit endpoints — transaction audit trail, analyst activity, export."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db, require_role
from src.schemas.audit import (
    AuditEntryResponse,
    AuditExportRequest,
    AuditExportResponse,
    AuditListResponse,
)
from src.services.audit import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])

_audit_service = AuditService()


@router.get("/transactions/{transaction_id}", response_model=AuditListResponse)
async def get_transaction_audit_trail(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AuditListResponse:
    """Get the complete audit trail for a specific transaction."""
    entries = await _audit_service.get_entries_for_transaction(
        db=db,
        transaction_id=transaction_id,
    )
    items = [
        AuditEntryResponse(
            id=str(e.id),
            action_type=e.action_type,
            transaction_id=str(e.transaction_id) if e.transaction_id else None,
            user_id=str(e.user_id) if e.user_id else None,
            previous_status=e.previous_status,
            new_status=e.new_status,
            details=e.details,
            sha256_checksum=e.sha256_checksum,
            created_at=e.created_at,
        )
        for e in entries
    ]
    return AuditListResponse(items=items, total=len(items))


@router.get("/analysts/{user_id}", response_model=AuditListResponse)
async def get_analyst_activity(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
) -> AuditListResponse:
    """Get all audit entries for a specific analyst (admin only)."""
    entries = await _audit_service.get_entries_for_analyst(
        db=db,
        user_id=user_id,
    )
    items = [
        AuditEntryResponse(
            id=str(e.id),
            action_type=e.action_type,
            transaction_id=str(e.transaction_id) if e.transaction_id else None,
            user_id=str(e.user_id) if e.user_id else None,
            previous_status=e.previous_status,
            new_status=e.new_status,
            details=e.details,
            sha256_checksum=e.sha256_checksum,
            created_at=e.created_at,
        )
        for e in entries
    ]
    return AuditListResponse(items=items, total=len(items))


@router.post("/export", response_model=AuditExportResponse)
async def export_audit_trail(
    payload: AuditExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
) -> AuditExportResponse:
    """Export audit entries within a date range (admin only)."""
    entries = await _audit_service.export(
        db=db,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    items = [
        AuditEntryResponse(
            id=str(e.id),
            action_type=e.action_type,
            transaction_id=str(e.transaction_id) if e.transaction_id else None,
            user_id=str(e.user_id) if e.user_id else None,
            previous_status=e.previous_status,
            new_status=e.new_status,
            details=e.details,
            sha256_checksum=e.sha256_checksum,
            created_at=e.created_at,
        )
        for e in entries
    ]
    return AuditExportResponse(
        entries=items,
        total=len(items),
        generated_at=datetime.now(tz=timezone.utc),
    )
