"""Transaction ORM model."""

import enum
import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import BaseModel


class TransactionStatus(str, enum.Enum):
    """Transaction status enumeration."""

    PENDING = "pending"
    APPROVED = "approved"
    FLAGGED = "flagged"
    BLOCKED = "blocked"


class Transaction(BaseModel):
    """Financial transaction record."""

    __tablename__ = "transactions"

    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant_category: Mapped[str] = mapped_column(String(100), nullable=True)
    card_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(
        String(20),
        default=TransactionStatus.PENDING,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
