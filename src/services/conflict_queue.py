"""The conflict queue — the transactions whose two scoring layers disagree.

WHAT THIS IS
============
A read-side filter. It selects transactions where the deterministic rules and
the ML model reached opposite conclusions about the same transaction, which is
the population the routed classification policy sends to `review` because it
cannot commit to either layer.

It changes NO verdict. Nothing here feeds `ScoringService.classify`, no score is
recomputed, no threshold is re-derived, and the ensemble is not consulted. A
transaction's classification is decided once, at scoring time, and this module
only decides which already-classified transactions an analyst is shown
together. Deleting this module would not change a single stored score.

THE DEFINITION, exactly
=======================
Against the row's OWN persisted ``fraud_scores.threshold`` — written ``T``
below — a transaction is a conflict when exactly one of its two layers clears
that bar:

    rules loud, model silent:   rule_score >  T   and   ml_score   <= T
    model loud, rules quiet:    ml_score   >  T   and   rule_score <= T

Both comparisons are strict ``>`` on the winning side, which is the same
strictness the routed policy uses (`ml_clears = ml_speaks and ml_score >
threshold`), so a layer sitting exactly ON the threshold has not cleared it.

WHY THE ROW'S OWN PERSISTED THRESHOLD
=====================================
`EnsembleScorer.get_threshold` is amount-tiered, so the threshold that applied
to a transaction is a function of its amount and of the tier table in force
WHEN IT WAS SCORED. Recomputing it here would re-apply today's tiers to a row
scored under yesterday's, and a reconfigured `THRESHOLD_TIERS` would silently
re-classify historical queue membership. The stored value is the only one that
cannot drift.

WHAT WAS CONSIDERED AND REJECTED
===============================
The first shape considered — and the one an earlier draft of this file's brief
proposed — was a pair of wider bands: "rules above the threshold while the model
sits under `ML_FLOOR`", and "model above the threshold while the rules sit under
half of it". Rejected for two reasons.

First, it invents constants. `ML_FLOOR` means something precise and
load-bearing elsewhere — it is the "has the model spoken at all" bar that gates
whether the rules may block alone — and reusing it here would make the queue's
membership depend on a setting whose documented job is elsewhere. The `0.5` had
no meaning at all: nothing else in the system uses it, so it would have been a
number with no owner, tuned by whoever first found the queue too noisy.

Second, and decisively, both wider bands are SUBSETS of the definition above, so
they answer a different question: "where is the disagreement sharpest?" rather
than "where do the layers disagree?". A queue whose membership is a subset of
the routed policy's `review` population is a strict improvement on re-deriving
the policy client-side; one that is only a subset of it is a narrower queue
with an extra tuning knob and a second definition of the same word.

REJECTED ALTERNATIVE, FOR THE RECORD: deriving the conflict from the STORED
`classification` ("everything routed to `review`"). That is not the same
population — `review` also absorbs rows where the rules cleared the bar and the
model merely failed to clear it by a hair (rule 85, model 39, T 50), which is
agreement in any useful sense. The brief's own example of the `acme`/`retail`
transaction at 50,001 EUR is in that population and is not a conflict.

SQL FORM: WHY `IN (subquery)` AND NOT A JOIN
============================================
`fraud_scores` has no unique constraint on `transaction_id` (see
`get_scores_for_transactions`, which keeps the newest row per transaction), so
a JOIN is free to fan one transaction out across several score rows and inflate
both the page and the count. `IN (subquery)` cannot duplicate anything.

The cost of that choice is one deliberate limitation: the subquery matches ANY
score row, while the list response displays the NEWEST one. A transaction whose
older score row conflicted and whose newer one did not would appear in the queue
showing two agreeing numbers. That is unreachable today — a transaction is
scored exactly once, inside `create_and_score_transaction`, and no code path
rescores one — so the restriction is not written. If rescoring is ever added,
this subquery must additionally restrict to the newest row per transaction.
"""

from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.sql.elements import ColumnElement

from src.models.fraud_score import FraudScore


def conflict_predicate(scores: Any = FraudScore.__table__) -> ColumnElement[bool]:
    """The SQL boolean that defines "these two layers disagreed".

    ``scores`` is any SQLAlchemy table carrying the three columns read below. It
    defaults to the shipped model, so callers pass nothing; it is a parameter
    because the predicate must also be executable against real SQL in the
    hermetic suite, where `FraudScore.transaction_id` being a
    `postgresql.UUID` makes the shipped table impossible to create on SQLite.
    See `tests/unit/test_conflict_predicate.py`.

    Returns an expression over a `fraud_scores` row. It reads no configuration:
    see the module docstring for why `ML_FLOOR` is deliberately absent.
    """
    rule_score = scores.c.rule_score
    ml_score = scores.c.ml_score
    threshold = scores.c.threshold

    # Spelled out as two AND-ed pairs rather than `(rule_clears != ml_clears)`.
    # The pairs are the same predicate, but this form renders to portable,
    # self-describing SQL, and — the reason it is written this way — it degrades
    # predictably if a threshold is NULL: each `<=` becomes NULL, the whole
    # expression becomes NULL, and the row drops out of the `IN (subquery)`
    # rather than raising. The shipped column is NOT NULL, so that state does
    # not arise; the behaviour is pinned rather than assumed.
    return or_(
        and_(rule_score > threshold, ml_score <= threshold),
        and_(ml_score > threshold, rule_score <= threshold),
    )


def conflict_ids_subquery() -> Any:
    """``select(fraud_scores.transaction_id)`` restricted to conflicting rows.

    The shape the endpoint uses for `Transaction.id IN (...)`. It projects a
    single id column deliberately: projecting whole rows would compile to a
    multi-column IN that PostgreSQL rejects outright, and that failure would
    surface as a 500 on the list endpoint rather than as a mistake at the
    definition.
    """
    return select(FraudScore.transaction_id).where(conflict_predicate())


__all__ = ["conflict_predicate", "conflict_ids_subquery"]