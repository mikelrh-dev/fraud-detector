"""Analyst verdicts leave the database as a labelled corpus, and go no further.

WHAT THIS FILE IS FOR
---------------------
Persisting a verdict is only half a feedback loop. The other half is getting it
out of the database in a form something can learn from, which is
`scripts/export_labels.py`. The interesting property of that script is not what
it writes -- it is what it refuses to write.

THE ASSERTION THAT MATTERS MOST IS THE REFUSAL
-----------------------------------------------
`scripts/train_xgboost_aligned.py` carries a hard refusal in
`_load_synthetic_csv`, added after the loader was found reading a corpus it did
not write: three of that corpus's ten features each separated the classes on
their own at ROC-AUC 1.0000, and its fraud rate was 4.81% against the training
corpus's 0.96%. The guard exists so a foreign vocabulary cannot silently
retrain the model.

So an exported label file is NOT a training corpus, and the temptation is to
make it one -- the columns line up closely enough that stamping
`corpus_schema=trainer_v4` on the output would make the trainer accept it
immediately. That would be the single worst line in this change. It would
re-open the exact hole the refusal was built to close, by asserting that a
corpus of analyst verdicts on review-band transactions has been checked against
a schema it has never seen. So the exporter deliberately emits no
`corpus_schema` column, and `test_the_trainer_still_refuses_an_exported_file`
proves it by running the real loader against real output.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
No retraining, no threshold search, no model comparison, and no claim that the
exported rows are a good corpus. They are whatever analysts happened to judge,
which is a biased sample of transactions they found worth looking at. Any
decision about what to do with that is a separate unit, and it needs a volume
argument this file does not make.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from scripts.export_labels import EXPORT_COLUMNS, write_label_csv
from src.models.fraud_alert import ANALYST_LABEL_VALUES, AlertStatus

REVIEWED_AT = datetime(2026, 10, 4, 9, 30, tzinfo=timezone.utc)


def _row(
    *,
    label: str | None,
    amount: str = "250.00",
    merchant_name: str = "Electronics Store",
    merchant_category: str | None = "retail",
    score: float = 91.5,
    threshold: float = 70.0,
    reviewed_by: str | None = "analyst-1",
    reviewed_at: datetime | None = REVIEWED_AT,
    user_id: str = "user-1",
    transaction_id: str = "txn-1",
    status: str = "resolved",
) -> dict:
    """One exported row.

    `amount` is built from `Decimal` and `category` is allowed to be None on
    purpose: both mirror `transactions`, where `amount` is `NUMERIC(12, 2)`
    and `merchant_category` is nullable. A CSV writer that calls `str()` on a
    `None` category writes the literal "None" into a training corpus, which is
    a category the model will happily learn.
    """
    return {
        "transaction_id": transaction_id,
        "user_id": user_id,
        "amount": Decimal(amount),
        "currency": "USD",
        "merchant_name": merchant_name,
        "merchant_category": merchant_category,
        "transaction_timestamp": datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc),
        "timestamp": datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc),
        "is_fraud": 1 if label == "confirmed_fraud" else 0,
        "analyst_label": label,
        "alert_score": score,
        "alert_threshold": threshold,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "status": status,
    }


@pytest.fixture()
def both_verdicts() -> list[dict]:
    return [
        _row(label="confirmed_fraud", transaction_id="txn-fraud"),
        _row(label="false_positive", transaction_id="txn-clean"),
    ]


def _read(path) -> list[dict]:
    with open(path, "r", newline="") as handle:
        return list(csv.DictReader(handle))


class TestTheExportedFile:
    def test_columns_are_exactly_the_documented_set(self, tmp_path, both_verdicts):
        """The header is pinned, so a column cannot be added silently.

        A column nobody reads is cost; a column nobody notices is missing is
        worse. Pinning the whole header means both directions need a
        deliberate edit.
        """
        out = tmp_path / "labels.csv"
        write_label_csv(both_verdicts, out)

        with open(out, "r", newline="") as handle:
            header = next(csv.reader(handle))

        assert tuple(header) == EXPORT_COLUMNS

    def test_both_verdicts_are_exported(self, tmp_path, both_verdicts):
        """Both verdicts, each mapping to the trainer's own label vocabulary."""
        out = tmp_path / "labels.csv"
        write_label_csv(both_verdicts, out)

        rows = {row["transaction_id"]: row for row in _read(out)}
        assert set(rows) == {"txn-fraud", "txn-clean"}
        assert rows["txn-fraud"]["analyst_label"] == "confirmed_fraud"
        assert rows["txn-clean"]["analyst_label"] == "false_positive"

    @pytest.mark.parametrize(
        ("label", "expected"),
        [("confirmed_fraud", "1"), ("false_positive", "0")],
    )
    def test_is_fraud_is_the_projection_of_the_verdict(
        self, tmp_path, label, expected
    ):
        """`is_fraud` is 1 for confirmed fraud and 0 for a false positive.

        Asserted for both directions on purpose. A one-directional assertion
        passes if the column is hardcoded to "1", which would export every
        false positive as a fraud and train the model on its own worst error.
        """
        out = tmp_path / "labels.csv"
        write_label_csv([_row(label=label)], out)

        assert _read(out)[0]["is_fraud"] == expected

    def test_reviewer_and_timestamp_travel_with_the_label(
        self, tmp_path, both_verdicts
    ):
        """Provenance travels with the verdict.

        A label with no reviewer cannot be audited, and one with no timestamp
        cannot be placed in time or aged. Both are on the alert row already and
        both are read here, or they are lost the moment the row is exported.
        """
        out = tmp_path / "labels.csv"
        write_label_csv(both_verdicts, out)

        row = _read(out)[0]
        assert row["reviewed_by"] == "analyst-1"
        assert row["reviewed_at"].startswith("2026-10-04T09:30")

    def test_the_feature_columns_the_trainer_reads_are_present(
        self, tmp_path, both_verdicts
    ):
        """The four columns `_load_synthetic_csv` indexes WITHOUT `.get`.

        `amount`, `merchant_name`, `merchant_category` and `timestamp` are read
        by name in the trainer's loader, so a rename on this side is a
        `KeyError` there rather than a fallback to a default. That is why the
        export carries the trainer's own column names and not this script's
        more descriptive ones: `timestamp`, not `transaction_timestamp`.

        `timestamp` is the one name this file borrows rather than invents. The
        value keeps its UTC offset: `tests/test_timestamp_timezone_normalization.py`
        exists because a naive timestamp here is a real defect, and the velocity
        features are computed from this field.
        """
        out = tmp_path / "labels.csv"
        write_label_csv(both_verdicts, out)

        row = _read(out)[0]
        assert row["amount"] == "250.00"
        assert row["merchant_name"] == "Electronics Store"
        assert row["merchant_category"] == "retail"

        parsed = datetime.fromisoformat(row["timestamp"])
        assert parsed == datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc), (
            f"timestamp round-tripped to {parsed!r}, which is not the instant "
            f"that was written. The trainer's velocity features are computed "
            f"from this column."
        )

    def test_a_null_merchant_category_is_empty_not_the_word_none(
        self, tmp_path
    ):
        """`merchant_category` is nullable in the database.

        `str(None)` writes the four characters `None` into the corpus, and the
        feature engine will treat it as a category name like any other. An
        empty cell is at least honest about there being no category.
        """
        out = tmp_path / "labels.csv"
        write_label_csv([_row(label="false_positive", merchant_category=None)], out)

        assert _read(out)[0]["merchant_category"] == ""

    def test_the_file_is_parseable_by_a_plain_csv_reader(
        self, tmp_path, both_verdicts
    ):
        """Round-trips: written here, read back with the stdlib reader.

        A quoting bug or an embedded newline in a merchant name would produce a
        file that looks fine and parses as fewer rows than were written.
        """
        out = tmp_path / "labels.csv"
        write_label_csv(both_verdicts, out)

        rows = _read(out)

        assert len(rows) == 2
        assert all(len(row) == len(EXPORT_COLUMNS) for row in rows)

    def test_a_merchant_name_with_a_comma_survives_the_round_trip(
        self, tmp_path
    ):
        """The quoting case that actually bites, and does so silently."""
        out = tmp_path / "labels.csv"
        write_label_csv(
            [_row(label="confirmed_fraud", merchant_name='Acme, Inc "Madrid"')],
            out,
        )

        assert _read(out)[0]["merchant_name"] == 'Acme, Inc "Madrid"'


class TestWhatTheExporterRefuses:
    """The negative space, which is where the risk actually lives."""

    def test_no_corpus_schema_column_is_written(self, tmp_path, both_verdicts):
        """The load stamp is absent, on purpose.

        Writing `corpus_schema=trainer_v4` would make the trainer accept this
        file immediately, and that is the whole hazard: it would assert that a
        corpus of analyst verdicts on review-band transactions has been checked
        against the trainer's schema, which is a claim nobody has made. The
        loader's refusal is what keeps the next unit's decision honest.
        """
        out = tmp_path / "labels.csv"
        write_label_csv(both_verdicts, out)

        with open(out, "r", newline="") as handle:
            header = next(csv.reader(handle))

        assert "corpus_schema" not in header

    def test_the_trainer_still_refuses_an_exported_file(
        self, tmp_path, both_verdicts
    ):
        """The real loader, on real output, raises.

        This is the end-to-end version of the assertion above and the one that
        would catch a future change to either side. It calls
        `_load_synthetic_csv` itself rather than trusting the header check,
        because the guard that matters is the loader's, not the file's.
        """
        from scripts.train_xgboost_aligned import CORPUS_SCHEMA, _load_synthetic_csv

        out = tmp_path / "labels.csv"
        write_label_csv(both_verdicts, out)

        with pytest.raises(ValueError) as exc:
            _load_synthetic_csv(str(out))

        message = str(exc.value)
        assert CORPUS_SCHEMA in message, (
            "the refusal must name the schema it wanted; an error that does not "
            "say what was expected leaves the next person guessing"
        )

    def test_an_unlabelled_alert_is_not_exported(self, tmp_path):
        """NULL is "nobody judged this", and it is not a verdict.

        A row with no label cannot be projected onto `is_fraud` without
        inventing one, and inventing it is the exact failure this change exists
        to stop. The filter lives in the query; this pins the observable
        consequence, which is that the export cannot contain a blank label.
        """
        out = tmp_path / "labels.csv"
        write_label_csv([_row(label=None)], out)

        rows = _read(out)
        assert rows == [] or all(r["analyst_label"] for r in rows)

    def test_exporting_nothing_writes_a_header_only_file(self, tmp_path):
        """Zero labels still produces a parseable file with the right header.

        An empty file is not obviously wrong, and "the script wrote nothing" is
        indistinguishable from "the script crashed" for whoever runs it next.
        """
        out = tmp_path / "labels.csv"
        write_label_csv([], out)

        with open(out, "r", newline="") as handle:
            header = next(csv.reader(handle))

        assert tuple(header) == EXPORT_COLUMNS
        assert _read(out) == []


class TestAContestedVerdictIsNotAFact:
    """A label on a NON-terminal alert is a position, not a verdict.

    `revert` moves an alert from `RESOLVED` back to `OPEN` and deliberately
    leaves `analyst_label` alone -- see
    `tests/integration/test_analyst_labels.py::test_revert_does_not_clear_an_
    existing_label`. So a reverted alert carries its old label while its status
    says the question is open again.

    Selecting on `analyst_label IS NOT NULL` alone cannot see that difference,
    and the row it produces is the worst kind: a verdict somebody took back,
    exported as fact, with `is_fraud` already written. Terminal status is
    therefore required, not merely the label.

    `REVIEWED` stays excluded on both counts: it carries no verdict, so the NULL
    filter already drops it, and it is not a terminal lifecycle state either.
    """

    @staticmethod
    def _row_at_status(status: str, *, label: str, transaction_id: str) -> dict:
        """`_row` plus the alert's lifecycle state.

        Built here rather than by adding a `status` parameter to `_row`, so the
        rows the other classes export stay exactly what they were.
        """
        return {**_row(label=label, transaction_id=transaction_id), "status": status}

    def test_an_open_alert_with_a_stale_label_is_not_exported(self, tmp_path):
        """The reverted alert: status `open`, label still `confirmed_fraud`.

        Asserted on the row count, not on a label check, because the failure
        mode is a row that is present and looks perfectly well formed -- it has
        a label, a reviewer and a timestamp. The only thing separating it from
        a settled verdict is its status.
        """
        out = tmp_path / "labels.csv"
        write_label_csv(
            [
                self._row_at_status(
                    AlertStatus.OPEN,
                    label="confirmed_fraud",
                    transaction_id="txn-reverted",
                )
            ],
            out,
        )

        rows = _read(out)

        assert [row["transaction_id"] for row in rows] == [], (
            f"an alert whose status is {AlertStatus.OPEN!r} was exported as "
            f"fact: {rows}. Its analyst_label was taken back by `revert`, and "
            f"the label column keeps the stale value on purpose, so a NULL-label "
            f"filter alone cannot tell a settled verdict from a contested one."
        )

    def test_a_reviewed_alert_is_not_exported_even_with_a_label(self, tmp_path):
        """`REVIEWED` is not terminal either.

        `review` writes no verdict, so a labelled `REVIEWED` row means the
        label came from somewhere the lifecycle has moved past. Non-terminal
        is non-terminal.
        """
        out = tmp_path / "labels.csv"
        write_label_csv(
            [
                self._row_at_status(
                    AlertStatus.REVIEWED,
                    label="false_positive",
                    transaction_id="txn-reviewed",
                )
            ],
            out,
        )

        assert _read(out) == []

    def test_both_terminal_verdicts_still_export(self, tmp_path):
        """The positive half: `resolved` rows are unaffected.

        Both verdicts, each still projected onto the trainer's label vocabulary
        the same way. A fix that simply stopped exporting labelled rows would
        pass the refusal test above and silently empty the corpus, so this is
        asserted explicitly.
        """
        out = tmp_path / "labels.csv"
        write_label_csv(
            [
                self._row_at_status(
                    AlertStatus.RESOLVED,
                    label="confirmed_fraud",
                    transaction_id="txn-fraud",
                ),
                self._row_at_status(
                    AlertStatus.RESOLVED,
                    label="false_positive",
                    transaction_id="txn-clean",
                ),
            ],
            out,
        )

        rows = {row["transaction_id"]: row for row in _read(out)}

        assert set(rows) == {"txn-fraud", "txn-clean"}
        assert rows["txn-fraud"]["is_fraud"] == "1"
        assert rows["txn-clean"]["is_fraud"] == "0"
        assert rows["txn-fraud"]["analyst_label"] == "confirmed_fraud"
        assert rows["txn-clean"]["analyst_label"] == "false_positive"


class TestTheDocumentationIsLoadBearing:
    """The field mapping is in the docstring, and the docstring is checked."""

    def test_every_column_is_named_in_the_docstring(self):
        """Docs and code cannot drift.

        A documented mapping that only describes most of the columns is worse
        than none, because it reads as complete. This makes the claim checkable
        instead of a matter of trust.
        """
        from scripts.export_labels import __doc__

        assert __doc__ is not None
        for column in EXPORT_COLUMNS:
            assert column in __doc__, (
                f"{column!r} is exported but not documented in the module "
                f"docstring. The mapping is the contract with whoever reads the "
                f"file next."
            )

    def test_the_docstring_states_the_missing_feature_columns(self):
        """The behavioural aggregates must be documented as ABSENT.

        `user_avg_amount`, `user_std_amount`, `velocity_5min` and `velocity_1h`
        are per-user aggregates the trainer reads with a `0` fallback. They are
        not on the alert row and this script does not fabricate them -- and
        `_save_synthetic_csv`'s docstring records exactly what a column of
        fabricated zeroes does downstream: `amount_vs_user_std` becomes a
        constant-zero feature while the deployed artifact still carries weight
        on it. Saying so here is the point.
        """
        from scripts.export_labels import __doc__

        assert __doc__ is not None
        for absent in (
            "user_avg_amount",
            "user_std_amount",
            "velocity_5min",
            "velocity_1h",
        ):
            assert absent in __doc__, (
                f"{absent} is read by the trainer with a 0 fallback and is NOT "
                f"in the export. That gap has to be written down where someone "
                f"building a corpus from this file will read it."
            )


class TestTheMappingStaysInsideTheRealVocabulary:
    def test_every_label_maps_to_one_of_two_values(self):
        """The projection is total over the label vocabulary.

        Derived from `ANALYST_LABEL_VALUES` rather than restated, so adding a
        verdict to the model surfaces here as a failure instead of silently
        falling through to "0".
        """
        assert set(ANALYST_LABEL_VALUES) == {"confirmed_fraud", "false_positive"}

    def test_a_label_outside_the_vocabulary_is_refused(
        self, tmp_path
    ):
        """A row the script cannot read is an error, not a silent "0".

        This is the mirror of the column's CHECK constraint: the database
        refuses to store the value, and this refuses to export it. Two layers
        because the exporter is run against databases the migration may not
        have reached yet.
        """
        with pytest.raises(ValueError):
            write_label_csv([_row(label="confirmed_fraudd")], tmp_path / "out.csv")

    def test_a_refused_export_leaves_no_partial_file_behind(
        self, tmp_path, both_verdicts
    ):
        """Atomic destination: a refusal must not truncate what was there.

        Rows stream to a sibling temp file and only a fully-validated run
        replaces the destination. Without this, the ValueError above fires
        after earlier rows were already flushed, leaving a truncated CSV
        indistinguishable in shape from a complete one.
        """
        out = tmp_path / "out.csv"
        write_label_csv(both_verdicts, out)
        before = out.read_bytes()

        with pytest.raises(ValueError):
            write_label_csv(
                [
                    _row(label="confirmed_fraud", transaction_id="txn-ok"),
                    _row(label="confirmed_fraudd", transaction_id="txn-bad"),
                ],
                out,
            )

        assert out.read_bytes() == before, (
            "the refused run replaced a complete export with a partial one"
        )
        assert list(tmp_path.glob("out.csv.*.tmp")) == [], (
            "temp file leaked next to the destination"
        )

    def test_the_script_never_calls_the_trainer(self):
        """Static, because the failure is a silent one.

        If this module ever imports `train_xgboost_aligned` or shells out to
        it, an export would start doing something irreversible, and the damage
        would be a model nobody can reproduce.

        Asserted on the parsed AST rather than on the source text. A substring
        scan over the file would fail on this module's own docstring, which
        NAMES `train_xgboost_aligned` and `CORPUS_SCHEMA` precisely to explain
        why it refuses to touch either -- the first version of this test did
        exactly that and was wrong. What has to be absent is the import and the
        call, not the word.
        """
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1] / "scripts" / "export_labels.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        for forbidden in (
            "train_xgboost_aligned",
            "scripts.train_xgboost_aligned",
            "subprocess",
            "xgboost",
            "sklearn",
        ):
            assert not any(forbidden in name for name in imported), (
                f"export_labels.py imports {forbidden!r} ({sorted(imported)}). "
                f"The exporter must not retrain and must not shell out."
            )

        # CORPUS_SCHEMA is a module-level CONSTANT in the trainer. Referring to
        # it needs an import or a qualified name, so a name check covers the
        # case where someone reaches it through the module object.
        referenced = {
            node.id for node in ast.walk(tree)
            if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        assert "CORPUS_SCHEMA" not in referenced, (
            "export_labels.py references CORPUS_SCHEMA. Writing that stamp is "
            "what this whole module exists to avoid doing."
        )
