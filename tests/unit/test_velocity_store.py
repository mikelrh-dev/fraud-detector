"""Unit tests for VelocityStore — Redis ZSET velocity counts with PG fallback.

Covers VEL-STORE-001..007: write path (ZADD/EXPIRE/trim, idempotent, best-effort),
read path (inclusive 5min/1h windows, 1 RTT pipeline, per-user isolation),
Postgres fallback (excludes soft-deleted, splits at 5 min), and the
`velocity_store_enabled` toggle.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError, TimeoutError

from src.core.config import settings
from src.services.velocity_store import (
    TRIM_SECONDS,
    VELOCITY_TTL_SECONDS,
    WINDOW_1H,
    WINDOW_5MIN,
    VelocityStore,
)

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.asyncio


def _store(redis: AsyncMock | None = None) -> VelocityStore:
    """Build a VelocityStore bound to a fake Redis client."""
    return VelocityStore(redis=redis or AsyncMock())


def _pipe(*execute_results: object) -> MagicMock:
    """Build a mock pipeline whose execute resolves to the given results.

    Queueing commands (zadd/expire/zremrangebyscore/zcount) are plain Mocks —
    the store queues them synchronously and only awaits execute(), matching
    the real redis.asyncio Pipeline API.
    """
    pipe = MagicMock()
    pipe.zadd = MagicMock(return_value=1)
    pipe.expire = MagicMock(return_value=True)
    pipe.zremrangebyscore = MagicMock(return_value=0)
    pipe.zcount = MagicMock(return_value=0)
    pipe.execute = AsyncMock(return_value=list(execute_results))
    return pipe


def _redis_with_pipe(pipe: MagicMock) -> AsyncMock:
    """Redis fake whose pipeline() returns `pipe` synchronously."""
    fake = AsyncMock()
    fake.pipeline = MagicMock(return_value=pipe)
    return fake


def _now_ms() -> int:
    return int(NOW.timestamp() * 1000)


class TestRecordTransaction:
    """VEL-STORE-001 — write path."""

    async def test_zadd_key_member_score_expire_and_trim_one_pipeline(self):
        """Recording must ZADD key `velocity:{uid}:tx`, member str(txn.id),
        score = epoch ms, EXPIRE the TTL, trim >24h, in a single pipeline RTT."""
        pipe = _pipe(1, True, 0)
        fake = _redis_with_pipe(pipe)
        store = _store(fake)

        uid, txn_id = uuid4(), uuid4()
        before_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000) - TRIM_SECONDS * 1000
        await store.record_transaction(uid, txn_id, NOW)
        after_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000) - TRIM_SECONDS * 1000

        key = f"velocity:{uid}:tx"
        fake.pipeline.assert_called_once()
        pipe.zadd.assert_called_once_with(key, {str(txn_id): _now_ms()})
        pipe.expire.assert_called_once_with(key, VELOCITY_TTL_SECONDS)
        # Trim boundary is real "now - 24h" (record has no `now` seam) — assert
        # it lands within a tolerance window around the wall clock.
        trim_args = pipe.zremrangebyscore.call_args.args
        assert trim_args[0] == key
        assert trim_args[1] == "-inf"
        assert before_ms <= trim_args[2] <= after_ms
        pipe.execute.assert_awaited_once()

    async def test_record_uses_current_time_when_created_at_missing(self):
        """Recording without a timestamp must fall back to the current time."""
        pipe = _pipe(1, True, 0)
        fake = _redis_with_pipe(pipe)
        store = _store(fake)

        before_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        await store.record_transaction(uuid4(), uuid4())
        after_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

        score = pipe.zadd.call_args.args[1]
        assert len(score) == 1
        recorded_ms = next(iter(score.values()))
        assert before_ms <= recorded_ms <= after_ms

    async def test_re_record_same_transaction_uses_same_member(self):
        """Re-recording the same transaction must target the same member/key
        (ZADD is idempotent at Redis level — VEL-STORE-001)."""
        pipe = _pipe(1, True, 0)
        fake = _redis_with_pipe(pipe)
        store = _store(fake)

        uid, txn_id = uuid4(), uuid4()
        await store.record_transaction(uid, txn_id, NOW)
        await store.record_transaction(uid, txn_id, NOW)

        key = f"velocity:{uid}:tx"
        member = {str(txn_id): _now_ms()}
        assert fake.pipeline.call_count == 2
        pipe.zadd.assert_any_call(key, member)
        pipe.zadd.assert_any_call(key, member)


class TestGetCounts:
    """VEL-STORE-002 / VEL-STORE-003 — read path."""

    async def test_maps_pipeline_results_to_both_windows(self):
        """A pipeline result [0, 2, 8] must map to {"5min": 2, "1h": 8}."""
        fake = _redis_with_pipe(_pipe(0, 2, 8))
        db = AsyncMock()
        store = _store(fake)

        counts = await store.get_counts(uuid4(), db, now=NOW)

        assert counts == {"5min": 2, "1h": 8}

    async def test_empty_set_returns_zero_counts(self):
        """An empty pipeline result must yield zeros for both windows."""
        fake = _redis_with_pipe(_pipe(0, 0, 0))
        db = AsyncMock()
        store = _store(fake)

        counts = await store.get_counts(uuid4(), db, now=NOW)

        assert counts == {"5min": 0, "1h": 0}

    async def test_inclusive_window_minima_and_single_round_trip(self):
        """ZCOUNT mins must be exactly now−300s / now−3600s (inclusive lower
        bound) with '+inf' max, trim must run before counting, and the whole
        read must be a single pipeline RTT."""
        pipe = _pipe(0, 1, 3)
        fake = _redis_with_pipe(pipe)
        db = AsyncMock()
        uid = uuid4()
        store = _store(fake)

        await store.get_counts(uid, db, now=NOW)

        key = f"velocity:{uid}:tx"
        pipe.zremrangebyscore.assert_called_once_with(
            key, "-inf", _now_ms() - TRIM_SECONDS * 1000
        )
        pipe.zcount.assert_any_call(key, _now_ms() - WINDOW_5MIN * 1000, "+inf")
        pipe.zcount.assert_any_call(key, _now_ms() - WINDOW_1H * 1000, "+inf")
        assert pipe.zcount.call_count == 2
        pipe.execute.assert_awaited_once()

    async def test_counts_isolated_per_user_key(self):
        """Reads for user A must only touch user A's key (VEL-STORE-003)."""
        pipe = _pipe(0, 3, 3)
        fake = _redis_with_pipe(pipe)
        db = AsyncMock()
        uid_a, uid_b = uuid4(), uuid4()
        store = _store(fake)

        await store.get_counts(uid_a, db, now=NOW)

        key_a = f"velocity:{uid_a}:tx"
        key_b = f"velocity:{uid_b}:tx"
        assert pipe.zcount.call_count == 2
        assert all(call.args[0] == key_a for call in pipe.zcount.call_args_list)
        assert all(key_b not in call.args[0] for call in pipe.zcount.call_args_list)


class TestFailureAndFallback:
    """VEL-STORE-001 (never raise), VEL-STORE-005 (PG fallback), VEL-STORE-007 (toggle)."""

    @pytest.mark.parametrize(
        "exc",
        [
            ConnectionError("redis down"),
            TimeoutError("redis slow"),
            OSError("socket error"),
        ],
    )
    async def test_record_never_raises_on_redis_failures(self, exc, caplog):
        """Recording must swallow RedisError/TimeoutError/OSError and log."""
        fake = AsyncMock()
        fake.pipeline = MagicMock(side_effect=exc)
        store = _store(fake)

        await store.record_transaction(uuid4(), uuid4(), NOW)  # must not raise

        assert any(
            "velocity" in r.message.lower() for r in caplog.records
        )

    async def test_read_redis_error_falls_back_to_postgres_and_logs(self, caplog):
        """On Redis read failure, counts must come from Postgres split at 5 min
        and a warning must be logged (VEL-STORE-005)."""
        fake = AsyncMock()
        fake.pipeline = MagicMock(side_effect=ConnectionError("redis down"))
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [
            NOW,
            NOW - timedelta(minutes=2),  # in 5min
            NOW - timedelta(minutes=30),  # in 1h but not 5min
        ]
        db.execute = AsyncMock(return_value=result)
        store = _store(fake)

        counts = await store.get_counts(uuid4(), db, now=NOW)

        assert counts == {"5min": 2, "1h": 3}
        db.execute.assert_awaited_once()
        assert any("redis" in r.message.lower() for r in caplog.records)

    async def test_pg_fallback_excludes_soft_deleted(self):
        """The fallback query must filter out soft-deleted transactions."""
        fake = AsyncMock()
        fake.pipeline = MagicMock(side_effect=ConnectionError("redis down"))
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [NOW - timedelta(minutes=1)]
        db.execute = AsyncMock(return_value=result)
        store = _store(fake)

        await store.get_counts(uuid4(), db, now=NOW)

        stmt = db.execute.await_args.args[0]
        compiled = str(stmt.compile())
        assert "deleted_at IS NULL" in compiled
        assert "created_at" in compiled

    async def test_pg_fallback_counts_txn_at_exactly_five_minutes(self):
        """A transaction exactly 5 minutes old must count in both windows
        (inclusive lower bound in the PG fallback too)."""
        fake = AsyncMock()
        fake.pipeline = MagicMock(side_effect=ConnectionError("redis down"))
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [NOW - timedelta(minutes=5)]
        db.execute = AsyncMock(return_value=result)
        store = _store(fake)

        counts = await store.get_counts(uuid4(), db, now=NOW)

        assert counts == {"5min": 1, "1h": 1}

    async def test_toggle_disabled_uses_postgres_only(self, monkeypatch):
        """With velocity_store_enabled=False, no Redis calls may happen and
        counts must come from Postgres (VEL-STORE-007)."""
        monkeypatch.setattr(settings, "velocity_store_enabled", False)
        fake = AsyncMock()
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [NOW - timedelta(minutes=1)]
        db.execute = AsyncMock(return_value=result)
        store = _store(fake)

        await store.record_transaction(uuid4(), uuid4(), NOW)
        counts = await store.get_counts(uuid4(), db, now=NOW)

        fake.pipeline.assert_not_called()
        fake.zadd.assert_not_called()
        assert counts == {"5min": 1, "1h": 1}