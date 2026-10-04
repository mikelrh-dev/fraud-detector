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

import csv
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.fraud_alert import ANALYST_LABEL_VALUES, AlertStatus

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

    with open(path, "w", newline="", encoding="utf-8") as handle:
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

    return written
