"""Pydantic schemas for transaction CRUD operations."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    """Payload for creating a new transaction."""

    amount: float = Field(..., gt=0, description="Transaction amount")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")
    merchant_name: str = Field(..., min_length=1, max_length=255)
    merchant_category: str | None = Field(None, max_length=100)
    card_last4: str = Field(..., min_length=4, max_length=4, description="Last 4 digits of card")
    user_id: uuid.UUID


class TransactionResponse(BaseModel):
    """Transaction details returned to clients."""

    id: uuid.UUID
    amount: float
    currency: str
    merchant_name: str
    merchant_category: str | None
    card_last4: str
    status: str
    risk_score: float | None = None
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    """Paginated list of transactions."""

    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int
