#!/usr/bin/env python
"""Seed a continuous, genuinely-scored 7-day history for the dashboard trend.

WHY THIS EXISTS
---------------
``scripts/seed_demo_data.py`` creates ``Transaction`` rows and nothing else.
The dashboard's trend chart (``frontend/src/components/ScoreTrendChart.tsx`` ->
``buildDailyAverages``) skips every row whose ``risk_score`` is null, and a
transaction only carries one once a ``FraudScore`` exists. So every row that
script seeded is invisible to the chart, and the trend showed three isolated
days (18 / 5 / 2 transactions) separated by four empty columns.

Closing those gaps with more unscored transactions would not have worked:
the chart skips them for exactly the same reason.

WHAT THIS SCRIPT GUARANTEES
---------------------------
* **Every score is real.** Each row's ``FraudScore`` is the return value of
  ``ScoringService.compute_scores`` for that row's own inputs. No score,
  classification or threshold is written as a literal anywhere in this file.
* **Every score is time-consistent.** ``tx_data["timestamp"]`` carries the
  BACKDATED transaction time, not ``now``, so ``hour_of_day``, ``is_weekend``
  and ``unusual_hours`` see the moment the transaction actually happened. A
  backdated row scored as of "now" would produce a number no transaction at
  that hour could ever receive.
* **Velocity is zero, honestly.** A backdated row has no Redis window and no
  recent history, so ``recent_transactions`` is 0 and ``tx_count_last_5min`` /
  ``tx_count_last_1h`` are 0. Velocity rules therefore stay silent. This is a
  real limitation of seeding history after the fact and it is accepted rather
  than papered over: fabricating a recent-transaction count to make
  ``high_velocity`` / ``velocity_burst`` fire would be manufacturing evidence
  of a card-testing burst that never happened. The trade-off is that the
  seeded rows exercise the merchant, amount and hour rules, not the velocity
  ones.

WHAT IT DELIBERATELY DOES NOT WRITE
----------------------------------
* ``drift_reference_data`` -- ``get_drift_status`` seeds a reference from live
  scores once the recent window reaches ``MIN_DRIFT_REFERENCE_ROWS`` (200,
  reached at ~400 total scores) and then persists it forever. A reference
  captured from a demo dataset would outlive the demo. ``DEFAULT_TOTAL_ROWS``
  is budgeted to keep the total far below that trigger.
* ``ml_model_runs``, ``rule_metadata`` -- audit tables for training runs and
  rule edits. A per-transaction row here would be decoration.
* ``outbox_events`` -- enqueues the async workers (LLM report, SHAP, embedding).
  Writing them would wake the workers for synthetic rows.
* ``fraud_alerts.analyst_label`` -- left NULL on every seeded alert.
  ``scripts/export_labels.py`` exports exactly the alerts whose status is
  ``resolved`` AND whose ``analyst_label`` is not null, as a labelled corpus; a
  seeded label would enter training data as though an analyst had judged it.

PROVENANCE MARKER AND HOW TO REMOVE THE ROWS
---------------------------------------------
There is no ``source``/``is_synthetic`` column and this script does not add a
migration. The marker is a dedicated user:

    email    = ``SEEDED_USER_EMAIL``  (demo-history@frauddetector.dev)
    username = ``SEEDED_USERNAME``    (demo_history)
    role     = ANALYST, and its password is a random value that is never
               recorded, so the account cannot be logged into -- it exists only
               to own the seeded rows.

Every seeded transaction hangs off that user, and no other row does. To remove
the demo history completely (scores and alerts cascade from the transactions):

    BEGIN;
    DELETE FROM fraud_alerts
     WHERE transaction_id IN (SELECT id FROM transactions
                               WHERE user_id = (SELECT id FROM users
                                                 WHERE email = 'demo-history@frauddetector.dev'));
    DELETE FROM fraud_scores
     WHERE transaction_id IN (SELECT id FROM transactions
                               WHERE user_id = (SELECT id FROM users
                                                 WHERE email = 'demo-history@frauddetector.dev'));
    DELETE FROM transactions
     WHERE user_id = (SELECT id FROM users
                       WHERE email = 'demo-history@frauddetector.dev');
    DELETE FROM users WHERE email = 'demo-history@frauddetector.dev';
    COMMIT;

Or simply ``DELETE FROM users WHERE email = '...';`` -- ``transactions.user_id``
cascades, and ``fraud_scores`` / ``fraud_alerts`` cascade from
``transactions.id``. The explicit form above is given because the cascade is
what makes the one-liner correct and it is worth being explicit about a
destructive statement whose scope is a demo database.

Because the marker is a user and not a column, these rows are otherwise
indistinguishable from real ones. Do not run the reset against a database
holding production data.

ROW BUDGET -- WHY 70
--------------------
``DashboardPage.tsx`` fetches ``page: 1, page_size: 100`` and
``list_transactions_endpoint`` caps ``page_size`` at 100, so the trend chart can
only ever see the newest 100 transactions, whatever the total. Measured before
the first run: 44 transactions existed, 19 of them older than the 7-day window.
Adding 70 evicts ``44 + 70 - 100 = 14`` rows -- fewer than the 19 pre-window
rows available to absorb them -- so every row inside the window stays inside
the newest 100 and the chart has no empty left edge. ``evicted_by_ceiling``
computes this; ``tests/test_seed_demo_history.py`` asserts it.

Usage:
    python scripts/seed_demo_history.py --dry-run
    python scripts/seed_demo_history.py
    python scripts/seed_demo_history.py --total 56 --days 7

Idempotent: re-running writes nothing. The marker user already owning a
transaction is the check, exactly as ``seed_demo_data.py`` uses "this user
already has a transaction".

Requires a running PostgreSQL with the schema applied (``alembic upgrade
head``). Run it inside the api container so the ML artifact and its
dependencies are present::

    docker compose exec api python scripts/seed_demo_history.py --dry-run
    docker compose exec api python scripts/seed_demo_history.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.core.config import settings
from src.core.database import async_session_maker
from src.core.security import hash_password
from src.models.fraud_alert import AlertStatus, FraudAlert
from src.models.fraud_score import FraudClassification, FraudScore
from src.models.transaction import Transaction, TransactionStatus
from src.models.user import User, UserRole
from src.services.ml_model import MLModelService
from src.services.scoring_service import ScoringService

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: The provenance marker. See "PROVENANCE MARKER" in the module docstring.
SEEDED_USER_EMAIL = "demo-history@frauddetector.dev"
SEEDED_USERNAME = "demo_history"

#: The chart's buckets: 7 UTC dates ending today. ``buildDailyAverages`` keys on
#: ``toISOString().slice(0, 10)``, so "a day" is a UTC date.
WINDOW_DAYS = 7

#: Rows to seed. 70 = 10 per day, and it keeps the newest-100 window complete
#: (see "ROW BUDGET" above). Raising it past ~75 empties the chart's left edge.
DEFAULT_TOTAL_ROWS = 70

#: ``page_size`` ceiling on ``GET /api/v1/transactions``, which is also the
#: number of rows the dashboard trend can see.
DASHBOARD_ROW_CEILING = 100

#: The seeded account's home country, matching the demo payload in
#: ``create_and_score_transaction``.
HOME_COUNTRY = "AR"

#: Cards the seeded history runs on. Two, so ``known_cards`` has something to
#: accumulate as the history is replayed in order.
SEEDED_CARDS = ("4242", "1881")

#: Mirrors ``create_and_score_transaction``'s status map exactly.
STATUS_BY_CLASSIFICATION: dict[str, TransactionStatus] = {
    "legitimate": TransactionStatus.APPROVED,
    "review": TransactionStatus.FLAGGED,
    "fraud": TransactionStatus.BLOCKED,
}

#: The catalog each day's rows are drawn from, in a fixed rotation.
#:
#: Categories come from ``KNOWN_MERCHANT_CATEGORIES`` -- the API rejects anything
#: outside it, so seeding a category the live path would refuse would make the
#: demo unrepresentative of what the system accepts.
#:
#: The mix is deliberate rather than uniform, because a uniform one would make
#: the chart flat by construction. Everyday purchases carry no rule evidence;
#: the night-hour adversarial rows fire ``unusual_hours`` +
#: ``off_hours_crypto`` + ``unusual_merchant``; the large transfers fire
#: ``high_amount`` with its magnitude term. Which of those lands in ``review``
#: and which in ``fraud`` is decided by the pipeline, not by this table -- see
#: the module docstring's note on velocity for what is NOT covered.
#:
#: Entry shape: (merchant_name, merchant_category, amount, hour_utc).
MERCHANT_CATALOG: tuple[tuple[str, str, float, int], ...] = (
    # --- everyday, daytime: no rule evidence -------------------------------
    ("Walmart Supercenter", "grocery", 84.32, 12),
    ("Starbucks", "restaurant", 6.75, 8),
    ("Shell", "fuel", 52.10, 18),
    ("Netflix", "subscription", 15.99, 22),
    ("Amazon", "retail", 129.99, 15),
    ("Target", "retail", 74.15, 11),
    ("Uber", "travel", 24.60, 23),
    ("Spotify", "subscription", 11.99, 9),
    ("Trader Joes", "grocery", 46.88, 17),
    ("Comcast", "utilities", 89.99, 10),
    ("AMC Theatres", "entertainment", 32.00, 20),
    ("Chipotle", "restaurant", 14.25, 13),
    ("CVS", "healthcare", 23.45, 14),
    ("Kroger", "grocery", 63.70, 16),
    # --- adversarial category, daytime: `unusual_merchant` only -----------
    ("bet365", "gambling", 220.00, 21),
    ("Betfair", "gambling", 95.50, 19),
    # --- regulated category at night: corroborated `unusual_merchant` ------
    ("Western Union", "money_transfer", 640.00, 3),
    ("MoneyGram", "money_transfer", 310.00, 2),
    # --- night-hour adversarial: the strongest honest signal ---------------
    ("Binance", "cryptocurrency", 1850.00, 3),
    ("Coinbase", "cryptocurrency", 5400.00, 4),
    # --- large but daylight: `high_amount` without a night-hour story ------
    ("Delta Air Lines", "travel", 4120.00, 6),
    # --- night remittance in the mid band: rule evidence, sub-critical ------
    ("MoneyGram", "money_transfer", 4200.00, 2),
    # --- the critical-amount band: the only tier the rule branch will BLOCK --
    # Above the last threshold tier's floor (``ScoringService._critical_floor``)
    # a rule-strong transaction can be classified `fraud` instead of `review`.
    # Without a row up here every seeded row tops out at `review` and the chart
    # never shows a blocked transaction, so the demo would not exercise the one
    # route that actually blocks. The amount is the classic "stolen balance
    # lands on an exchange" shape that ``ml_constants`` documents as the
    # reported 400k-USD/binance case.
    ("Binance", "cryptocurrency", 78000.00, 3),
)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DayPlan:
    """How many rows land on one UTC calendar day."""

    day: date
    count: int


@dataclass(frozen=True)
class TxSpec:
    """One planned transaction, before it has a score or an id."""

    merchant: str
    category: str
    amount: float
    card_last4: str
    occurred_at: datetime


@dataclass
class SeedReport:
    """What a run actually did."""

    dry_run: bool = False
    #: Rows the plan calls for. Set even by a dry run, which writes nothing --
    #: `rows_written` stays 0 there, so the two are separate on purpose.
    planned_rows: int = 0
    rows_written: int = 0
    rows_skipped: int = 0
    alerts_created: int = 0
    user_email: str = SEEDED_USER_EMAIL
    per_day: dict[str, int] = field(default_factory=dict)
    per_classification: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Planning (pure -- no database, no scoring)
# ---------------------------------------------------------------------------


def build_day_plan(
    now: datetime, total: int = DEFAULT_TOTAL_ROWS, days: int = WINDOW_DAYS
) -> list[DayPlan]:
    """Spread ``total`` rows over the ``days`` UTC dates ending today.

    Every day gets at least one row. That is the whole point of the script: the
    chart renders a day with no scored rows as a blank column, so an allocation
    that gave some day zero rows would reproduce the exact gap it exists to
    close. A ``total`` too small to cover the window is therefore an error
    rather than a best-effort split.

    Days are returned oldest-first, and any remainder goes to the OLDEST days.
    Today is a partial day -- the run happens during it -- so it is the one day
    that cannot absorb an extra row without the newest point looking like a
    spike.
    """
    if days < 1:
        raise ValueError("days must be at least 1")
    if total < days:
        raise ValueError(
            f"cannot cover {days} days with {total} rows: the trend chart needs "
            "at least one row per day, so total must be >= days"
        )

    base, remainder = divmod(total, days)
    plan: list[DayPlan] = []
    for offset in reversed(range(days)):
        # offsets days-1..0 are the oldest..newest; the extra rows go to the
        # largest offsets.
        count = base + (1 if offset >= days - remainder else 0)
        plan.append(DayPlan(day=now.date() - timedelta(days=offset), count=count))
    return plan


def build_transaction_specs(plan: list[DayPlan], now: datetime) -> list[TxSpec]:
    """Turn a day plan into concrete, backdated transaction specs.

    Deterministic: the catalog is walked in a fixed rotation and the within-day
    minute/second are derived from the slot index, so two runs plan identical
    rows and a scoring difference between runs is never explained by "the seed
    was random".

    Returned oldest-first, which is what lets ``seed_history`` accumulate
    ``known_cards`` in the order the account would actually have seen them.

    Today's rows are clamped to an hour strictly before ``now``: a seeded row
    dated in the future would be a row the dashboard can see but no transaction
    could have produced.
    """
    specs: list[TxSpec] = []
    index = 0
    latest_hour = max(0, now.hour - 1)

    for day_plan in plan:
        for slot in range(day_plan.count):
            merchant, category, amount, hour = MERCHANT_CATALOG[
                index % len(MERCHANT_CATALOG)
            ]
            index += 1

            if day_plan.day == now.date():
                hour = min(hour, latest_hour)

            occurred_at = datetime(
                day_plan.day.year,
                day_plan.day.month,
                day_plan.day.day,
                hour=hour,
                # Prime-ish strides so rows inside a day do not share a stamp.
                minute=(slot * 17) % 60,
                second=(slot * 29) % 60,
                tzinfo=timezone.utc,
            )
            specs.append(
                TxSpec(
                    merchant=merchant,
                    category=category,
                    amount=float(amount),
                    card_last4=SEEDED_CARDS[index % len(SEEDED_CARDS)],
                    occurred_at=occurred_at,
                )
            )
    return specs


def evicted_by_ceiling(
    existing_total: int,
    seed_total: int,
    ceiling: int = DASHBOARD_ROW_CEILING,
) -> int:
    """How many of the oldest transactions the dashboard would never see.

    The trend chart reads the newest ``ceiling`` transactions, ordered
    ``created_at DESC``, so a seed that pushes the total past ``ceiling``
    evicts the oldest rows from the chart. Rows older than the 7-day window are
    the cheapest thing to evict -- they were never drawn -- which is what makes
    a seed of this size safe.
    """
    return max(0, existing_total + seed_total - ceiling)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


async def get_or_create_seeded_user(db) -> User:
    """Fetch the marker user, creating it on first run.

    The password is random and never printed or recorded, so the account is a
    marker rather than a login. Seeding a login here would put a known
    credential in the demo data.
    """
    result = await db.execute(select(User).where(User.email == SEEDED_USER_EMAIL))
    user = result.scalar_one_or_none()
    if user is not None:
        print(f"  = marker user {SEEDED_USER_EMAIL} already exists")
        return user

    user = User(
        id=uuid4(),
        username=SEEDED_USERNAME,
        email=SEEDED_USER_EMAIL,
        hashed_password=hash_password(uuid4().hex),
        role=UserRole.ANALYST,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    print(f"  + created marker user {SEEDED_USER_EMAIL}")
    return user


async def already_seeded(db, user_id) -> bool:
    """Whether this marker user already owns a transaction.

    The marker user doubles as the idempotency lock, because there is no
    ``source`` column to check and no migration may be added for one.
    """
    result = await db.execute(
        select(Transaction.id)
        .where(Transaction.user_id == user_id)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def default_scoring_service() -> ScoringService:
    """The production scoring pipeline, ML artifact included.

    ``src/api/v1/transactions.py`` loads the model once at import
    (``_ml_service.load_model()``) and scores every request through it. A seed
    script that skipped the load would score through the DEGRADED path --
    ``ml_score is None``, the ML weight redistributed away -- and produce rows
    that look scored but describe a pipeline the API never runs. Same artifact,
    same weights, same rules.
    """
    ml_service = MLModelService()
    ml_service.load_model()
    return ScoringService(ml_service=ml_service)


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


async def seed_history(
    db,
    *,
    total: int = DEFAULT_TOTAL_ROWS,
    days: int = WINDOW_DAYS,
    now: datetime | None = None,
    scoring_service=None,
) -> SeedReport:
    """Write a backdated, genuinely-scored history for the marker user.

    Returns a report; writes nothing if the marker user is already seeded.
    """
    now = now or datetime.now(tz=timezone.utc)

    user = await get_or_create_seeded_user(db)
    if await already_seeded(db, user.id):
        print(
            f"  = {SEEDED_USER_EMAIL} already owns transactions, nothing to do "
            f"(drop them with the reset SQL in this script's docstring to re-seed)"
        )
        return SeedReport(rows_skipped=total)

    plan = build_day_plan(now, total=total, days=days)
    specs = build_transaction_specs(plan, now)
    service = scoring_service or default_scoring_service()

    # The account's amount history, from the plan itself -- the same aggregate
    # the endpoint computes with SQL, over the rows this run will write.
    amounts = [spec.amount for spec in specs]
    history_stats = ScoringService.compute_user_history_stats(amounts)

    known_cards: set[str] = set()
    per_day: Counter[str] = Counter()
    per_classification: Counter[str] = Counter()
    alerts = 0

    for spec in specs:
        known_cards.add(spec.card_last4)
        occurred_at = spec.occurred_at

        tx_data: dict = {
            "amount": spec.amount,
            "merchant_name": spec.merchant,
            "merchant_category": spec.category,
            "card_last4": spec.card_last4,
            "user_id": str(user.id),
            # The BACKDATED time, not `now`. This is what makes the score
            # consistent with the row's own date.
            "timestamp": occurred_at.isoformat(),
            "country": HOME_COUNTRY,
        }
        user_history = {
            "avg_amount": history_stats["avg_amount"],
            "std_amount": history_stats["std_amount"],
            # Zero, honestly: a backdated row has no velocity window. See the
            # module docstring -- fabricating these would manufacture a burst.
            "tx_count_last_5min": 0,
            "tx_count_last_1h": 0,
        }
        context: dict = {
            "recent_transactions": 0,
            "known_cards": sorted(known_cards),
            "merchant_blacklist": settings.merchant_blacklist,
            "home_country": HOME_COUNTRY,
            "graph_features": {},
        }

        result = await service.compute_scores(tx_data, context, user_history)

        txn = Transaction(
            id=uuid4(),
            user_id=user.id,
            amount=spec.amount,
            currency="USD",
            merchant_name=spec.merchant,
            merchant_category=spec.category,
            card_last4=spec.card_last4,
            status=STATUS_BY_CLASSIFICATION.get(
                result.classification, TransactionStatus.PENDING
            ),
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        db.add(txn)
        # Flush the parent before its children. Both `fraud_scores` and
        # `fraud_alerts` carry `ForeignKey("transactions.id")`, and writing a
        # whole history in one session means the unit of work flushes all three
        # tables together -- so without this the INSERT order is not guaranteed
        # and PostgreSQL rejects the run with a ForeignKeyViolationError on
        # whichever child rows it emitted first. `create_transaction` flushes
        # for the same reason; this is the same contract, one layer up.
        await db.flush()

        score = FraudScore(
            id=uuid4(),
            transaction_id=txn.id,
            rule_score=result.rule_score,
            ml_score=result.ml_score,
            ensemble_score=result.ensemble_score,
            threshold=result.threshold,
            classification=FraudClassification(result.classification),
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        db.add(score)

        # Same gate as the endpoint: anything an analyst has to look at gets an
        # alert. `analyst_label` is deliberately left unset (NULL) so
        # export_labels.py can never export a seeded row as a judged label.
        if result.classification in ("fraud", "review"):
            db.add(
                FraudAlert(
                    id=uuid4(),
                    transaction_id=txn.id,
                    status=AlertStatus.OPEN,
                    score=result.ensemble_score,
                    threshold=result.threshold,
                    classification=result.classification,
                    created_at=occurred_at,
                    updated_at=occurred_at,
                )
            )
            alerts += 1

        per_day[occurred_at.date().isoformat()] += 1
        per_classification[result.classification] += 1

    await db.commit()

    return SeedReport(
        rows_written=len(specs),
        alerts_created=alerts,
        per_day=dict(sorted(per_day.items())),
        per_classification=dict(sorted(per_classification.items())),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_plan(report: SeedReport, *, committed: bool) -> None:
    if report.dry_run:
        print(f"  would write {report.planned_rows} scored transactions")
    else:
        print(f"  wrote {report.rows_written} scored transactions")
    for day, count in report.per_day.items():
        print(f"    {day}  {count:>3} rows")
    if report.per_classification:
        mix = ", ".join(
            f"{name}={count}" for name, count in report.per_classification.items()
        )
        print(f"  classifications: {mix}")
    if report.dry_run:
        print("  classifications: not scored (a dry run never touches the pipeline)")
        print(f"  marker user: {report.user_email}")
        print("  nothing was written.")
        return
    print(f"  alerts created: {report.alerts_created}")
    print(f"  marker user: {report.user_email}")
    print()
    print("Reset everything this script wrote:")
    print(f"  DELETE FROM users WHERE email = '{report.user_email}';")


async def run(
    *,
    total: int = DEFAULT_TOTAL_ROWS,
    days: int = WINDOW_DAYS,
    dry_run: bool = False,
    now: datetime | None = None,
    session=None,
    scoring_service=None,
) -> SeedReport:
    """Plan, and either print the plan or write it.

    ``session`` exists so a test can drive the whole path with a fake; the CLI
    leaves it unset and the real session maker opens one.
    """
    now = now or datetime.now(tz=timezone.utc)

    if dry_run:
        # Planned from the calendar alone: a dry run must not query the
        # database, let alone write to it.
        plan = build_day_plan(now, total=total, days=days)
        specs = build_transaction_specs(plan, now)
        per_day: Counter[str] = Counter(
            spec.occurred_at.date().isoformat() for spec in specs
        )
        report = SeedReport(
            dry_run=True,
            planned_rows=len(specs),
            per_day=dict(sorted(per_day.items())),
            user_email=SEEDED_USER_EMAIL,
        )
        _print_plan(report, committed=False)
        return report

    if session is not None:
        report = await seed_history(
            session, total=total, days=days, now=now, scoring_service=scoring_service
        )
        _print_plan(report, committed=True)
        return report

    async with async_session_maker() as db:
        report = await seed_history(
            db, total=total, days=days, now=now, scoring_service=scoring_service
        )
    _print_plan(report, committed=True)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and write nothing (no database access at all)",
    )
    parser.add_argument(
        "--total",
        type=int,
        default=DEFAULT_TOTAL_ROWS,
        help=f"rows to seed (default: {DEFAULT_TOTAL_ROWS}; must be >= --days)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=WINDOW_DAYS,
        help=f"days of history to cover (default: {WINDOW_DAYS})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    print(
        f"Seeding demo history for {SEEDED_USER_EMAIL} "
        f"({args.total} rows over {args.days} days)"
        + (" [DRY RUN - nothing will be written]" if args.dry_run else "")
    )
    asyncio.run(
        run(total=args.total, days=args.days, dry_run=args.dry_run)
    )


if __name__ == "__main__":
    main()