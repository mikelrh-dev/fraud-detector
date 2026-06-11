"""Pydantic schemas for LLM-generated fraud reports."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ReportResponse(BaseModel):
    """Response schema for LLM-generated fraud reports.

    Returned by GET /transactions/{id}/report. The status field indicates
    whether the report is pending, completed, or failed.
    """

    transaction_id: uuid.UUID
    report_text: str | None = None
    model_name: str | None = None
    status: str = "pending"
    generation_time_ms: int | None = None
    created_at: datetime | None = None
    error_detail: str | None = None

    model_config = {"from_attributes": True}
