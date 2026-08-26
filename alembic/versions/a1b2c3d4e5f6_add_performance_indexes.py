"""add performance indexes

Revision ID: a1b2c3d4e5f6
Revises: b02e4753e78e
Create Date: 2026-08-26 17:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "b02e4753e78e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # transactions(user_id, deleted_at) — 3 queries per POST (create_transaction,
    # velocity store, user-history aggregates)
    op.create_index(
        "ix_transactions_user_id_deleted_at",
        "transactions",
        ["user_id", "deleted_at"],
        unique=False,
    )

    # fraud_scores(transaction_id) — every list/detail view joins on this
    op.create_index(
        "ix_fraud_scores_transaction_id",
        "fraud_scores",
        ["transaction_id"],
        unique=False,
    )

    # llm_reports(transaction_id) — reports endpoint
    op.create_index(
        "ix_llm_reports_transaction_id",
        "llm_reports",
        ["transaction_id"],
        unique=False,
    )

    # audit_entries(transaction_id) — audit trail per transaction
    op.create_index(
        "ix_audit_entries_transaction_id",
        "audit_entries",
        ["transaction_id"],
        unique=False,
    )

    # audit_entries(user_id) — analyst activity query
    op.create_index(
        "ix_audit_entries_user_id",
        "audit_entries",
        ["user_id"],
        unique=False,
    )

    # fraud_alerts(status, created_at) — default alert list sort
    op.create_index(
        "ix_fraud_alerts_status_created_at",
        "fraud_alerts",
        ["status", "created_at"],
        unique=False,
    )

    # fraud_alerts(transaction_id) — alerts-by-transaction lookup
    op.create_index(
        "ix_fraud_alerts_transaction_id",
        "fraud_alerts",
        ["transaction_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_fraud_alerts_transaction_id", table_name="fraud_alerts")
    op.drop_index("ix_fraud_alerts_status_created_at", table_name="fraud_alerts")
    op.drop_index("ix_audit_entries_user_id", table_name="audit_entries")
    op.drop_index("ix_audit_entries_transaction_id", table_name="audit_entries")
    op.drop_index("ix_llm_reports_transaction_id", table_name="llm_reports")
    op.drop_index("ix_fraud_scores_transaction_id", table_name="fraud_scores")
    op.drop_index("ix_transactions_user_id_deleted_at", table_name="transactions")
