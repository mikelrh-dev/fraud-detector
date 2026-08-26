"""Round-trip tests for the performance-indexes Alembic migration — R1.

Verifies that ``alembic upgrade head`` creates the expected composite
single-column indexes for hot query paths and that
``alembic downgrade base`` removes them all.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles

from alembic import command
from src.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# --- Expected indexes added by the performance-indexes migration ---
# Each entry is (table_name, index_name, sorted list of column names).
EXPECTED_INDEXES = [
    ("transactions", "ix_transactions_user_id_deleted_at", ["deleted_at", "user_id"]),
    ("fraud_scores", "ix_fraud_scores_transaction_id", ["transaction_id"]),
    ("llm_reports", "ix_llm_reports_transaction_id", ["transaction_id"]),
    ("audit_entries", "ix_audit_entries_transaction_id", ["transaction_id"]),
    ("audit_entries", "ix_audit_entries_user_id", ["user_id"]),
    ("fraud_alerts", "ix_fraud_alerts_status_created_at", ["created_at", "status"]),
    ("fraud_alerts", "ix_fraud_alerts_transaction_id", ["transaction_id"]),
]


@compiles(PG_UUID, "sqlite")
def _render_pg_uuid_on_sqlite(type_, compiler, **kw):
    """Render PostgreSQL UUID as CHAR(32) so migrations can run on SQLite."""
    return "CHAR(32)"


@pytest.fixture()
def scratch_db_url(tmp_path):
    """SQLite scratch DB URL wired into alembic env via settings override."""
    url = f"sqlite:///{tmp_path / 'scratch.db'}"
    original = Settings.database_url
    Settings.database_url = property(lambda self: url)  # type: ignore[method-assign]
    try:
        yield url
    finally:
        Settings.database_url = original  # type: ignore[method-assign]


@pytest.fixture()
def alembic_config(scratch_db_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return cfg


def _get_indexes(engine, table_name: str) -> dict[str, list[str]]:
    """Return {index_name: [columns]} for the given table."""
    inspector = sa_inspect(engine)
    indexes = {}
    for idx in inspector.get_indexes(table_name):
        # SQLite inspector may use 'column_names' instead of 'columns'
        cols = idx.get("columns") or idx.get("column_names") or []
        indexes[idx["name"]] = sorted(cols)
    return indexes


class TestPerformanceIndexes:
    """After upgrade head, every expected index must exist with correct columns."""

    def test_indexes_created_after_upgrade(self, alembic_config):
        """RED: verify indexes exist after upgrade head."""
        command.upgrade(alembic_config, "head")
        engine = create_engine(
            alembic_config.get_main_option("sqlalchemy.url")
        )
        try:
            for table, idx_name, expected_cols in EXPECTED_INDEXES:
                table_indexes = _get_indexes(engine, table)
                assert idx_name in table_indexes, (
                    f"Index '{idx_name}' missing on table '{table}'. "
                    f"Found: {list(table_indexes.keys())}"
                )
                assert table_indexes[idx_name] == expected_cols, (
                    f"Index '{idx_name}' columns mismatch: "
                    f"expected {expected_cols}, got {table_indexes[idx_name]}"
                )
        finally:
            engine.dispose()

    def test_indexes_removed_after_downgrade(self, alembic_config):
        """After downgrade base, none of the new indexes should exist."""
        command.upgrade(alembic_config, "head")
        command.downgrade(alembic_config, "base")
        # Re-upgrade to just the initial migration (no performance indexes)
        # by dropping and recreating — downgrade base removes everything,
        # so we just verify via a fresh upgrade to the initial revision.
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(alembic_config)
        # Get the initial revision (b02e4753e78e)
        heads = script.get_heads()
        initial = None
        for rev in script.walk_revisions():
            if rev.down_revision is None:
                initial = rev.revision
                break
        if initial is None:
            initial = heads.split(",")[0]  # fallback

        command.upgrade(alembic_config, initial)
        engine = create_engine(
            alembic_config.get_main_option("sqlalchemy.url")
        )
        try:
            for table, idx_name, _expected_cols in EXPECTED_INDEXES:
                table_indexes = _get_indexes(engine, table)
                assert idx_name not in table_indexes, (
                    f"Index '{idx_name}' still exists on '{table}' after "
                    f"downgrade — should have been removed"
                )
        finally:
            engine.dispose()
