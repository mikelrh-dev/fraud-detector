"""Pydantic schemas for fraud alert management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AlertResponse(BaseModel):
    """Fraud alert details returned to clients."""

    id: uuid.UUID
    transaction_id: uuid.UUID
    status: str
    score: float
    threshold: float
    classification: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    """Paginated list of fraud alerts."""

    items: list[AlertResponse]
    total: int
    page: int
    page_size: int


class AlertActionRequest(BaseModel):
    """Payload for analyst action on an alert."""

    action: str = Field(
        ...,
        pattern=r"^(review|false_positive|revert)$",
        description="Action to perform: review, false_positive, or revert",
    )
    reason: str | None = Field(None, max_length=500)
