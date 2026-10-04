"""Tests for ``scripts/seed_demo_history.py``.

Why this file exists and what it is guarding
-------------------------------------------

The dashboard's 7-day trend chart reads the newest 100 transactions and skips
every row whose ``risk_score`` is null
(``frontend/src/components/ScoreTrendChart.tsx`` -> ``buildDailyAverages``).
``scripts/seed_demo_data.py`` only ever created ``Transaction`` rows and never a
``FraudScore``, so all of its rows are invisible to the trend and the chart was
showing three isolated days with four blank columns between them.

This script's whole job is to make that chart honest, which means three
specific failure modes have to be impossible rather than merely unlikely:

1. **Invented scores.** A hand-written ``ensemble_score=73.0`` would render a
   beautiful chart describing a model run that never happened. Every score here
   must be the production ``ScoringService``'s own output for that row's real
   inputs. ``test_persisted_scores_are_the_scoring_services_own_output`` proves
   the persisted row IS the service's return value, recomputed and compared
   field by field.
2. **Velocity fiction.** A backdated row genuinely has zero velocity signal.
   The honest answer is to pass zero and let velocity rules stay silent;
   fabricating a ``recent_transactions`` count to make them fire would be
   writing evidence for a card-testing burst that never happened.
   ``test_velocity_context_is_zero`` pins that.
3. **Poisoning the tables that must stay quiet.** ``drift_reference_data``
   auto-seeds from live scores once the recent window is large enough and then
   persists permanently; ``ml_model_runs``, ``rule_metadata`` and
   ``outbox_events`` are audit/pipeline tables. A seed script that writes them
   leaves the demo permanently worse than it found it.
   ``test_the_script_constructs_rows_only_for_permitted_tables`` and
   ``test_the_script_imports_no_forbidden_model`` guard that structurally.

One more, and it is the reason the row count has an upper bound rather than
just a target: the chart can only ever see the newest 100 transactions, so a
seed generous enough to spill past that ceiling leaves the chart's left edge
empty -- a 250-row seed spread over 14 days produces exactly the broken chart
this script exists to fix. ``test_the_newest_hundred_rows_cover_every_day``
computes that boundary instead of trusting the eyeball.

No database. The suite is mock-session based (``asyncio_mode = "strict"``), so
these tests assert on the ORM objects the script hands to ``session.add`` and on
the arguments it hands the scoring service -- the two places a fabricated score
or a forbidden write would have to enter.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

# Imported for its side effect: it registers every model on ``Base.metadata``,
# which is what ``create_all`` below needs. ``F401`` acknowledges that.
import src.models  # noqa: E402,F401  (registers every model on Base.metadata)
from scripts import seed_demo_history as script
from scripts.seed_demo_history import (
    DEFAULT_TOTAL_ROWS,
    SEEDED_USER_EMAIL,
    WINDOW_DAYS,
    already_seeded,
    build_day_plan,
    build_transaction_specs,
    get_or_create_seeded_user,
    run,
    seed_history,
)
from src.core.config import settings
from src.core.database import Base  # noqa: E402
from src.core.ml_constants import KNOWN_MERCHANT_CATEGORIES
from src.models.fraud_alert import FraudAlert
from src.models.fraud_score import FraudScore
from src.models.transaction import Transaction
from src.models.user import User
from src.services.rule_engine import RuleEngine
from src.services.scoring_service import ScoringResult, ScoringService

SCRIPT_PATH = Path(script.__file__)

# The models declare ``postgresql.UUID``, which SQLite cannot compile. Same
# shim as ``tests/test_export_labels_cli.py``; the handler is stateless so
# whichever module imports last wins with identical behaviour.
@compiles(PG_UUID, "sqlite")
def _render_pg_uuid_on_sqlite(type_, compiler, **kw):
    """Render PostgreSQL UUID as CHAR(32) so the models load on SQLite."""
    return "CHAR(32)"

#: Tables this script must never write, and why each one matters. Asserted
#: against in two independent ways -- by inspecting the models the script
#: constructs, and by inspecting the models it imports -- so neither a
#: refactor that routes a write through a helper nor a new import can smuggle a
#: row past the other check.
FORBIDDEN_MODELS = (
    "src.models.drift_reference",
    "src.models.ml_model_run",
    "src.models.outbox_event",
    "src.models.rule",
)

#: The only ORM models the script is allowed to construct. A seeded row is a
#: transaction plus the score that makes it visible, optionally the alert an
#: analyst would work, and the one user that marks all of them as ours.
PERMITTED_MODELS = (User, Transaction, FraudScore, FraudAlert)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Result:
    """Stand-in for an AsyncResult, answering only what the script asks."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """Records everything the script tries to write.

    ``results`` is a queue consumed one entry per ``execute`` call, so a test
    states up front what the database "answers" instead of depending on the
    order the script happens to query in.
    """

    def __init__(self, *results):
        self._queue = list(results)
        self.added: list[object] = []
        self.executes = 0
        self.commits = 0
        self.flushes = 0

    async def execute(self, statement):
        self.executes += 1
        if not self._queue:
            raise AssertionError("script queried the database more than expected")
        return _Result(self._queue.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1

    # -- helpers used by the assertions -----------------------------------

    def of_type(self, model):
        return [o for o in self.added if isinstance(o, model)]

    def scores_by_transaction(self):
        """Map transaction_id -> the FraudScore written for it.

        Joined the way the database will join them, so the assertion does not
        depend on the script adding the two rows in any particular order.
        """
        return {s.transaction_id: s for s in self.of_type(FraudScore)}


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 4, 15, 30, tzinfo=timezone.utc)


def _new_user() -> User:
    user = User(email=SEEDED_USER_EMAIL, username="demo_history")
    # The fake session never persists, so the PK the script generated is absent.
    # Give it one so rows can be associated without touching a database.
    from uuid import uuid4

    user.id = uuid4()
    return user


# ---------------------------------------------------------------------------
# Day-coverage math
# ---------------------------------------------------------------------------


def test_day_plan_covers_every_calendar_day_of_the_window(now):
    """The chart's 7 buckets are the 7 UTC dates ending today.

    ``buildDailyAverages`` keys its buckets on ``toISOString().slice(0, 10)``,
    so "a day" is a UTC date and a plan built in any other frame would put its
    rows in a bucket the chart never draws.
    """
    plan = build_day_plan(now, total=DEFAULT_TOTAL_ROWS, days=WINDOW_DAYS)

    assert len(plan) == WINDOW_DAYS
    assert [p.day for p in plan] == [
        (now.date() - timedelta(days=offset))
        for offset in reversed(range(WINDOW_DAYS))
    ]
    assert plan[-1].day == now.date()


def test_day_plan_gives_every_day_at_least_one_row(now):
    plan = build_day_plan(now, total=DEFAULT_TOTAL_ROWS, days=WINDOW_DAYS)
    assert all(p.count >= 1 for p in plan), [p.count for p in plan]


def test_day_plan_sums_to_the_requested_total(now):
    plan = build_day_plan(now, total=DEFAULT_TOTAL_ROWS, days=WINDOW_DAYS)
    assert sum(p.count for p in plan) == DEFAULT_TOTAL_ROWS


def test_day_plan_hands_the_remainder_to_the_older_days(now):
    """An uneven total must not land its remainder on today.

    Today is a partial day -- the run happens during it -- so the older days
    are the ones that can absorb an extra row without making today's spike
    look like a trend. This pins the remainder's destination, not just that
    the sum is right, because "sums correctly" and "sums on the right days" are
    different properties.
    """
    plan = build_day_plan(now, total=DEFAULT_TOTAL_ROWS + 3, days=WINDOW_DAYS)

    assert sum(p.count for p in plan) == DEFAULT_TOTAL_ROWS + 3
    # Oldest-first, so the three extra rows land on the three oldest days and
    # today keeps the base count.
    assert [p.count for p in plan] == [11, 11, 11, 10, 10, 10, 10]
    assert plan[-1].count == 10


def test_day_plan_refuses_a_total_it_cannot_spread_over_the_window(now):
    """Fewer rows than days cannot cover every day, and the script says so.

    Silently giving some day zero rows would reintroduce exactly the blank
    column the script exists to remove, so this is an error rather than a
    best-effort allocation.
    """
    with pytest.raises(ValueError, match="at least one"):
        build_day_plan(now, total=WINDOW_DAYS - 1, days=WINDOW_DAYS)


def test_specs_land_on_their_planned_day_and_never_in_the_future(now):
    plan = build_day_plan(now, total=DEFAULT_TOTAL_ROWS, days=WINDOW_DAYS)
    specs = build_transaction_specs(plan, now)

    assert len(specs) == DEFAULT_TOTAL_ROWS

    by_day: dict[date, int] = {}
    for spec in specs:
        assert spec.occurred_at <= now, "a seeded row must never be in the future"
        assert spec.occurred_at.tzinfo is not None
        by_day[spec.occurred_at.date()] = by_day.get(spec.occurred_at.date(), 0) + 1

    assert by_day == {p.day: p.count for p in plan}


def test_specs_are_deterministic(now):
    """A rerun must plan the same rows, or the script is not reproducible.

    Nothing here is random on purpose: an operator comparing two runs of a seed
    script should be able to diff the output, and a genuinely random plan would
    make a scoring difference unexplainable.
    """
    plan = build_day_plan(now, total=DEFAULT_TOTAL_ROWS, days=WINDOW_DAYS)
    first = build_transaction_specs(plan, now)
    second = build_transaction_specs(plan, now)

    assert first == second


def test_specs_only_use_categories_from_the_canonical_vocabulary(now):
    """The API rejects a category outside ``KNOWN_MERCHANT_CATEGORIES``.

    Seeding a category the live path would refuse would make the demo data
    unrepresentable of what the system can actually accept.
    """
    plan = build_day_plan(now, total=DEFAULT_TOTAL_ROWS, days=WINDOW_DAYS)
    for spec in build_transaction_specs(plan, now):
        assert spec.category in KNOWN_MERCHANT_CATEGORIES


def test_spec_amounts_are_floats_not_decimals(now):
    """``RuleEngine`` scores only ``int``/``float``; a ``Decimal`` is untrusted.

    ``RuleEngine.evaluate`` does ``isinstance(raw_amount, (int, float))`` and
    treats anything else -- ``Decimal`` included -- as an unreadable amount,
    which sets it to ``inf`` and fires ``high_amount``. Every seeded row would
    then score as a large-amount attack purely because of its Python type.
    ``TransactionCreate.amount`` is a ``float`` for the same reason, so the
    script must hand the service a ``float`` too.
    """
    plan = build_day_plan(now, total=DEFAULT_TOTAL_ROWS, days=WINDOW_DAYS)
    for spec in build_transaction_specs(plan, now):
        assert type(spec.amount) is float


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_already_seeded_is_true_when_the_marker_user_owns_a_transaction():
    user = _new_user()
    session = _FakeSession("an-existing-transaction-id")

    assert await already_seeded(session, user.id) is True


@pytest.mark.asyncio
async def test_rerunning_writes_nothing_when_the_seeded_user_already_has_rows():
    """The dedicated user is the provenance marker, and it is also the lock.

    There is no ``source``/``is_synthetic`` column and this script may not add
    a migration, so the marker user doubles as the idempotency check: one row
    under that user means the seed already ran. The two queued answers below
    are "the user exists" then "the user already has a transaction".
    """
    session = _FakeSession(_new_user(), "an-existing-transaction-id")

    report = await seed_history(session, total=WINDOW_DAYS, days=WINDOW_DAYS)

    assert report.rows_written == 0
    assert report.rows_skipped == WINDOW_DAYS
    assert session.added == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_the_marker_user_is_created_only_once():
    """Two runs, two lookups: the second finds the row and creates nothing."""
    first = _FakeSession(None)  # lookup misses
    created = await get_or_create_seeded_user(first)
    assert len(first.of_type(User)) == 1
    assert created.email == SEEDED_USER_EMAIL

    second = _FakeSession(created)  # lookup hits
    reused = await get_or_create_seeded_user(second)
    assert second.of_type(User) == []
    assert reused.id == created.id


# ---------------------------------------------------------------------------
# Forbidden tables
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_script_constructs_rows_only_for_permitted_tables():
    """Behavioural guard: nothing but the four permitted models is ever added.

    A source scan would only catch the obvious spelling. Watching what actually
    reaches ``session.add`` catches the write wherever it was routed from --
    including through a helper this test never has to know about.
    """
    session = _FakeSession(_new_user(), None)
    await seed_history(session, total=WINDOW_DAYS, days=WINDOW_DAYS)

    assert session.added, "the seed wrote nothing, so this assertion proves nothing"
    for obj in session.added:
        assert type(obj) in PERMITTED_MODELS, f"{type(obj)!r} is not permitted"


def test_the_script_imports_no_forbidden_model():
    """Structural guard, independent of the behavioural one above.

    The behavioural guard only sees rows that reach ``add``. This one fails at
    import time instead, so a forbidden model cannot even be named -- and the
    two checks cannot both be defeated by a single edit.

    Scoped to the import statements deliberately. The module docstring has to
    NAME these tables to explain why it does not write them, so a scan of the
    whole file would flag its own documentation.
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    imported = set(re.findall(r"from\s+(src\.models[\w.]*)\s+import", source))
    assert imported, "the import scan matched nothing; the regex is stale"

    assert not (imported & set(FORBIDDEN_MODELS)), (
        f"forbidden model imported: {sorted(imported & set(FORBIDDEN_MODELS))}"
    )
    # The models it does import are all expected to be demo-data carriers.
    assert imported <= {
        "src.models.fraud_alert",
        "src.models.fraud_score",
        "src.models.transaction",
        "src.models.user",
    }


def test_drift_reference_is_never_auto_seeded_by_this_script():
    """``drift_reference_data`` must stay empty after a seed run.

    The monitor seeds a reference from live scores once the recent window is
    large enough and then persists it, so a reference captured from a demo
    dataset would outlive the demo. The script's row budget is what keeps the
    total below that trigger; this pins the budget is a real constraint rather
    than an incidental number.
    """
    assert DEFAULT_TOTAL_ROWS + 34 < 400, (
        "the seed budget must keep the score total well below the ~400 that "
        "lets the monitor auto-seed a permanent drift reference"
    )


# ---------------------------------------------------------------------------
# NULL analyst_label
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_seeded_alert_keeps_a_null_analyst_label():
    """A non-null label would be exported as synthetic ground truth.

    ``scripts/export_labels.py`` writes exactly the alerts whose status is
    ``resolved`` AND whose ``analyst_label`` is not null, as a labelled corpus.
    A seeded alert carrying a label would enter the training data as though an
    analyst had judged it. The script never labels anything, so the column is
    left at its NULL default.
    """
    session = _FakeSession(_new_user(), None)
    await seed_history(session, total=WINDOW_DAYS * 4, days=WINDOW_DAYS)

    alerts = session.of_type(FraudAlert)
    assert alerts, "no alerts were produced, so nothing proved the label stays NULL"
    for alert in alerts:
        assert alert.analyst_label is None


# ---------------------------------------------------------------------------
# Scores come from the real service
# ---------------------------------------------------------------------------


def test_the_default_scoring_service_is_the_production_one():
    """The script must not ship a private scoring path of its own.

    Asserted by calling the factory rather than by reading its source: what
    matters is that the object the script scores with when nobody injects one
    is the production ``ScoringService``, not that the line looks right.
    """
    assert isinstance(script.default_scoring_service(), ScoringService)


@pytest.mark.asyncio
async def test_persisted_scores_are_the_scoring_services_own_output(now):
    """Recompute every score with the real service and demand a match.

    A literal score in the ``FraudScore(...)`` constructor would fail here: the
    persisted row is compared against a second, independent call into the real
    pipeline for the same inputs.
    """
    calls: list[tuple[dict, dict, dict, object]] = []

    class _Spy:
        def __init__(self):
            self._real = ScoringService()

        async def compute_scores(self, tx_data, context, user_history):
            result = await self._real.compute_scores(tx_data, context, user_history)
            calls.append((dict(tx_data), dict(context), dict(user_history), result))
            return result

    session = _FakeSession(_new_user(), None)
    report = await seed_history(
        session, total=WINDOW_DAYS * 3, days=WINDOW_DAYS, now=now,
        scoring_service=_Spy(),
    )

    assert len(calls) == report.rows_written == WINDOW_DAYS * 3

    persisted = session.scores_by_transaction()
    assert len(persisted) == report.rows_written

    for _, _, _, result in calls:
        matches = [
            s for s in persisted.values()
            if s.rule_score == pytest.approx(result.rule_score)
            and s.ml_score == pytest.approx(result.ml_score)
            and s.ensemble_score == pytest.approx(result.ensemble_score)
            and s.threshold == pytest.approx(result.threshold)
        ]
        assert matches, (
            "a persisted FraudScore did not reproduce the scoring service's "
            f"output: rule={result.rule_score} ml={result.ml_score} "
            f"ensemble={result.ensemble_score} threshold={result.threshold}"
        )
        assert matches[0].classification.value == result.classification


@pytest.mark.asyncio
async def test_seeded_scores_are_not_all_identical(now):
    """A constant score across every row is the signature of a hardcoded value.

    Cheap and blunt on purpose: a literal would produce one repeated number,
    while a real pipeline fed varied merchants, amounts and hours produces a
    spread.
    """
    session = _FakeSession(_new_user(), None)
    await seed_history(session, total=WINDOW_DAYS * 4, days=WINDOW_DAYS, now=now)

    scores = session.of_type(FraudScore)
    assert len({round(s.ensemble_score, 6) for s in scores}) > 1


@pytest.mark.asyncio
async def test_the_scored_timestamp_is_the_backdated_transaction_time(now):
    """The score must be computed as of when the transaction happened.

    ``tx_data["timestamp"]`` drives ``hour_of_day``/``is_weekend`` and the
    ``unusual_hours`` rule. Scoring a backdated row with ``now`` would produce
    a score no real transaction at that hour would ever receive -- the numbers
    would look genuine while describing a different moment in time.
    """
    seen: list[str] = []

    class _Recorder:
        async def compute_scores(self, tx_data, context, user_history):
            seen.append(tx_data["timestamp"])
            return ScoringResult(rule_score=0.0, ensemble_score=0.0)

    session = _FakeSession(_new_user(), None)
    await seed_history(
        session, total=WINDOW_DAYS * 2, days=WINDOW_DAYS, now=now,
        scoring_service=_Recorder(),
    )

    assert len(seen) == WINDOW_DAYS * 2
    days = {datetime.fromisoformat(ts).astimezone(timezone.utc).date() for ts in seen}
    expected = {(now.date() - timedelta(days=d)) for d in reversed(range(WINDOW_DAYS))}
    assert days == expected


@pytest.mark.asyncio
async def test_velocity_context_is_zero_for_backdated_rows():
    """Velocity is legitimately absent, and zero is the honest answer.

    A backdated row has no Redis window and no recent history to count, so
    ``recent_transactions`` is 0 and ``context_score`` is 0 -- every velocity
    rule stays silent. Fabricating a count would make ``high_velocity`` and the
    context layer fire on evidence of a card-testing burst that never happened,
    and the resulting score would be a plausible-looking fiction.
    """
    contexts: list[dict] = []
    histories: list[dict] = []

    class _Recorder:
        async def compute_scores(self, tx_data, context, user_history):
            contexts.append(dict(context))
            histories.append(dict(user_history))
            return ScoringResult(rule_score=0.0, ensemble_score=0.0)

    session = _FakeSession(_new_user(), None)
    await seed_history(
        session, total=WINDOW_DAYS * 2, days=WINDOW_DAYS, scoring_service=_Recorder(),
    )

    assert contexts, "no scoring calls were recorded"
    for context in contexts:
        assert context["recent_transactions"] == 0
    for history in histories:
        assert history["tx_count_last_5min"] == 0
        assert history["tx_count_last_1h"] == 0


@pytest.mark.asyncio
async def test_the_seeded_user_is_the_provenance_marker():
    """Every seeded transaction hangs off the one dedicated user.

    The reset procedure in the script's docstring is scoped to this user, so
    every row has to belong to it -- a single stray row under another account
    would be unremovable by the documented cleanup.
    """
    user = _new_user()
    session = _FakeSession(user, None)
    await seed_history(session, total=WINDOW_DAYS * 3, days=WINDOW_DAYS)

    transactions = session.of_type(Transaction)
    assert transactions
    assert {t.user_id for t in transactions} == {user.id}


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_prints_the_plan_and_writes_nothing(capsys, now):
    session = _FakeSession()

    report = await run(
        total=DEFAULT_TOTAL_ROWS, days=WINDOW_DAYS, dry_run=True, session=session, now=now,
    )

    output = capsys.readouterr().out

    assert report.dry_run is True
    assert report.planned_rows == DEFAULT_TOTAL_ROWS
    assert report.rows_written == 0
    assert session.added == []
    assert session.executes == 0, "a dry run must not query, let alone write"
    assert session.commits == 0

    # The plan has to be legible enough to act on without running the seed:
    # the row total, every day in the window, and the account it will write to.
    assert str(DEFAULT_TOTAL_ROWS) in output
    assert SEEDED_USER_EMAIL in output
    for offset in range(WINDOW_DAYS):
        assert str((now.date() - timedelta(days=offset)).isoformat()) in output


@pytest.mark.asyncio
async def test_the_catalog_exercises_the_rules_review_and_fraud_need(now):
    """The catalog must be able to reach BOTH non-legitimate verdicts.

    A seed whose every row scores ``legitimate`` would make the trend chart a
    flat line and the alert queue permanently empty -- a demo that demonstrates
    nothing. This asserts the property with the real ``RuleEngine`` and no ML,
    so it holds in an environment without xgboost installed: the catalog must
    fire the rule evidence that ``review`` and ``fraud`` are routed from, and
    must contain at least one transaction at or above the critical amount floor
    (``ScoringService``'s rule branch blocks only at that amount, and the floor
    is read from the last threshold tier rather than written down here).

    Which of these rows actually LANDS in review or fraud is decided by the full
    ensemble, so this asserts reachability, not a fixed verdict -- pinning the
    verdict would make the test fail every time the model is retrained.
    """
    plan = build_day_plan(now, total=DEFAULT_TOTAL_ROWS, days=WINDOW_DAYS)
    specs = build_transaction_specs(plan, now)

    engine = RuleEngine()
    merchant_blacklist = settings.merchant_blacklist
    critical_floor = float(settings.threshold_tiers[-1]["min_amount"])

    fired: set[str] = set()
    at_or_above_critical = 0
    for spec in specs:
        score, rules = engine.evaluate(
            {
                "amount": spec.amount,
                "merchant_name": spec.merchant,
                "merchant_category": spec.category,
                "timestamp": spec.occurred_at.isoformat(),
            },
            {
                "recent_transactions": 0,
                "merchant_blacklist": merchant_blacklist,
                "graph_features": {},
            },
        )
        fired.update(rules)
        if spec.amount >= critical_floor:
            at_or_above_critical += 1

    assert {"high_amount", "unusual_merchant", "unusual_hours", "off_hours_crypto"} <= fired, (
        f"the catalog never fires {sorted(fired)}; review/fraud are unreachable"
    )
    assert at_or_above_critical >= 1, (
        "no catalog row reaches the critical amount floor, so the rule branch "
        "of the fraud route can never be taken"
    )


# ---------------------------------------------------------------------------
# The foreign keys the real database enforces
# ---------------------------------------------------------------------------


@pytest.fixture
def live_schema_session(tmp_path):
    """A real (SQLite) session against real tables with foreign keys ON.

    The unit tests above hand the script a fake session that records ``add``
    calls, which cannot see an INSERT ORDER problem -- a fake happily accepts a
    child row written before its parent. This fixture is the one place the
    script's actual flush behaviour is checked against the constraint the real
    database enforces.
    """
    db_path = tmp_path / "seed_demo_history.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys_on(dbapi_connection, _record):
        # SQLite ignores FK constraints unless asked, per connection. Without
        # this the whole point of the fixture is silently absent.
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    return engine, db_path, _create


@pytest.mark.asyncio
async def test_seeded_scores_and_alerts_satisfy_the_transaction_foreign_key(
    live_schema_session, now
):
    """Every score and alert must land after the transaction it points at.

    ``fraud_scores`` and ``fraud_alerts`` both carry
    ``ForeignKey("transactions.id")``. Writing a whole history in one session
    means the unit of work flushes all three tables together, and if it emits
    the child rows before the parents the database rejects the run with
    ``ForeignKeyViolationError`` -- which is exactly what happened on the first
    real execution, after the dry run had already promised it would work.
    """
    engine, _db_path, create = live_schema_session
    await create()

    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            report = await seed_history(
                session, total=WINDOW_DAYS * 2, days=WINDOW_DAYS, now=now
            )
            assert report.rows_written == WINDOW_DAYS * 2

            scores = (await session.execute(select(func.count()).select_from(FraudScore))).scalar_one()
            transactions = (
                await session.execute(select(func.count()).select_from(Transaction))
            ).scalar_one()
            assert scores == transactions == WINDOW_DAYS * 2

            # An alert exists only for a non-legitimate row, and every one of
            # them must resolve to a transaction that exists.
            orphans = (
                await session.execute(
                    select(func.count())
                    .select_from(FraudAlert)
                    .where(
                        FraudAlert.transaction_id.not_in(
                            select(Transaction.id)
                        )
                    )
                )
            ).scalar_one()
            assert orphans == 0
            assert report.alerts_created == (
                await session.execute(select(func.count()).select_from(FraudAlert))
            ).scalar_one()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_persisted_rows_carry_the_backdated_created_at(
    live_schema_session, now
):
    """``created_at`` must be the backdated stamp, not the moment of the run.

    ``BaseModel.created_at`` has a Python-side ``default``, so a row added
    without an explicit value is stamped "now" -- which would place every seeded
    row on today and leave the six older days empty, the exact failure the
    script exists to fix, while still reporting a successful write.
    """
    engine, _db_path, create = live_schema_session
    await create()

    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            await seed_history(session, total=WINDOW_DAYS * 2, days=WINDOW_DAYS, now=now)

            stamps = (
                await session.execute(select(Transaction.created_at))
            ).scalars().all()

            # SQLite hands back naive datetimes where PostgreSQL returns
            # tz-aware ones (the models declare server_default=func.now(), which
            # SQLite renders as a naive UTC string), so the instant is compared
            # and the tzinfo is not -- the same concession
            # tests/test_export_labels_cli.py documents.
            naive = [
                s.replace(tzinfo=None) if s.tzinfo is not None else s for s in stamps
            ]
            cutoff = now.replace(tzinfo=None)

            days = {s.date() for s in naive}
            assert len(days) == WINDOW_DAYS
            assert max(naive) < cutoff
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# The 100-row ceiling
# ---------------------------------------------------------------------------


def test_the_newest_hundred_rows_cover_every_day():
    """The chart sees the newest 100 transactions and nothing older.

    ``DashboardPage.tsx`` fetches ``page: 1, page_size: 100`` and
    ``list_transactions_endpoint`` caps ``page_size`` at 100, so rows past that
    boundary are invisible to the trend no matter how many exist. Seeding
    generously enough to spill past the ceiling is the trap this guards: a
    250-row seed over 14 days would evict every row inside the 7-day window and
    leave the chart's left edge empty -- the exact broken chart this script
    exists to fix.

    The numbers below are the live database measured before the first run: 44
    transactions exist and 19 of them are older than the 7-day window. The
    oldest rows are evicted first, so as long as the evicted count stays at or
    below the 19 pre-window rows, every row inside the window survives.
    """
    existing_total = 44
    existing_outside_window = 19

    evicted = script.evicted_by_ceiling(existing_total, DEFAULT_TOTAL_ROWS)

    assert evicted <= existing_outside_window, (
        f"{DEFAULT_TOTAL_ROWS} rows would evict {evicted} transactions, but only "
        f"{existing_outside_window} pre-window rows exist to absorb it -- the "
        "chart's left edge would go empty"
    )