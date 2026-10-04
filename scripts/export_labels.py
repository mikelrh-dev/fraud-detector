"""Export analyst verdicts from `fraud_alerts` as a labelled CSV.

THIS SCRIPT DOES NOT RETRAIN ANYTHING. It reads rows and writes a file. It does
not import the trainer, does not touch `CORPUS_SCHEMA`, and does not shell out.
`tests/test_export_labels.py` asserts all three statically, because the failure
mode here is a model that nobody can reproduce and nobody was warned about.

WHY THERE IS NO `corpus_schema` COLUMN
--------------------------------------
`scripts/train_xgboost_aligned.py::_load_synthetic_csv` refuses any corpus it
did not write, and the refusal is a hard error raised before a single row is
parsed. It exists because that loader once read a foreign corpus in silence and
produced a model with three features that each separated the classes on their
own at ROC-AUC 1.0000, plus a fraud rate 5x the training corpus's.

The columns here line up closely enough that stamping `corpus_schema` onto the
output would make the trainer accept this file immediately. That is exactly why
it is not done. The stamp asserts that a corpus of analyst verdicts on
review-band transactions has been checked against the trainer's schema, and
nobody has checked it. Writing the stamp would convert an open question into a
false assurance, and it would reopen the hole the refusal was built to close.

So the export is deliberately refused by the trainer, and the next unit's
decision -- what a real labelled corpus has to be checked for -- stays a
decision. `test_the_trainer_still_refuses_an_exported_file` runs the real loader
against real output so this stays true rather than merely intended.

FIELD MAPPING
-------------
Every column, its source, and what it means. The trainer's own names are used
where it has one, so the file is directly consumable once the corpus question
above is answered rather than needing a rename.

    transaction_id   fraud_alerts.transaction_id. Provenance key. Unused by
                     the trainer's feature engine; it is how a row in this file
                     is traced back to the alert an analyst actually looked at.

    user_id          transactions.user_id. The trainer reads this as an opaque
                     string and derives the per-user aggregates below.

    amount           transactions.amount (`NUMERIC(12, 2)`). Read by the trainer
                     by name, so a rename here is a KeyError there. Written as
                     the plain decimal string, never as a float.

    currency         transactions.currency (`CHAR(3)`). Carried for the analyst
                     reading the file. Not a trainer feature.

    merchant_name    transactions.merchant_name. Read by name, and it is the
                     field that decides the merchant risk features.

    merchant_category transactions.merchant_category. NULLABLE in the
                     database, and an empty cell means "no category" rather
                     than the four characters `None`, which the feature engine
                     would treat as a category name like any other.

    timestamp        transactions.created_at, ISO-8601 UTC. Named `timestamp`
                     because that is what `_load_synthetic_csv` reads; this is
                     the one place the export borrows a name instead of
                     inventing one.

    is_fraud         DERIVED, not stored: 1 for `confirmed_fraud`, 0 for
                     `false_positive`. This is the projection of the analyst's
                     verdict onto the trainer's label vocabulary.

    analyst_label    fraud_alerts.analyst_label, verbatim. The provenance of
                     `is_fraud`. Kept so a row can be audited back to the
                     verdict that produced it, and so a consumer can tell a
                     real judgement from anything else that later writes an
                     `is_fraud`.

    alert_score      fraud_alerts.score. Diagnostic. What the model scored at
                     alert time, NOT a feature -- feeding it back would leak
                     the decision into the training set.

    alert_threshold  fraud_alerts.threshold. Diagnostic, for the same reason.

    reviewed_by      fraud_alerts.reviewed_by. Who judged. A label with no
                     reviewer cannot be audited.

    reviewed_at      fraud_alerts.reviewed_at, ISO-8601 UTC. When it was
                     judged. Lets the corpus be aged, and lets a policy change
                     later be evaluated against when it took effect.

DELIBERATELY ABSENT
-------------------
`user_avg_amount`, `user_std_amount`, `velocity_5min` and `velocity_1h` are
per-user aggregates the trainer reads with a `"0"` fallback. They are not on
the alert row and this script does NOT fabricate them.

This is not an omission to be tidied up later -- it is a known, deliberate gap,
and `_save_synthetic_csv`'s docstring records what a column of fabricated zeroes
actually does: `amount_vs_user_std` becomes a constant-zero feature for every
row of the training set while the deployed artifact still carries weight on
that dead column. Whichever way the corpus question above is answered, these
have to be recomputed from the transaction history by the same code path that
computes them at serving time, or omitted from the corpus entirely. They must
not be written as zeroes.

A WARNING ABOUT WHAT THESE ROWS ARE
-----------------------------------
This is every alert an analyst judged, which is a biased sample: it contains
transactions somebody found worth looking at, and nothing else. It is not a
representative corpus, it is not balanced, and the review band's coverage rules
are unchanged by this script. No threshold, rule, fusion weight or model is
touched anywhere in this file. Whether these rows are worth training on, and
in what proportion, is a decision for a later unit that has to argue it from
label volume rather than from this script existing.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import tempfile
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

# Added before the `src` imports so the file runs as a script from any working
# directory, exactly as `scripts/init_db.py` and `scripts/seed_demo_data.py`
# do. Without it, `python scripts/export_labels.py --help` -- the first command
# an operator will ever run -- dies with `ModuleNotFoundError: No module named
# 'src'`. The tests import this module from the repo root, so they would never
# have caught it; `tests/test_export_labels_cli.py` runs it as a subprocess
# precisely to keep that honest.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.database import async_session_maker
from src.models.fraud_alert import ANALYST_LABEL_VALUES, AlertStatus, FraudAlert
from src.models.transaction import Transaction

#: The header, in order. Pinned by `test_columns_are_exactly_the_documented_set`
#: so neither an added nor a renamed column can happen without a test change.
EXPORT_COLUMNS = (
    "transaction_id",
    "user_id",
    "amount",
    "currency",
    "merchant_name",
    "merchant_category",
    "timestamp",
    "is_fraud",
    "analyst_label",
    "alert_score",
    "alert_threshold",
    "reviewed_by",
    "reviewed_at",
)

#: The analyst verdict projected onto the trainer's label vocabulary. Written
#: out rather than derived from `ANALYST_LABEL_VALUES` because the projection
#: is a decision: it asserts that "false positive" means the label 0. A verdict
#: added to the model has to be added here too, deliberately, and
#: `test_a_label_outside_the_vocabulary_is_refused` is what enforces it.
_LABEL_TO_IS_FRAUD = {
    "confirmed_fraud": "1",
    "false_positive": "0",
}


#: Where the export lands when the operator does not say. `data/` already holds
#: this project's other CSV (`data/synthetic_transactions.csv`, written by the
#: trainer), so it needs no new convention and no .gitignore entry.
DEFAULT_OUT_PATH = Path("data") / "analyst_labels.csv"

#: The alert states that count as a settled verdict. See `AlertStatus`.
_TERMINAL = AlertStatus.RESOLVED.value

_FILTER_NOTE = """\
WHAT GETS EXPORTED
  Only alerts whose status is 'resolved' AND whose analyst_label is not NULL.
  Both gates are terminal-state gates and both must hold:

    * NULL label means nobody judged the row, so there is no verdict to
      project onto is_fraud.
    * Status must be 'resolved'. 'revert' moves an alert back to 'open' and
      deliberately LEAVES analyst_label in place, so a reverted row still
      carries a verdict somebody took back. Its label alone cannot tell you
      that; the status can.

  So 'open' and 'reviewed' rows are excluded even when they carry a label. An
  analyst_label outside the vocabulary raises instead of being written as
  is_fraud=0 -- a false positive recorded as fact is the worst possible output.

THIS FILE IS NOT A TRAINING CORPUS
  The trainer (scripts/train_xgboost_aligned.py) deliberately refuses this
  output. Its loader raises unless a corpus carries the corpus_schema stamp the
  trainer itself wrote. This export does NOT write that column and does NOT set
  it. Stamping it would assert that a corpus of analyst verdicts has been
  checked against a schema nobody has checked it against, re-opening the hole
  the refusal exists to close. Pointing the trainer at this file is the one
  mistake this command invites, because the columns line up almost exactly.
"""


def build_parser() -> argparse.ArgumentParser:
    """The operator-facing argument surface.

    `--help` carries the two contracts an operator cannot infer from the output
    file: what is filtered out, and that the trainer will refuse the result.
    Both are in the epilog rather than in per-flag help so that `--help` reads
    as one explanation rather than three fragments.
    """
    parser = argparse.ArgumentParser(
        prog="export_labels.py",
        description=(
            "Export resolved analyst verdicts from fraud_alerts as a labelled CSV. "
            "Reads the database and writes a file. Does not retrain anything and "
            "does not shell out."
        ),
        epilog=_FILTER_NOTE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_PATH,
        help=(
            "Path of the CSV to write; parent directories are created. "
            f"Default: {DEFAULT_OUT_PATH.as_posix()}"
        ),
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help=(
            "SQLAlchemy async URL to read from. Defaults to the application's "
            "configured database (DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME, "
            "or the .env file). Supply one to export from another database, "
            "e.g. a read replica or a snapshot."
        ),
    )
    return parser


def _select_resolved_alerts() -> Any:
    """Build the SELECT behind the export.

    Every CSV column is projected under the name the writer reads, and two
    columns are projected that the CSV does NOT contain:

        * `status` is not an exported column. It is the second terminal-state
          gate, and `write_label_csv` drops any row whose status is not
          resolved. A query that omitted it would produce a header-only file
          that looks like an empty database.
        * `Transaction.id` is the CSV's `transaction_id`, which lives on the
          alert as a foreign key.

    The WHERE clause is the first gate, and it is deliberately NOT a third one.
    It filters on label-not-null and terminal status -- the same two rules
    `write_label_csv` applies -- and adds nothing. In particular it does not
    restrict `analyst_label` to `ANALYST_LABEL_VALUES`: an unreadable label has
    to reach the writer to be raised there, and a query that silently dropped
    it would turn a loud refusal into a quiet omission. Soft-deleted rows are
    likewise left in, because soft delete does not un-judge a transaction that
    an analyst already decided on.

    Ordering is by review time then id so two runs over an unchanged database
    produce byte-identical files, which is what makes the export diffable.
    """
    return (
        select(
            Transaction.id.label("transaction_id"),
            Transaction.user_id.label("user_id"),
            Transaction.amount.label("amount"),
            Transaction.currency.label("currency"),
            Transaction.merchant_name.label("merchant_name"),
            Transaction.merchant_category.label("merchant_category"),
            Transaction.created_at.label("timestamp"),
            FraudAlert.analyst_label.label("analyst_label"),
            FraudAlert.score.label("alert_score"),
            FraudAlert.threshold.label("alert_threshold"),
            FraudAlert.reviewed_by.label("reviewed_by"),
            FraudAlert.reviewed_at.label("reviewed_at"),
            FraudAlert.status.label("status"),
        )
        .join(FraudAlert, FraudAlert.transaction_id == Transaction.id)
        .where(
            FraudAlert.analyst_label.is_not(None),
            FraudAlert.status == _TERMINAL,
        )
        .order_by(FraudAlert.reviewed_at, Transaction.id)
    )


async def _resolved_alert_rows(session: Any) -> list[dict[str, Any]]:
    """Fetch the rows the writer will filter again. Read-only; never commits."""
    result = await session.execute(_select_resolved_alerts())
    return [dict(mapping) for mapping in result.mappings()]


def _session_maker_for(db_url: str | None) -> tuple[Any, Any]:
    """Return `(session_maker, engine_to_dispose)`.

    With no `--db-url` the application's own `async_session_maker` is reused, so
    the script connects with the same pool settings, timeouts and credentials
    as the API instead of standing up a second, differently-configured pool.
    With one, a throwaway `NullPool` engine is built and disposed afterwards: a
    one-shot export should not leave a pool sitting on a database it was only
    asked to read.

    Async rather than sync: `AGENTS.md` mandates async everywhere and
    `scripts/seed_demo_data.py` is the house pattern for scripts that touch
    rows. `scripts/init_db.py`'s synchronous engine is DDL-only.
    """
    if db_url is None:
        return async_session_maker, None
    engine = create_async_engine(db_url, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def main(argv: Iterable[str] | None = None) -> int:
    """Run the export. Returns the number of rows written.

    The row count, not an exit code: zero rows is a real answer ("nobody has
    resolved a labelled alert yet") and not a failure, so it must not be
    reported as one. The count is also what the tests assert against. The
    `__main__` block deliberately discards it, because a non-zero return would
    become a non-zero process exit.

    The `ValueError` from an unreadable label is deliberately NOT caught: it
    propagates so the operator gets a traceback and a non-zero exit rather than
    a file that quietly omits rows.
    """
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    session_maker, owned_engine = _session_maker_for(args.db_url)

    try:
        async with session_maker() as session:
            rows = await _resolved_alert_rows(session)
            written = write_label_csv(rows, args.out)
    finally:
        if owned_engine is not None:
            await owned_engine.dispose()

    print(f"Wrote {written} resolved verdict(s) to {args.out}")
    if written == 0:
        # An empty export is indistinguishable from a broken one unless the
        # script says which it was.
        print(
            "No resolved, labelled alerts found. The file has a header and no "
            "rows -- that is a real answer, not a failure."
        )
    else:
        print(
            "The trainer refuses this file by design; it is not a training "
            "corpus."
        )
    return written


def _iso(value: Any) -> str:
    """Render a datetime as ISO-8601, and an absent value as an empty cell.

    `str(None)` would write the four characters `None` into a corpus column,
    which every consumer then has to special-case. An empty cell is honest.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _text(value: Any) -> str:
    """Render a scalar for CSV. `None` becomes an empty cell, never `"None"`."""
    if value is None:
        return ""
    return str(value)


def write_label_csv(rows: Iterable[Mapping[str, Any]], out_path: str | Path) -> int:
    """Write analyst-labelled rows to `out_path` as CSV. Returns the row count.

    TWO GATES, AND BOTH ARE TERMINAL-STATE GATES
    ----------------------------------------------
    Rows whose `analyst_label` is NULL are not written: NULL means "nobody
    judged this", and projecting it onto `is_fraud` would mean inventing a
    verdict.

    Rows whose `status` is not `AlertStatus.RESOLVED` are not written either.
    `revert` moves an alert back to `open` and deliberately leaves
    `analyst_label` in place, so a reverted alert still carries the verdict
    somebody took back. The NULL filter cannot see that: the row has a label, a
    reviewer and a timestamp, and looks exactly like a settled verdict. Requiring
    the resolved status is what stops a contested verdict being written out as
    fact, with `is_fraud` already decided.

    Callers query for labelled, resolved rows; this is the second gate, so a
    caller whose WHERE clause is wrong still cannot export a fiction.

    A missing `status` key is therefore NOT terminal, and the row is dropped
    rather than exported on the strength of its label alone. Note what that
    costs: a caller that does not project `status` gets a header-only file, and
    an empty file is not obviously wrong -- it is why this function takes rows
    that already carry the lifecycle state rather than a query it builds itself.

    A label outside `ANALYST_LABEL_VALUES` raises rather than defaulting. The
    database's CHECK constraint refuses to store one, but this script is also
    run against databases the migration has not reached, and a row exported as
    `"0"` because its label was unreadable is the worst possible outcome: a
    false positive taught to the model as fact.
    """
    written = 0
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic destination: rows stream into a sibling temp file and only a
    # fully-validated run replaces the destination. A label outside the
    # vocabulary raises mid-loop; without this, the already-flushed rows
    # would remain as a truncated file indistinguishable in shape from a
    # complete one. On error the temp file is removed and a previous
    # complete export at `path` is left untouched.
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(EXPORT_COLUMNS))
            writer.writeheader()

            for row in rows:
                label = row.get("analyst_label")
                if label is None:
                    continue
                # Compared against the enum member, not the literal "resolved":
                # `AlertStatus` is a `str` enum, so this is true for both the raw
                # column value and an ORM instance that has not been str()'d.
                if row.get("status") != AlertStatus.RESOLVED:
                    continue
                if label not in _LABEL_TO_IS_FRAUD:
                    raise ValueError(
                        f"refusing to export analyst_label={label!r}; the documented "
                        f"vocabulary is {tuple(ANALYST_LABEL_VALUES)}. A label this "
                        f"script cannot read would be written as is_fraud=0, which "
                        f"is a false positive recorded as fact."
                    )

                amount = row.get("amount")
                writer.writerow({
                    "transaction_id": _text(row.get("transaction_id")),
                    "user_id": _text(row.get("user_id")),
                    # NUMERIC comes back from the driver as Decimal. `str()` on a
                    # Decimal keeps the two decimal places; routing it through
                    # `float` first would lose them and is what
                    # `tests/test_amount_precision.py` exists about.
                    "amount": "" if amount is None else str(amount),
                    "currency": _text(row.get("currency")),
                    "merchant_name": _text(row.get("merchant_name")),
                    "merchant_category": _text(row.get("merchant_category")),
                    "timestamp": _iso(row.get("timestamp")),
                    "is_fraud": _LABEL_TO_IS_FRAUD[label],
                    "analyst_label": label,
                    "alert_score": _text(row.get("alert_score")),
                    "alert_threshold": _text(row.get("alert_threshold")),
                    "reviewed_by": _text(row.get("reviewed_by")),
                    "reviewed_at": _iso(row.get("reviewed_at")),
                })
                written += 1
    except BaseException:
        os.unlink(tmp_name)
        raise

    os.replace(tmp_name, path)
    return written


# LAST IN THE FILE, deliberately. An `if __name__ == "__main__"` block executes
# where it sits, so placed above the definitions it calls `main()` while
# `write_label_csv` is still unbound and the script dies with `NameError` on a
# real run -- while every test that IMPORTS this module passes, because the
# block never runs. `tests/test_export_labels_cli.py` runs the command in a
# subprocess to keep that honest.
if __name__ == "__main__":  # pragma: no cover - exercised via subprocess
    # The row count is not an exit code, so it is discarded. An exception
    # escaping here -- an unreadable label, an unreachable database -- is what
    # makes the command fail.
    asyncio.run(main())
