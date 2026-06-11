"""FraudScore ORM model — persists scoring breakdown for each transaction."""

import enum
import uuid

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import BaseModel


class FraudClassification(str, enum.Enum):
    """Fraud classification based on ensemble score vs threshold."""

    LEGITIMATE = "legitimate"
    REVIEW = "review"
    FRAUD = "fraud"


class FraudScore(BaseModel):
    """Persisted fraud scoring breakdown for a transaction."""

    __tablename__ = "fraud_scores"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_score: Mapped[float] = mapped_column(Float, nullable=False)
    ml_score: Mapped[float] = mapped_column(Float, nullable=False)
    ensemble_score: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    classification: Mapped[FraudClassification] = mapped_column(
        String(20),
        nullable=False,
    )
