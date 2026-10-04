"""The conflict predicate — the SQL that selects the disagreement queue.

WHY THESE RUN REAL SQL AND NOT A MOCK
=====================================
A disagreement is a claim about arithmetic on stored columns, so the only way to
test it honestly is to let a database evaluate it. A mocked session proves the
endpoint CALLS the predicate; it cannot prove the predicate selects what it
claims, which is where every interesting bug in this feature would live: an
inverted comparison, a `<=` that should be `<`, or a clause that accidentally
requires BOTH layers to disagree.

WHY SQLITE AND NOT THE SHIPPED `FraudScore` TABLE
=================================================
`FraudScore.transaction_id` is a `postgresql.UUID`, which the SQLite dialect
cannot compile, so the shipped model cannot be created in this database. The
table below therefore mirrors the columns the predicate reads and the
predicate is handed it explicitly for that reason — which is the whole reason
`conflict_predicate` takes that parameter.

WHAT IS *NOT* COVERED HERE, AND WHY IT IS NOT MISSING
=====================================================
This file proves the predicate's SEMANTICS. That the HTTP endpoint puts this
predicate into both the page query and the count query is a wiring claim, and
`tests/integration/test_conflict_queue.py` proves it by compiling the actual
`Select` objects the endpoint executes. Neither file proves the other.
"""

import pytest
from sqlalchemy import (
    Column,
    Float,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
)

from src.services.conflict_queue import conflict_predicate

# Mirrors the `fraud_scores` columns the predicate reads, plus the id it
# projects. Types are SQLite-portable on purpose (see the module docstring).
#
# `threshold` is declared NULLABLE here although the shipped column is NOT NULL.
# That is not sloppiness: the point of the NULL case below is to pin what this
# SQL does when the threshold is missing, and the shipped DDL would have
# rejected the row before the predicate ever saw it.
metadata = MetaData()
scores = Table(
    "fraud_scores",
    metadata,
    Column("transaction_id", String(36), primary_key=True),
    Column("rule_score", Float, nullable=False),
    Column("ml_score", Float, nullable=False),
    Column("threshold", Float, nullable=True),
)


@pytest.fixture
def db():
    """A real SQLite database, one fresh per test."""
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def seed(db, rows):
    """Insert ``(rule_score, ml_score, threshold)`` rows, one per transaction."""
    db.execute(
        insert(scores),
        [
            {
                "transaction_id": f"tx-{index}",
                "rule_score": rule,
                "ml_score": ml,
                "threshold": threshold,
            }
            for index, (rule, ml, threshold) in enumerate(rows)
        ],
    )


def selected(db, predicate):
    """The transaction ids the predicate selects, sorted."""
    return sorted(
        db.execute(select(scores.c.transaction_id).where(predicate)).scalars().all()
    )


def test_rules_loud_model_silent_is_a_conflict(db):
    """The measured flagship case: rule 85 against a model at 27.55, T 50.

    Real values, lifted from the seeded development database, because a fixture
    invented to suit the predicate cannot disagree with it.
    """
    seed(db, [(85.0, 27.55399949848652, 50.0)])

    assert selected(db, conflict_predicate(scores)) == ["tx-0"]


def test_model_loud_rules_quiet_is_a_conflict(db):
    """The other direction, mirrored: the model clears the bar, the rules do not."""
    seed(db, [(27.55399949848652, 85.0, 50.0)])

    assert selected(db, conflict_predicate(scores)) == ["tx-0"]


@pytest.mark.parametrize(
    ("rule", "ml", "threshold", "direction"),
    [
        # Clearing is STRICT, so a layer resting exactly ON the threshold has not
        # cleared it — and one layer over the bar against one layer resting on it
        # is a disagreement, not a near miss. This boundary is the whole reason
        # the predicate says `>` and not `>=`, and the first draft of this file
        # got it backwards: it listed "model one hair over, rules exactly on" as
        # an AGREEMENT case, which is what the implementation then disproved.
        (50.0, 50.0001, 50.0, "model loud, rules resting on the bar"),
        (50.0001, 50.0, 50.0, "rules loud, model resting on the bar"),
    ],
)
def test_one_layer_over_the_other_resting_on_it_is_a_conflict(
    db, rule, ml, threshold, direction
):
    seed(db, [(rule, ml, threshold)])

    assert selected(db, conflict_predicate(scores)) == ["tx-0"], direction


@pytest.mark.parametrize(
    ("rule", "ml", "threshold", "why"),
    [
        (85.0, 90.0, 50.0, "both layers clear the bar — they agree"),
        (10.0, 5.0, 50.0, "neither layer clears the bar — they agree"),
        (50.0, 50.0, 50.0, "both sit exactly ON the bar; clearing is strict"),
        (50.0001, 50.0002, 50.0, "both a hair over is still agreement"),
        (0.0, 0.0, 0.0, "a zero threshold cannot be cleared by a strict >"),
    ],
)
def test_agreement_is_not_a_conflict(db, rule, ml, threshold, why):
    seed(db, [(rule, ml, threshold)])

    assert selected(db, conflict_predicate(scores)) == [], why


def test_the_threshold_is_the_rows_own_persisted_one(db):
    """Same two scores, two thresholds, opposite verdicts.

    The threshold is amount-tiered, so a recomputed one would grade a row
    against a tier the scorer never used. The predicate reads the stored value,
    which is what makes this pair possible at all.
    """
    seed(
        db,
        [
            (85.0, 27.0, 40.0),  # rule clears 40, the model does not
            (85.0, 27.0, 90.0),  # neither clears 90
        ],
    )

    assert selected(db, conflict_predicate(scores)) == ["tx-0"]


def test_both_directions_appear_in_one_page(db):
    seed(
        db,
        [
            (85.0, 27.0, 50.0),  # rules loud
            (27.0, 85.0, 50.0),  # model loud
            (85.0, 90.0, 50.0),  # agree
            (1.0, 2.0, 50.0),  # agree
        ],
    )

    assert selected(db, conflict_predicate(scores)) == ["tx-0", "tx-1"]


def test_a_conflict_is_exactly_one_layer_clearing(db):
    """The definition, stated as a property over a grid rather than a list.

    "Rules loud and the model disagrees" has two readings — the model crossing
    the threshold, or the two layers disagreeing with each other by some other
    measure — and they select different rows. This pins the one the module
    documents: exactly one layer strictly above the row's own threshold.
    """
    values = [0.0, 25.0, 49.0, 50.0, 51.0, 75.0, 100.0]
    threshold = 50.0
    rows = [(rule, ml, threshold) for rule in values for ml in values]
    seed(db, rows)

    expected = sorted(
        f"tx-{index}"
        for index, (rule, ml, _) in enumerate(rows)
        if (rule > threshold) != (ml > threshold)
    )

    assert selected(db, conflict_predicate(scores)) == expected
    assert expected, "the grid must contain conflicts, or this asserts nothing"


def test_a_missing_threshold_yields_no_conflict_rather_than_an_error(db):
    """`threshold` is NOT NULL in the shipped schema, so this row is unreachable.

    Asserted anyway because the SQL compares with `<=`, and against a NULL
    threshold that comparison is NULL rather than False — which, inside an
    `IN (subquery)`, silently drops the row instead of raising. Pinning the
    behaviour keeps the schema assumption visible instead of implicit.
    """
    seed(db, [(85.0, 27.0, None)])  # type: ignore[list-item]

    assert selected(db, conflict_predicate(scores)) == []


def test_the_predicate_cannot_duplicate_a_transaction(db):
    """`IN (subquery)` cannot fan a page out the way a JOIN would.

    `fraud_scores` has no unique constraint on `transaction_id`, which is why
    `get_scores_for_transactions` keeps the newest row per transaction. A JOIN
    would therefore be free to repeat a transaction across its score rows and
    inflate the page AND the count; the subquery form cannot.
    """
    seed(db, [(85.0, 27.0, 50.0)])

    rows = db.execute(
        select(scores.c.transaction_id).where(conflict_predicate(scores))
    ).scalars().all()

    assert len(rows) == len(set(rows))