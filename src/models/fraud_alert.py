"""FraudAlert ORM model — alerts when a transaction exceeds its threshold."""

import enum
import uuid

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import BaseModel


class AlertStatus(str, enum.Enum):
    """Alert status enumeration."""

    OPEN = "open"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"


class FraudAlert(BaseModel):
    """Alert record for transactions that exceed the fraud threshold."""

    __tablename__ = "fraud_alerts"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[AlertStatus] = mapped_column(
        String(20),
        default=AlertStatus.OPEN,
        nullable=False,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
