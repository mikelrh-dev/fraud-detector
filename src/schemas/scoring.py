"""Pydantic schemas for fraud scoring responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ScoreResponse(BaseModel):
    """Full scoring breakdown returned after transaction scoring."""

    transaction_id: uuid.UUID
    rule_score: float
    ml_score: float
    ensemble_score: float
    threshold: float
    classification: str
    fired_rules: list[str]
    created_at: datetime
    
    # Dynamic friction based on score and classification
    friction_level: str  # ALLOW | CHALLENGE | BLOCK
    action: str | None = None  # request_3d_secure | request_sms | request_biometric | block_transaction

    model_config = {"from_attributes": True}
