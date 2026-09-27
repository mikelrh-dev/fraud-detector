"""OutboxEvent ORM model — durable hand-off from the database to Redis Streams.

A19: the three ``publish_event`` calls in the scoring endpoint were
fire-and-forget. A Redis blip produced a committed, fully-scored transaction
with no LLM report, no SHAP attribution and no merchant embedding, and nothing in
the system could ever discover the gap: the report endpoint would just report
``pending`` forever.

Writing the event in the same session as the transaction is what makes it
durable. It also closes a race the audit did not name: the events were published
before the commit (the real commit happens in the ``get_db`` teardown, after the
response), and all three consumer tables have a hard foreign key to
``transactions.id``, so a worker that picked the message up in that window hit
an FK violation and burned retries on a transaction that was about to exist.

Rows are deleted once published rather than kept as history: this is a
transport queue, not an audit log, and ``AuditEntry`` is the audit log.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class OutboxEvent(Base):
    """One pending event awaiting publication to a Redis stream."""

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # The payload is JSON-encoded text rather than a JSON column: the shape
    # differs per stream and this is a transport buffer, not something to query
    # into. Text keeps the migration portable across SQLite and Postgres.
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # The relay polls for unpublished rows in id order, so the index has to
        # serve that scan; without it the drain degrades as the table grows.
        Index("ix_outbox_events_id", "id"),
        Index("ix_outbox_events_stream_name", "stream_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<OutboxEvent id={self.id} stream={self.stream_name} "
            f"attempts={self.attempts}>"
        )
