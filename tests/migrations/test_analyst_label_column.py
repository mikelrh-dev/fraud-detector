"""The analyst verdict is persisted on the alert row, not inferred from status.

WHAT THIS FILE IS FOR
--------------------
An analyst's verdict was the only thing that separated "this alert was wrong"
from "this alert was right", and the row could not record it. `AlertStatus`
carried `open` / `reviewed` / `resolved`, and `resolved` was reachable from
exactly one endpoint — `false-positive`. A transaction that WAS fraud and an
analyst correctly confirmed it had nowhere to write that down, so the two
outcomes were indistinguishable in storage.

So this adds one nullable column, `analyst_label`, holding
`confirmed_fraud` / `false_positive` / NULL, and leaves every existing row at
NULL. NULL means "no verdict", which is a fact about the row. Backfilling it
would be inventing one.

WHY THE CHECK CONSTRAINT IS ASSERTED AND NOT JUST THE COLUMN
------------------------------------------------------------
`NULL` is a legal verdict here ("nobody has judged this yet"), so the legal
value set is three values, not two. A `CHECK` makes that a database guarantee
rather than an application convention: without it, any future writer that
misspells a label writes a row that reads as "unlabelled" to every consumer,
and the exporter silently drops it. This repository's own history is the
argument — `_load_synthetic_csv` was hardened because a loader that reads
whatever vocabulary it finds is a corruption one command away.

The constraint is asserted on BOTH sides on purpose. `test_migration_drift`
forbids a constraint that exists only in a migration, because autogenerate
cannot see it and emits `drop_constraint` on the next `revision`; and a
constraint that exists only on the model was never created in a real database.
Both halves have to be true at once or the column's guarantee is fiction in one
direction or the other.

DOWNGRADE IS TESTED, NOT ASSUMED
---------------------------------
A migration that only works going up leaves a broken downgrade path in the
chain forever. There is no live PostgreSQL here, so this uses the same SQLite
substitution `test_migration_drift` established: `alembic` reaches the
database through `Settings.database_url`, and the PG UUID type is rendered as
`CHAR(32)` for SQLite.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import CheckConstraint, create_engine
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles

import src.models  # noqa: F401  — registers every model on Base.metadata
from alembic import command
from src.core.config import Settings
from src.models.base import Base
from src.models.fraud_alert import FraudAlert

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: The three values a label may hold. `None` is not in the tuple because it is
#: the column's default, not a value the writer ever supplies.
EXPECTED_VALUES = ("confirmed_fraud", "false_positive")


@compiles(PG_UUID, "sqlite")
def _render_pg_uuid_on_sqlite(type_, compiler, **kw):
    """Render PostgreSQL UUID as CHAR(32) so migrations can run on SQLite."""
    return "CHAR(32)"


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'labels.db'}"


@pytest.fixture()
def alembic_cfg(tmp_path):
    """A `Config` pointed at this project's `alembic/` directory."""
    cfg = Config()
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return cfg


@pytest.fixture()
def upgraded_db(tmp_path, alembic_cfg):
    """A SQLite database migrated to head, and rolled back on teardown."""
    url = _sqlite_url(tmp_path)
    original = Settings.database_url
    Settings.database_url = property(lambda self: url)  # type: ignore[method-assign]
    try:
        command.upgrade(alembic_cfg, "head")
        engine = create_engine(url)
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        Settings.database_url = original  # type: ignore[method-assign]


class TestTheLabelColumn:
    """`analyst_label` exists, is nullable, and admits only real verdicts."""

    def test_column_exists_after_upgrade(self, upgraded_db):
        columns = {c["name"] for c in sa_inspect(upgraded_db).get_columns("fraud_alerts")}

        assert "analyst_label" in columns, (
            f"migrated fraud_alerts has {sorted(columns)}; the analyst verdict "
            f"has nowhere to live, so a confirmed fraud and a false positive "
            f"stay indistinguishable in storage."
        )

    def test_column_is_nullable(self, upgraded_db):
        """Pre-existing rows stay NULL. NULL means "unlabelled", not "clean"."""
        columns = {
            c["name"]: c for c in sa_inspect(upgraded_db).get_columns("fraud_alerts")
        }

        assert columns["analyst_label"]["nullable"] is True, (
            "analyst_label is NOT NULL. Every alert row that predates the "
            "migration would have to be backfilled with a verdict, and there "
            "is no verdict to backfill — the rows were never judged."
        )

    def test_unlabelled_row_is_readable_and_defaults_to_null(self, upgraded_db):
        """A row with no verdict stores NULL, not a placeholder string.

        This is what makes "existing rows stay null" observable rather than
        merely intended: the column has to accept and round-trip NULL.
        """
        with upgraded_db.connect() as connection:
            connection.exec_driver_sql(
                "INSERT INTO transactions "
                "(id, amount, currency, merchant_name, merchant_category, "
                "card_last4, status, user_id, created_at, updated_at) "
                "VALUES ('t1', 10.0, 'USD', 'Store', 'retail', '1234', "
                "'flagged', 'u1', '2024-01-01', '2024-01-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO fraud_alerts "
                "(id, transaction_id, status, score, threshold, classification, "
                "created_at, updated_at) "
                "VALUES ('a1', 't1', 'open', 90.0, 70.0, 'fraud', "
                "'2024-01-01', '2024-01-01')"
            )
            connection.commit()
            label = connection.exec_driver_sql(
                "SELECT analyst_label FROM fraud_alerts WHERE id = 'a1'"
            ).scalar()

        assert label is None, (
            f"a freshly inserted alert carries analyst_label={label!r}; a row "
            f"nobody has judged must read as NULL."
        )

    @pytest.mark.parametrize("value", EXPECTED_VALUES)
    def test_both_verdicts_are_accepted(self, upgraded_db, value):
        """The CHECK admits both real verdicts."""
        with upgraded_db.connect() as connection:
            connection.exec_driver_sql(
                "INSERT INTO transactions "
                "(id, amount, currency, merchant_name, merchant_category, "
"card_last4, status, user_id, created_at, updated_at) "
                "VALUES ('t1', 10.0, 'USD', 'Store', 'retail', '1234', "
                "'flagged', 'u1', '2024-01-01', '2024-01-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO fraud_alerts "
                "(id, transaction_id, status, score, threshold, classification, "
                "analyst_label, created_at, updated_at) "
                f"VALUES ('a1', 't1', 'resolved', 90.0, 70.0, 'fraud', "
                f"'{value}', '2024-01-01', '2024-01-01')"
            )
            connection.commit()
            stored = connection.exec_driver_sql(
                "SELECT analyst_label FROM fraud_alerts WHERE id = 'a1'"
            ).scalar()

        assert stored == value

    def test_a_third_value_is_refused_by_the_database(self, upgraded_db):
        """A label outside the vocabulary is rejected by the database.

        The failure this replaces is quiet: without the CHECK, a typo writes a
        row whose label no consumer recognises, and the exporter — which keys
        on the label — drops it without a word.
        """
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            with upgraded_db.connect() as connection:
                connection.exec_driver_sql(
                    "INSERT INTO transactions "
                    "(id, amount, currency, merchant_name, merchant_category, "
                    "card_last4, status, user_id, created_at, updated_at) "
                    "VALUES ('t1', 10.0, 'USD', 'Store', 'retail', '1234', "
                    "'flagged', 'u1', '2024-01-01', '2024-01-01')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO fraud_alerts "
                    "(id, transaction_id, status, score, threshold, "
                    "classification, analyst_label, created_at, updated_at) "
                    "VALUES ('a1', 't1', 'resolved', 90.0, 70.0, 'fraud', "
                    "'confirmed_fraudd', '2024-01-01', '2024-01-01')"
                )
                connection.commit()


class TestModelAndMigrationAgree:
    """Both halves of the guarantee, or the guarantee is fiction in one."""

    def test_model_declares_the_column(self):
        assert hasattr(FraudAlert, "analyst_label"), (
            "the model does not declare analyst_label; autogenerate compares "
            "the migration chain against the models, so a column that exists "
            "in the database and not on the model reads as drift and gets "
            "emitted as a drop_column."
        )

    def test_model_column_is_nullable(self):
        column = FraudAlert.__table__.c.get("analyst_label")

        assert column is not None, "the model declares no analyst_label column"
        assert column.nullable is True

    def test_model_declares_the_check_constraint(self):
        """The constraint must be visible to autogenerate.

        This is the C8 shape: a constraint that exists only in a migration is
        invisible to autogenerate, which then proposes dropping it. Declared
        only on the model, it was never created in the database at all.
        """
        from sqlalchemy import CheckConstraint

        constraints = [
            c for c in FraudAlert.__table__.constraints
            if isinstance(c, CheckConstraint)
        ]

        assert constraints, (
            "no CheckConstraint on the model. Either the value set lives only "
            "in the migration (and autogenerate will propose dropping it) or "
            "only on the model (and the database never enforces it)."
        )

    def test_model_value_set_matches_the_documented_one(self):
        """The vocabulary is one constant, imported by every writer."""
        from src.models.fraud_alert import ANALYST_LABEL_VALUES

        assert ANALYST_LABEL_VALUES == EXPECTED_VALUES, (
            f"ANALYST_LABEL_VALUES is {ANALYST_LABEL_VALUES}; the documented "
            f"vocabulary is {EXPECTED_VALUES}. These are the values the CHECK "
            f"admits, the exporter keys on, and the endpoints write."
        )

    def test_alembic_would_not_drop_the_column(self, upgraded_db):
        """The column is on the model AND in the migration."""
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext

        with upgraded_db.connect() as connection:
            diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

        removed = [op for op in diff if op[0] == "remove_column"]

        assert not removed, (
            f"autogenerate would drop columns: {[r[1].name for r in removed]}"
        )

def _emitted_sql(revision_range: str, *, downgrade_to: bool = False) -> str:
    """The SQL alembic would run for `revision_range`, without a database.

    `--sql` renders the migration offline against a real dialect, so this is
    the DDL PostgreSQL would receive -- not a reconstruction of it. The URL is a
    PostgreSQL one because that is the target that matters here; the SQLite path
    goes through batch mode's copy-and-move and is covered by the drift test.

    Offline downgrade needs an explicit `from:to` range; a bare relative `-1`
    raises "Relative revision -1 didn't produce 1 migrations" because there is
    no version table to count against in offline mode.
    """
    import io

    url = "postgresql+psycopg2://user:pass@localhost/db"
    original = Settings.database_url
    Settings.database_url = property(lambda self: url)  # type: ignore[method-assign]
    cfg = Config()
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    # Offline mode writes the rendered DDL to `output_buffer`, not to a
    # `command.upgrade` kwarg -- there isn't one.
    buf = io.StringIO()
    cfg.stdout = buf
    cfg.output_buffer = buf
    try:
        if downgrade_to:
            command.downgrade(cfg, revision_range, sql=True, tag="probe")
        else:
            command.upgrade(cfg, revision_range, sql=True, tag="probe")
    finally:
        Settings.database_url = original  # type: ignore[method-assign]
    return re.sub(r"^\s*(INFO|WARNING)\s.*$", "", buf.getvalue(), flags=re.M)


class TestTheConstraintNameReachesPostgresIntact:
    """The name in the DDL must be the name the model knows.

    This is the one place the SQLite drift test cannot help, and it is here
    because the first version of this constraint got it wrong twice.

    `Base.metadata` runs every constraint name through the project's convention,
    `"ck": "ck_%(table_name)s_%(constraint_name)s"` (src/core/database.py).
    Crucially `batch_alter_table` binds the migration's constraint to that same
    `MetaData`, so the convention applies to the MIGRATION too -- which is not
    what it looks like from reading `op.create_check_constraint`, and which the
    first draft of this file got backwards by asserting the opposite.

    So a pre-prefixed name renders doubled in both places and matches nothing;
    a bare name renders correctly in both. The two mistakes are symmetric and
    neither is caught by the SQLite drift test, because batch mode reflects the
    table and rebuilds it through the model, so on SQLite the database always
    ends up agreeing with whatever the model says.

    That is why this asserts on the EMITTED DDL. A string comparison against a
    constant would have passed on the doubled version.
    """

    def test_the_model_name_is_the_one_the_upgrade_emits(self):
        from_model = next(
            c.name
            for c in FraudAlert.__table__.constraints
            if isinstance(c, CheckConstraint)
        )
        sql = _emitted_sql("c4d5e6f7a8b9:head")

        emitted = re.findall(r"ADD CONSTRAINT (\w+) CHECK", sql)

        assert emitted, (
            f"the upgrade emitted no CHECK constraint; SQL was:\n{sql}"
        )
        assert emitted == [from_model], (
            f"the upgrade emits {emitted} but the model declares {from_model!r}. "
            f"They must be the same string or autogenerate will propose "
            f"dropping the constraint the migration created -- and only on "
            f"PostgreSQL, which is why the SQLite drift test cannot see it."
        )

    def test_the_downgrade_emits_a_drop_for_that_same_name(self):
        """Both directions, or the downgrade targets a name that never existed."""
        from_model = next(
            c.name
            for c in FraudAlert.__table__.constraints
            if isinstance(c, CheckConstraint)
        )
        sql = _emitted_sql("d7e8f9a0b1c2:c4d5e6f7a8b9", downgrade_to=True)

        dropped = re.findall(r"DROP CONSTRAINT (\w+)", sql)

        assert dropped == [from_model], (
            f"the downgrade drops {dropped}; the upgrade creates {from_model!r}. "
            f"A downgrade naming a constraint that was never created fails on "
            f"the first rollback."
        )

    def test_the_upgrade_adds_the_column_nullable_and_undefaulted(self):
        """No server_default, so pre-existing rows read NULL rather than a
        fabricated verdict."""
        sql = _emitted_sql("c4d5e6f7a8b9:head")

        add_column = [ln for ln in sql.splitlines() if "ADD COLUMN analyst_label" in ln]

        assert add_column, f"the upgrade never adds analyst_label; SQL was:\n{sql}"
        assert "DEFAULT" not in add_column[0].upper(), (
            f"{add_column[0].strip()} carries a DEFAULT; every pre-existing alert "
            f"would be given a verdict the migration knows nothing about"
        )


class TestDowngrade:
    """The downgrade path is exercised, not assumed."""

    def test_downgrade_removes_the_column(self, tmp_path, alembic_cfg):
        url = _sqlite_url(tmp_path)
        original = Settings.database_url
        Settings.database_url = property(lambda self: url)  # type: ignore[method-assign]
        try:
            command.upgrade(alembic_cfg, "head")
            engine = create_engine(url)
            columns_before = {
                c["name"] for c in sa_inspect(engine).get_columns("fraud_alerts")
            }
            engine.dispose()
            assert "analyst_label" in columns_before, (
                "the upgrade did not add the column, so a downgrade proves "
                "nothing"
            )

            command.downgrade(alembic_cfg, "-1")

            engine = create_engine(url)
            try:
                columns_after = {
                    c["name"] for c in sa_inspect(engine).get_columns("fraud_alerts")
                }
            finally:
                engine.dispose()
        finally:
            Settings.database_url = original  # type: ignore[method-assign]

        assert "analyst_label" not in columns_after, (
            f"after downgrade the column is still present in {sorted(columns_after)}"
        )

    def test_the_chain_returns_to_head_after_a_round_trip(self, tmp_path, alembic_cfg):
        """downgrade -1 then upgrade head leaves the schema where it started.

        Without this, a downgrade that drops the column and an upgrade that
        re-adds it slightly differently pass both single-direction tests and
        still leave the chain unable to round-trip.
        """
        url = _sqlite_url(tmp_path)
        original = Settings.database_url
        Settings.database_url = property(lambda self: url)  # type: ignore[method-assign]
        try:
            command.upgrade(alembic_cfg, "head")
            engine = create_engine(url)
            at_head = {
                c["name"] for c in sa_inspect(engine).get_columns("fraud_alerts")
            }
            engine.dispose()

            command.downgrade(alembic_cfg, "-1")
            command.upgrade(alembic_cfg, "head")

            engine = create_engine(url)
            try:
                after_round_trip = {
                    c["name"] for c in sa_inspect(engine).get_columns("fraud_alerts")
                }
            finally:
                engine.dispose()
        finally:
            Settings.database_url = original  # type: ignore[method-assign]

        assert after_round_trip == at_head, (
            f"head had {sorted(at_head)}; after downgrade -1 and re-upgrade it "
            f"has {sorted(after_round_trip)}"
        )
