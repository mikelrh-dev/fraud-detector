"""AuditEntry ORM model — immutable audit trail for all scoring events."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class AuditEntry(Base):
    """Immutable audit trail entry — records every scoring and analyst action.

    This model deliberately uses Base directly (not BaseModel) to exclude
    updated_at — entries are append-only and never modified.
    """

    __tablename__ = "audit_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(tz=timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
