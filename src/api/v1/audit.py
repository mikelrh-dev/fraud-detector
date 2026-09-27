"""Audit endpoints — transaction audit trail, analyst activity, export."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db, require_role
from src.models.transaction import Transaction
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
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AuditListResponse:
    """Get the audit trail for a specific transaction.

    Non-admin users can only access audit trails for their own transactions.
    """
    # --- Ownership check (R1-003 / F1): load the transaction and verify
    # the current user owns it (or is admin). ---
    txn_result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    txn = txn_result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    is_admin = current_user.get("role") == "admin"
    if not is_admin and str(txn.user_id) != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not your transaction",
        )

    offset = (page - 1) * page_size
    entries = await _audit_service.get_entries_for_transaction(
        db=db,
        transaction_id=transaction_id,
        offset=offset,
        limit=page_size,
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
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
) -> AuditListResponse:
    """Get audit entries for a specific analyst (admin only)."""
    offset = (page - 1) * page_size
    entries = await _audit_service.get_entries_for_analyst(
        db=db,
        user_id=user_id,
        offset=offset,
        limit=page_size,
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
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
) -> AuditExportResponse:
    """Export audit entries within a date range (admin only)."""
    offset = (page - 1) * page_size
    entries = await _audit_service.export(
        db=db,
        start_date=payload.start_date,
        end_date=payload.end_date,
        offset=offset,
        limit=page_size,
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
