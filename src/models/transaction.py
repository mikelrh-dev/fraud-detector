"""Transaction ORM model."""

import enum
import uuid

from sqlalchemy import ForeignKey, Index, Numeric, String
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

    # Declared on the model, not only in the migration: an index that exists
    # solely in a migration is invisible to autogenerate, which then emits
    # drop_index for it on the next `alembic revision`.
    __table_args__ = (
        Index("ix_transactions_user_id_deleted_at", "user_id", "deleted_at"),
    )

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
