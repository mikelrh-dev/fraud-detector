"""FraudAlert ORM model — alerts when a transaction exceeds its threshold."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import BaseModel


class AlertStatus(str, enum.Enum):
    """Alert status enumeration."""

    OPEN = "open"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"


#: The analyst verdicts `fraud_alerts.analyst_label` may hold, in the order the
#: exporter and the CHECK constraint read them. A third value is ``None`` and
#: lives in the column's nullability rather than here: "nobody has judged this
#: yet" is a fact about the row, not a verdict.
#:
#: One constant, imported by every writer. The alternative — each endpoint
#: typing its own string literal — is how a column ends up holding a value no
#: consumer recognises, which the exporter then drops in silence.
ANALYST_LABEL_VALUES = ("confirmed_fraud", "false_positive")


class FraudAlert(BaseModel):
    """Alert record for transactions that exceed the fraud threshold."""

    __tablename__ = "fraud_alerts"

    # Declared on the model so autogenerate can see them; see transactions.
    # The CHECK is declared here for the same reason and with the same
    # consequence: a constraint that exists only in the migration is invisible
    # to autogenerate, which then emits `drop_constraint` on the next
    # `revision`. It is spelled out rather than built from the constant above
    # because a CHECK constraint in DDL is a literal — the f-string cannot see
    # the tuple the writers import, so the two are pinned to each other by
    # `tests/migrations/test_analyst_label_column.py`.
    __table_args__ = (
        Index("ix_fraud_alerts_status_created_at", "status", "created_at"),
        Index("ix_fraud_alerts_transaction_id", "transaction_id"),
        CheckConstraint(
            "analyst_label IS NULL OR analyst_label IN "
            f"({', '.join(repr(v) for v in ANALYST_LABEL_VALUES)})",
            # The BARE name, not `ck_fraud_alerts_analyst_label`. The project's
            # naming convention is `"ck": "ck_%(table_name)s_%(constraint_name)s"`
            # (src/core/database.py), so this renders to
            # `ck_fraud_alerts_analyst_label` — which is the name the migration's
            # raw `create_check_constraint` call writes.
            #
            # Writing the prefix here instead yields
            # `ck_fraud_alerts_ck_fraud_alerts_analyst_label` from the model
            # against `ck_fraud_alerts_analyst_label` in the database. On SQLite
            # the two then agree by ACCIDENT — batch mode reflects the table and
            # rebuilds it through the model, so the doubled name is what lands in
            # the test database — which is why `test_migration_drift` stays green
            # and hides it. On PostgreSQL, the real target, they genuinely differ
            # and autogenerate proposes dropping a constraint the migration
            # created. `test_the_constraint_name_the_model_generates_is_the_one_
            # the_migration_creates` compares the two names directly, with no
            # database, precisely because the drift test cannot catch this.
            name="analyst_label",
        ),
    )

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
    # The analyst's verdict. Nullable and NOT defaulted: an alert nobody has
    # judged stores NULL, and every alert row that predates this column keeps
    # NULL rather than being backfilled with a verdict that was never given.
    # `review` deliberately does NOT set it — "an analyst looked at this" is
    # not a verdict, and conflating the two would put unlabelled rows into
    # every downstream count.
    analyst_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
