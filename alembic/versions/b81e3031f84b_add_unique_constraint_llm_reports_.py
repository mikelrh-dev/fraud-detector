"""add unique constraint llm_reports transaction_id

Revision ID: b81e3031f84b
Revises: a1b2c3d4e5f6
Create Date: 2026-09-27 13:46:44.597403

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b81e3031f84b'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enforce one LLM report per transaction at the database level.
    # Prevents duplicate reports from retry/recovery loops.
    op.create_unique_constraint(
        "uq_llm_reports_transaction_id",
        "llm_reports",
        ["transaction_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_llm_reports_transaction_id",
        "llm_reports",
        type_="unique",
    )
