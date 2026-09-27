"""Migration-vs-model drift must be a test, not a manual `alembic revision`.

C8 regression: `DriftReferenceData` was used by `drift_service` and had a
migration, but was absent from `src/models/__init__.__py` and from
`alembic/env.py`. An unregistered model never reaches `Base.metadata`, so
`alembic revision --autogenerate` emitted `drop_table('drift_reference_data')`
— one careless command away from deleting the table in production.

Deriving `EXPECTED_TABLES` from `Base.metadata` could not catch this: it
asserted the drifted set against itself. This module instead diffs the schema
the migrations actually build against the models, the same comparison
autogenerate performs.
"""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic import command
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles

import src.models  # noqa: F401  — registers every model on Base.metadata
from src.core.config import Settings
from src.models.base import Base

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@compiles(PG_UUID, "sqlite")
def _render_pg_uuid_on_sqlite(type_, compiler, **kw):
    """Render PostgreSQL UUID as CHAR(32) so migrations can run on SQLite."""
    return "CHAR(32)"


@pytest.fixture()
def migrated_db(tmp_path):
    """A SQLite database built purely from the migration chain."""
    url = f"sqlite:///{tmp_path / 'drift.db'}"
    original = Settings.database_url
    Settings.database_url = property(lambda self: url)  # type: ignore[method-assign]
    cfg = Config()
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    try:
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        Settings.database_url = original  # type: ignore[method-assign]


class TestEveryModelIsRegistered:
    """A model missing from the package never reaches Base.metadata."""

    def test_all_concrete_models_are_exported(self):
        import inspect as py_inspect

        import src.models as models_pkg

        exported = set(models_pkg.__all__)
        for name in exported:
            obj = getattr(models_pkg, name)
            if not (py_inspect.isclass(obj) and hasattr(obj, "__tablename__")):
                continue
            assert name in exported

    def test_drift_reference_is_on_metadata(self):
        """The concrete C8 regression."""
        assert "drift_reference_data" in Base.metadata.tables

    def test_migrated_tables_cover_metadata(self, migrated_db):
        """Every model table must exist after `upgrade head`."""
        live = set(sa_inspect(migrated_db).get_table_names()) - {"alembic_version"}
        missing = set(Base.metadata.tables) - live
        assert not missing, f"models with no migration: {sorted(missing)}"


class TestAutogenerateIsNonDestructive:
    """The diff autogenerate would produce must contain no drops."""

    @pytest.fixture()
    def diff(self, migrated_db):
        with migrated_db.connect() as connection:
            context = MigrationContext.configure(connection)
            return compare_metadata(context, Base.metadata)

    def test_no_drop_table(self, diff):
        drops = [op for op in diff if op[0] == "remove_table"]
        assert not drops, (
            "autogenerate would DROP tables (a model is probably not "
            f"registered on Base.metadata): {[d[1].name for d in drops]}"
        )

    def test_no_drop_column(self, diff):
        drops = [op for op in diff if op[0] == "remove_column"]
        assert not drops, (
            f"autogenerate would DROP columns: {[d[1].name for d in drops]}"
        )

    def test_no_orphan_constraint_or_index(self, diff):
        """Constraints/indexes must be declared where autogenerate can see them."""
        drops = [
            op
            for op in diff
            if op[0] in {"remove_constraint", "remove_index", "remove_unique_constraint"}
        ]
        assert not drops, (
            "autogenerate would DROP constraints/indexes that exist only in a "
            f"migration: {[d[0] for d in drops]}"
        )

    def test_no_unexpected_additions(self, diff):
        """Additions are the safe direction, but any drift should be deliberate."""
        adds = [op for op in diff if op[0] == "add_table"]
        assert not adds, (
            f"migrations are missing tables the models declare: {[a[1].name for a in adds]}"
        )
