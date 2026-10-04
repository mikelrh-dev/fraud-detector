"""The label exporter has an operator entry point, and it reads the database.

WHAT THIS FILE IS FOR
---------------------
`scripts/export_labels.py` had a writer and no way to reach it. The only caller
of `write_label_csv` was `tests/test_export_labels.py`, so the corpus-export
half of the analyst feedback loop existed as a library function that no human
could invoke: you could `import` it and you could test it, and that was the
whole of its reachability. A feedback loop whose export step needs an IDE is a
feedback loop that does not run.

So this file pins the wiring -- CLI arguments in, resolved alert rows out, CSV
on disk -- and, more importantly, pins that adding it changed nothing about
WHAT leaves the database. The export contract lives in
`tests/test_export_labels.py` and is untouched: terminal verdicts only, and an
unreadable label raises rather than being written as `is_fraud=0`.

THE INTERESTING RISK IS NOT THE ARGUMENTS, IT IS THE JOIN
---------------------------------------------------------
Handing `--out` to a function that takes an `out_path` is trivial. What can
actually go wrong is the SELECT that feeds it: `transactions` owns
`created_at` while the CSV column is `timestamp`, the alert owns `score` while
the CSV column is `alert_score`, and `status` is not an exported column at all
-- it is the second terminal-state gate, and a query that fails to project it
yields a silent, plausible-looking, EMPTY file. `write_label_csv`'s own
docstring names that failure mode. So the field mapping is asserted here against
seeded rows, and the gates are asserted on the rows that actually come back.

PORTABILITY, STATED RATHER THAN GLOSSED
--------------------------------------
These tests run against a scratch SQLite database, not PostgreSQL. The SELECT
is written with the ORM's `select()` and `==`/`.is_(None)` operators, so
SQLAlchemy emits portable SQL and no PostgreSQL-only syntax is involved. The
shim that makes it possible is `_render_pg_uuid_on_sqlite`, copied from
`tests/migrations/test_analyst_label_column.py`: the models declare
`postgresql.UUID`, which SQLite cannot compile. Two SQLite-only differences are
worth naming rather than hiding:

1. `BaseModel.created_at` uses `server_default=func.now()`, and SQLite renders
   that as a naive UTC string while PostgreSQL returns a TIMESTAMPTZ-aware
   datetime. That is why the timestamp assertions below check the instant and
   not the tzinfo -- asserting tz-awareness here would pin SQLite's behaviour
   and fail on the database that actually runs in production.
2. `amount` is `NUMERIC(12, 2)`. Both drivers hand it back as `Decimal` here,
   and that is what keeps the two decimal places in `str()`.

What these tests do NOT prove is that a real PostgreSQL deployment returns the
same values; they prove the wiring. The end-to-end run against scratch SQLite
in the verification step is a wiring proof too, and is labelled as one.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

# Registering the same (type, dialect) handler in two modules is harmless: the
# handler is stateless and the behaviour is identical, so whichever module is
# imported last wins and the answer is the same. Imported here rather than
# borrowed from the migrations test so this file does not depend on collection
# order.
import src.models  # noqa: F401  (registers every model on Base.metadata)
from scripts.export_labels import (
    DEFAULT_OUT_PATH,
    EXPORT_COLUMNS,
    build_parser,
    main,
)
from src.core.database import Base
from src.models.fraud_alert import AlertStatus, FraudAlert
from src.models.transaction import Transaction
from src.models.user import User


@compiles(PG_UUID, "sqlite")
def _render_pg_uuid_on_sqlite(type_, compiler, **kw):
    """Render PostgreSQL UUID as CHAR(32) so the models load on SQLite."""
    return "CHAR(32)"


REVIEWED_AT = datetime(2026, 10, 4, 9, 30, tzinfo=timezone.utc)


def _alert(
    *,
    status: str,
    label: str | None,
    amount: str,
    merchant: str = "Electronics Store",
    category: str | None = "retail",
    score: float = 91.5,
    threshold: float = 70.0,
) -> tuple[FraudAlert, Transaction]:
    """One alert and the transaction it points at, ready to be added to a session."""
    user_id, txn_id = uuid.uuid4(), uuid.uuid4()
    txn = Transaction(
        id=txn_id,
        amount=Decimal(amount),
        currency="EUR",
        merchant_name=merchant,
        merchant_category=category,
        card_last4="4242",
        user_id=user_id,
        created_at=datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc),
    )
    alert = FraudAlert(
        transaction_id=txn_id,
        status=status,
        score=score,
        threshold=threshold,
        classification="high",
        analyst_label=label,
        reviewed_by=user_id,
        reviewed_at=REVIEWED_AT if label else None,
    )
    return alert, txn


async def _seed(db_path: Path) -> None:
    """Create the schema and load one alert per interesting lifecycle state.

    The five rows are the whole export decision, so they are all present at
    once: two terminal verdicts that must be written, and three rows that each
    fail a gate for a different reason. If the query ever widens, the count
    moves.
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(User(username="analyst", email="a@x.io", hashed_password="x"))
        # Terminal: two verdicts, one each way. Both must be exported.
        pairs = [
            _alert(status=AlertStatus.RESOLVED, label="confirmed_fraud", amount="1899.00"),
            _alert(status=AlertStatus.RESOLVED, label="false_positive", amount="12.50"),
            # Reverted: `revert` leaves the label in place, so this row has a
            # verdict that somebody took back. Status is the only thing left
            # that says so.
            _alert(status=AlertStatus.OPEN, label="confirmed_fraud", amount="5000.00"),
            # Reviewed: carries a label but is not a terminal lifecycle state.
            _alert(status=AlertStatus.REVIEWED, label="false_positive", amount="75.00"),
            # Terminal but unlabelled: NULL means nobody judged this.
            _alert(status=AlertStatus.RESOLVED, label=None, amount="99.99"),
        ]
        for alert, txn in pairs:
            session.add_all([alert, txn])
        await session.commit()
    await engine.dispose()


def _read(path: Path) -> list[dict]:
    with open(path, "r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _instant(text: str) -> datetime:
    """Parse an exported ISO-8601 cell, treating a naive value as UTC.

    Mirrors how the two databases differ: PostgreSQL's asyncpg returns
    timezone-aware datetimes for `TIMESTAMPTZ`, SQLite returns naive ones, and
    `write_label_csv` renders whichever it was handed with `isoformat()`.
    Normalising to UTC before comparing is what lets the equivalence proof
    assert on the instant without either driver deciding the outcome.
    """
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


class TestTheArgumentsAnOperatorGets:
    """`--help` has to be enough to run this without reading the source."""

    def test_the_parser_is_returned_for_reuse(self):
        assert isinstance(build_parser(), argparse.ArgumentParser)

    def test_the_default_output_path_is_a_documented_location(self):
        """The default is `data/`, where this project already keeps CSVs.

        Asserted as a name rather than a literal so the check cannot rot, and
        asserted as a `.csv` under a directory so it cannot quietly become a
        path in the repo root where it would show up in `git status`.
        """
        assert DEFAULT_OUT_PATH.suffix == ".csv"
        assert DEFAULT_OUT_PATH.parent.name == "data"
        assert not DEFAULT_OUT_PATH.is_absolute(), (
            "the default must resolve inside the checkout, not depend on the "
            "operator's working directory"
        )

    def test_an_out_of_the_box_invocation_uses_the_default_path(self):
        args = build_parser().parse_args([])
        assert args.out == DEFAULT_OUT_PATH
        assert args.db_url is None, (
            "no --db-url must mean 'use settings', not 'guess a URL'"
        )

    def test_out_and_db_url_are_accepted(self, tmp_path):
        target = tmp_path / "labels.csv"
        args = build_parser().parse_args(
            ["--out", str(target), "--db-url", "sqlite+aiosqlite:///x.db"]
        )
        assert args.out == target
        assert args.db_url == "sqlite+aiosqlite:///x.db"

    def test_help_documents_the_filter_and_the_refusal(self, capsys):
        """`--help` states the terminal-verdict filter AND the refusal.

        Both, because both are the things an operator gets wrong. Without the
        filter in the help text, an empty file is unexplainable. Without the
        refusal, the natural next move is to point the trainer at the output --
        and the file is shaped so nearly enough that nobody would think twice.
        """
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--help"])

        assert exc.value.code == 0
        text = capsys.readouterr().out
        assert "resolved" in text.lower()
        assert "trainer" in text.lower()
        assert "corpus_schema" in text


@pytest.mark.asyncio
class TestTheRowsThatActuallyComeOut:
    """End-to-end: a seeded database in, a CSV on disk out."""

    async def _export(self, db_path: Path, out: Path) -> int:
        return await main([
            "--db-url", f"sqlite+aiosqlite:///{db_path}",
            "--out", str(out),
        ])

    async def test_only_terminal_verdicts_are_written(self, tmp_path):
        """Two in, two out: the open, reviewed and unlabelled rows all go.

        The count is the assertion. Each excluded row is well formed and has
        something to say -- two of them even carry a label -- so asserting on
        label contents would pass while a reverted verdict leaked through.
        """
        db_path, out = tmp_path / "seed.db", tmp_path / "labels.csv"
        await _seed(db_path)

        written = await self._export(db_path, out)

        assert written == 2
        assert len(_read(out)) == 2

    async def test_both_verdicts_survive_the_join(self, tmp_path):
        db_path, out = tmp_path / "seed.db", tmp_path / "labels.csv"
        await _seed(db_path)
        await self._export(db_path, out)

        assert {r["analyst_label"] for r in _read(out)} == {
            "confirmed_fraud",
            "false_positive",
        }

    async def test_the_header_is_the_documented_column_set(self, tmp_path):
        """The query projects extra columns; the CSV must not gain any.

        `status` and `id` are selected for the gates and the join. Leaking
        either into the header would change the contract that
        `tests/test_export_labels.py` pins exactly.
        """
        db_path, out = tmp_path / "seed.db", tmp_path / "labels.csv"
        await _seed(db_path)
        await self._export(db_path, out)

        with open(out, "r", newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))

        assert tuple(header) == EXPORT_COLUMNS
        assert "status" not in header
        assert "corpus_schema" not in header

    async def test_the_database_columns_land_in_the_documented_csv_columns(self, tmp_path):
        """The field mapping, end to end. This is the actual wiring risk.

        Four of these pairs are renamed between the database and the CSV:
        `transactions.created_at` -> `timestamp`, `fraud_alerts.score` ->
        `alert_score`, `fraud_alerts.threshold` -> `alert_threshold`. A typo in
        a single `.label()` writes a plausible file with the wrong column, and
        nothing downstream notices until a model is trained on it.
        """
        db_path, out = tmp_path / "seed.db", tmp_path / "labels.csv"
        await _seed(db_path)
        await self._export(db_path, out)

        rows = {r["analyst_label"]: r for r in _read(out)}
        fraud = rows["confirmed_fraud"]

        assert fraud["amount"] == "1899.00", "NUMERIC must keep its two decimals"
        assert fraud["currency"] == "EUR"
        assert fraud["merchant_name"] == "Electronics Store"
        assert fraud["alert_score"] == "91.5", "fraud_alerts.score, not a feature"
        assert fraud["alert_threshold"] == "70.0"
        assert fraud["reviewed_at"].startswith("2026-10-04T09:30:00")
        assert fraud["timestamp"].startswith("2026-10-03T14:00:00"), (
            "timestamp is transactions.created_at, ISO-8601"
        )
        assert fraud["is_fraud"] == "1"
        assert rows["false_positive"]["is_fraud"] == "0"

    async def test_a_null_category_is_an_empty_cell(self, tmp_path):
        """The nullable column stays empty rather than becoming "None"."""
        db_path, out = tmp_path / "seed.db", tmp_path / "labels.csv"
        await _seed(db_path)

        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            alert, txn = _alert(
                status=AlertStatus.RESOLVED, label="false_positive", amount="1.00"
            )
            txn.merchant_category = None
            session.add_all([alert, txn])
            await session.commit()
        await engine.dispose()

        await self._export(db_path, out)
        # Selected by amount, not by position: the export is ordered by review
        # time then id, and the seeded rows share a review time, so row order
        # is not something this test should depend on.
        null_category = [r for r in _read(out) if r["amount"] == "1.00"]
        assert len(null_category) == 1
        assert null_category[0]["merchant_category"] == ""

    async def test_the_file_is_byte_identical_to_what_the_writer_alone_writes(self, tmp_path):
        """The equivalence proof: CLI in, hand-built rows in, same bytes.

        The two paths are genuinely different -- one reads a SQLite database
        through the SELECT, the other is a literal list of dicts -- so this
        catches a mis-mapped column rather than restating the query against
        itself.
        """
        from scripts.export_labels import write_label_csv

        db_path, out, control = tmp_path / "seed.db", tmp_path / "out.csv", tmp_path / "ctl.csv"
        await _seed(db_path)
        await self._export(db_path, out)

        stamp = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)
        base = {
            "currency": "EUR",
            "merchant_name": "Electronics Store",
            "merchant_category": "retail",
            "timestamp": stamp,
            "alert_threshold": 70.0,
            "reviewed_at": REVIEWED_AT,
            "status": AlertStatus.RESOLVED,
            "alert_score": 91.5,
        }
        write_label_csv([
            {
                **base,
                "transaction_id": "TID-1",
                "user_id": "UID-1",
                "amount": Decimal("1899.00"),
                "analyst_label": "confirmed_fraud",
                "reviewed_by": "UID-R",
            },
            {
                **base,
                "transaction_id": "TID-2",
                "user_id": "UID-2",
                "amount": Decimal("12.50"),
                "analyst_label": "false_positive",
                "reviewed_by": "UID-R",
            },
        ], control)

        # The transaction ids are random UUIDs seeded per row, so the keys are
        # compared for presence and every other column for value.
        produced = _read(out)
        expected = _read(control)
        assert len(produced) == len(expected) == 2

        # TIMESTAMPS ARE COMPARED AS INSTANTS, NOT AS STRINGS, and that is not
        # a convenience. `created_at` has `server_default=func.now()`, which
        # SQLite renders as a naive UTC string, so the database-sourced
        # timestamp is `2026-10-03T14:00:00` while the hand-built control row is
        # `2026-10-03T14:00:00+00:00`. Same instant, different text, and only
        # because of the scratch driver: PostgreSQL returns TIMESTAMPTZ-aware
        # datetimes and both sides would carry `+00:00`. Asserting byte-identity
        # here would pin SQLite's behaviour and fail against the database that
        # actually runs in production, so the instant is what gets compared and
        # the SQLite divergence stays documented instead of hidden.
        timestamp_columns = {"timestamp", "reviewed_at"}
        for got, want in zip(sorted(produced, key=lambda r: r["amount"]),
                             sorted(expected, key=lambda r: r["amount"])):
            for column in EXPORT_COLUMNS:
                if column in timestamp_columns:
                    assert _instant(got[column]) == _instant(want[column]), column
                elif column == "transaction_id":
                    assert got[column], "the join must project a transaction id"
                elif column in ("user_id", "reviewed_by"):
                    assert got[column], f"{column} must come from the database"
                else:
                    assert got[column] == want[column], f"{column} disagrees"

    async def test_an_empty_database_still_writes_a_parseable_file(self, tmp_path):
        """Zero resolved verdicts is a header, not a crash and not an empty file.

        `write_label_csv` already guarantees this; the CLI must not turn it into
        an exception on the way past.
        """
        db_path, out = tmp_path / "seed.db", tmp_path / "labels.csv"
        await _seed(db_path)

        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.execute(FraudAlert.__table__.delete())
            await conn.execute(Transaction.__table__.delete())
        await engine.dispose()

        written = await self._export(db_path, out)

        assert written == 0
        with open(out, "r", newline="", encoding="utf-8") as handle:
            assert tuple(next(csv.reader(handle))) == EXPORT_COLUMNS


@pytest.mark.asyncio
class TestTheRefusalsStillStandBehindTheCLI:
    """The exporter's refusals are the reason it exists. The CLI must not
    route around them."""

    async def test_the_trainer_still_refuses_what_the_cli_wrote(self, tmp_path):
        """The real loader, on the file the real CLI produced.

        This is the contract with the next person: the export is deliberately
        not a training corpus. If a future change to the CLI ever stamps
        `corpus_schema`, this fails, because it runs `_load_synthetic_csv`
        itself instead of inspecting the header.
        """
        from scripts.train_xgboost_aligned import CORPUS_SCHEMA, _load_synthetic_csv

        db_path, out = tmp_path / "seed.db", tmp_path / "labels.csv"
        await _seed(db_path)
        assert await main([
            "--db-url", f"sqlite+aiosqlite:///{db_path}", "--out", str(out)
        ]) == 2

        with pytest.raises(ValueError) as exc:
            _load_synthetic_csv(str(out))

        assert CORPUS_SCHEMA in str(exc.value)

    async def test_an_unreadable_label_cannot_reach_the_csv(self, tmp_path):
        """The two layers, and which one stops this row first.

        The CHECK constraint refuses to store a label outside the vocabulary,
        so that is what an operator actually hits at insert time -- and it is
        worth pinning, because the exporter's own refusal is the second layer
        and only reachable on a database the migration has not reached.
        """
        from sqlalchemy.exc import IntegrityError

        db_path = tmp_path / "seed.db"
        await _seed(db_path)

        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        maker = async_sessionmaker(engine, expire_on_commit=False)
        with pytest.raises(IntegrityError):
            async with maker() as session:
                alert, txn = _alert(
                    status=AlertStatus.RESOLVED,
                    label="confirmed_fraudd",
                    amount="10.00",
                )
                session.add_all([alert, txn])
                await session.commit()
        await engine.dispose()

        # And whatever IS in the database exports as the two real verdicts.
        out = tmp_path / "labels.csv"
        assert await main([
            "--db-url", f"sqlite+aiosqlite:///{db_path}", "--out", str(out)
        ]) == 2


def test_the_module_entry_point_is_runnable_as_a_script():
    """`python scripts/export_labels.py --help` is the operator's first command.

    Run as a subprocess, in its own process, because that is the only way to
    prove the import path and the `sys.path` shim work: the other tests import
    `scripts.export_labels` from an already-configured repo root.
    """
    proc = _run_script(["--help"])

    assert proc.returncode == 0, proc.stderr
    assert "--out" in proc.stdout
    assert "--db-url" in proc.stdout


def test_the_entry_point_actually_exports_when_run_as_a_script(tmp_path):
    """A real end-to-end run in a real process, not an import.

    `--help` alone is not enough to prove this works, and the difference is not
    academic. `if __name__ == "__main__"` runs in the middle of the module if it
    is placed above the function definitions rather than at the bottom: the
    script then calls `main()` before `write_label_csv` exists, and dies with
    `NameError`. Every other test in this file IMPORTS the module, where that
    block never executes and the bug is invisible, and `--help` exits before
    reaching it. Only a subprocess that runs the whole command finds it.
    """
    db_path, out = tmp_path / "seed.db", tmp_path / "labels.csv"
    asyncio.run(_seed(db_path))

    proc = _run_script([
        "--db-url", f"sqlite+aiosqlite:///{db_path}",
        "--out", str(out),
    ])

    assert proc.returncode == 0, (
        f"the script must export when run, not only when imported.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert len(_read(out)) == 2


def _run_script(argv: list[str]):
    """Run `scripts/export_labels.py` as a subprocess from the repo root."""
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "export_labels.py"), *argv],
        capture_output=True,
        text=True,
        cwd=root,
        timeout=180,
    )


def test_the_exporter_still_never_reaches_the_trainer():
    """The static guarantee, restated for the version with a CLI.

    The point of adding an entry point is that the module can now be run. A
    module that can be run is a module that can accidentally do something
    irreversible, so the ban on importing or shelling out to the trainer is
    re-checked here against the same AST walk the original test uses.
    """
    import ast

    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "export_labels.py"
    ).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    for forbidden in ("train_xgboost_aligned", "subprocess", "xgboost", "sklearn"):
        assert not any(forbidden in name for name in imported), sorted(imported)

    referenced = {
        n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)
    } | {n.attr for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Attribute)}
    assert "CORPUS_SCHEMA" not in referenced


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())