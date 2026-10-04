"""add analyst_label to fraud_alerts

Revision ID: d7e8f9a0b1c2
Revises: c4d5e6f7a8b9
Create Date: 2026-10-04 09:00:00.000000

The analyst's verdict had nowhere to live. `AlertStatus.resolved` was reachable
from exactly one endpoint — `false-positive` — so a transaction that WAS fraud
and an analyst correctly confirmed it was indistinguishable, in storage, from a
transaction that was never fraud at all. Every labelled example in the database
would have been a false positive.

So this adds one nullable column holding the verdict, and leaves every existing
row at NULL. NULL means "unlabelled". There is no backfill, because there is no
verdict to backfill: those rows were never judged, and writing one would be
inventing evidence.

The CHECK is the reason the vocabulary is enforced rather than documented. NULL
is a legal value here, so the legal set is three values, not two, and any
writer that misspells a label would otherwise produce a row that reads as
"unlabelled" to every consumer — which the label exporter drops in silence.

Declared on the model as well as here, deliberately: a constraint that exists
only in this file is invisible to autogenerate, which then proposes dropping it
on the next `revision` (the C8 shape in `tests/migrations/test_migration_drift.py`).

BATCH MODE IS NOT A WORKAROUND HERE, IT IS THE ONLY WAY
-------------------------------------------------------
Neither `create_check_constraint` nor `drop_constraint` exists on SQLite: there
is no `ALTER TABLE ... ADD CONSTRAINT`, and Alembic raises
`NotImplementedError: No support for ALTER of constraints in SQLite dialect`
rather than degrading. `tests/migrations/test_migration_drift.py` builds the
chain on SQLite, so the migration has to run there to be testable at all.

`batch_alter_table` with `recreate="auto"` is the resolution that costs nothing
on the real target: on PostgreSQL batch mode emits ordinary `ALTER TABLE`
statements, so production runs the cheap path and SQLite runs the
copy-and-move path. The alternative -- dropping the CHECK and enforcing the
vocabulary in application code only -- was rejected because it moves a
data-integrity guarantee to the one layer that can be bypassed by a script, and
because a value no consumer recognises is dropped by the exporter in silence.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: The BARE constraint name. `batch_alter_table` binds the constraint to the
#: project's `MetaData`, whose convention is
#: `"ck": "ck_%(table_name)s_%(constraint_name)s"` (src/core/database.py), so
#: this renders as `ck_fraud_alerts_analyst_label` — the same string the model
#: produces from its own bare name.
#:
#: Passing a pre-prefixed `ck_fraud_alerts_analyst_label` here does NOT produce
#: that name. It renders as `ck_fraud_alerts_ck_fraud_alerts_analyst_label`,
#: verified by reading the emitted DDL with `alembic upgrade --sql`. So this
#: constant must stay unprefixed, in BOTH directions of the migration.
_CHECK_NAME = "analyst_label"
_CHECK_SQL = (
    "analyst_label IS NULL OR analyst_label IN ('confirmed_fraud', 'false_positive')"
)


def upgrade() -> None:
    with op.batch_alter_table("fraud_alerts") as batch:
        # Nullable with no server_default: existing rows read NULL, and a
        # default would be a value the migration asserted about rows it knows
        # nothing about.
        batch.add_column(
            sa.Column("analyst_label", sa.String(length=20), nullable=True)
        )
        batch.create_check_constraint(_CHECK_NAME, _CHECK_SQL)


def downgrade() -> None:
    with op.batch_alter_table("fraud_alerts") as batch:
        # Drops the constraint before the column: the constraint references the
        # column, so the reverse order leaves the constraint behind.
        batch.drop_constraint(_CHECK_NAME, type_="check")
        batch.drop_column("analyst_label")
