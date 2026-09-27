"""Pydantic schemas for transaction CRUD operations."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    """Payload for creating a new transaction."""

    # Upper bound mirrors the Numeric(12,2) column. Without it, `inf` was
    # accepted, matched no threshold tier (the test is `amount < max_amount`
    # and the last tier's max is math.inf), and scored as legitimate.
    amount: float = Field(
        ...,
        gt=0,
        le=9_999_999_999.99,
        allow_inf_nan=False,
        description="Transaction amount",
    )
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")
    merchant_name: str = Field(..., min_length=1, max_length=255)
    merchant_category: str | None = Field(None, max_length=100)
    card_last4: str = Field(..., min_length=4, max_length=4, description="Last 4 digits of card")
    # DEPRECATED: user_id is ignored server-side (F2). The authenticated
    # user's identity is always used. Kept for backward compatibility with
    # existing clients; will be removed in a future version.
    user_id: uuid.UUID | None = Field(None, deprecated="Ignored — server uses authenticated user identity")


class ShapContribution(BaseModel):
    """A single feature contribution computed by SHAP (FRD-SHP-001).

    Ordered by rank in the detail response; signed contribution —
    positive pushes toward fraud, negative toward legitimate.
    """

    feature: str
    contribution: float


class ScoreBreakdown(BaseModel):
    """Scoring breakdown nested in transaction responses.

    Mirrors ScoreResponse minus transaction_id/created_at/fired_rules
    (fired_rules is not persisted in fraud_scores).
    """

    rule_score: float
    ml_score: float
    ensemble_score: float
    threshold: float
    classification: str

    shap_contributions: list[ShapContribution] | None = None

    model_config = {"from_attributes": True}  # enables model_validate(FraudScore)


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
    classification: str | None = None
    scoring: ScoreBreakdown | None = None
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
