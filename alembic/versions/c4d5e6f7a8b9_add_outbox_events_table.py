"""add outbox_events table

Revision ID: c4d5e6f7a8b9
Revises: 876b2825a737
Create Date: 2026-09-27 20:40:00.000000

A19: durable hand-off between the transaction commit and the Redis streams, so a
Redis blip cannot leave a scored transaction with no report, no SHAP
attribution and no embedding, with nothing able to detect the gap.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = '876b2825a737'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        # A plain autoincrement integer, not the BaseModel UUID: the relay drains
        # in id order and the rows are deleted on publication, so a monotonic
        # counter is both cheaper and more useful than a random key.
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stream_name", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # The relay scans unpublished rows in id order; without these the drain
    # degrades as the table accumulates.
    op.create_index("ix_outbox_events_id", "outbox_events", ["id"])
    op.create_index("ix_outbox_events_stream_name", "outbox_events", ["stream_name"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_stream_name", table_name="outbox_events")
    op.drop_index("ix_outbox_events_id", table_name="outbox_events")
    op.drop_table("outbox_events")
