"""Pydantic schemas for audit trail queries and export."""

from datetime import datetime

from pydantic import BaseModel


class AuditEntryResponse(BaseModel):
    """An individual audit trail entry returned to clients."""

    id: str
    action_type: str
    transaction_id: str | None = None
    user_id: str | None = None
    previous_status: str | None = None
    new_status: str | None = None
    details: dict | None = None
    sha256_checksum: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditListResponse(BaseModel):
    """Paginated list of audit entries."""

    items: list[AuditEntryResponse]
    total: int


class AuditExportResponse(BaseModel):
    """Audit trail export — all entries in a date range."""

    entries: list[AuditEntryResponse]
    total: int
    generated_at: datetime


class AuditExportRequest(BaseModel):
    """Payload for requesting an audit export."""

    start_date: datetime
    end_date: datetime
