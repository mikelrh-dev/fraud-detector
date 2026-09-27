"""A19: durable hand-off from the transaction commit to the Redis streams.

The scoring endpoint used to call ``publish_event`` three times, fire-and-forget,
each wrapped in try/except. A Redis blip therefore produced a committed,
fully-scored transaction with no LLM report, no SHAP attribution and no merchant
embedding, and nothing could ever discover the gap: the report endpoint reported
``pending`` forever.

Staging the event in the same session as the transaction fixes that, and it also
closes a race the audit did not name — publication happened *before* the commit
(the real commit is in the ``get_db`` teardown, after the handler returns), and
all three consumer tables have a hard FK to ``transactions.id``, so a worker
picking the message up in that window hit a foreign key violation.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.models.outbox_event import OutboxEvent
from src.services.outbox import (
    MAX_ATTEMPTS,
    OutboxRelay,
    drain_once,
    enqueue_event,
)

pytestmark = pytest.mark.asyncio


def _session_with(rows: list[OutboxEvent]) -> MagicMock:
    """A session whose `select(...).scalars().all()` yields `rows`."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def _row(event_id: int = 1, stream: str = "fraud:llm") -> OutboxEvent:
    return OutboxEvent(
        id=event_id,
        stream_name=stream,
        payload='{"transaction_id": "abc"}',
        attempts=0,
    )


class TestEnqueueIsSessionLocal:
    def test_does_not_touch_redis(self) -> None:
        """The request path must not depend on the event bus being up.

        This is the inversion that matters: previously an outage cost three
        events per transaction. Now it costs nothing at request time.
        """
        db = _session_with([])
        with patch("src.services.outbox.publish_event") as publish:
            enqueue_event(db, "fraud:llm", {"transaction_id": "abc"})
        publish.assert_not_called()

    def test_adds_a_row_to_the_session(self) -> None:
        db = _session_with([])
        enqueue_event(db, "fraud:llm", {"transaction_id": "abc"})
        db.add.assert_called_once()
        assert isinstance(db.add.call_args[0][0], OutboxEvent)

    def test_records_the_stream_name(self) -> None:
        db = _session_with([])
        enqueue_event(db, "fraud:shap", {"transaction_id": "abc"})
        assert db.add.call_args[0][0].stream_name == "fraud:shap"

    def test_payload_is_json(self) -> None:
        db = _session_with([])
        enqueue_event(db, "fraud:llm", {"transaction_id": "abc", "n": 1})
        assert '"transaction_id": "abc"' in db.add.call_args[0][0].payload

    def test_unserialisable_payload_does_not_raise(self) -> None:
        """A scored transaction must not be rolled back by a bad event payload.

        The transaction and its score are the valuable part; the event is
        enrichment. Losing the score because a payload held an exotic type would
        be the wrong trade.
        """
        db = _session_with([])

        class Exotic:
            def __repr__(self) -> str:
                return "<exotic>"

        # default=str means even this serialises, so assert the contract that
        # matters: it returns rather than propagating.
        assert enqueue_event(db, "fraud:llm", {"weird": Exotic()}) is not None


class TestDrain:
    async def test_publishes_and_deletes(self) -> None:
        db = _session_with([_row(1)])

        with patch("src.services.outbox.publish_event", new=AsyncMock()) as publish:
            published, failed = await drain_once(db)

        assert (published, failed) == (1, 0)
        publish.assert_awaited_once_with("fraud:llm", {"transaction_id": "abc"})
        db.commit.assert_awaited()

    async def test_no_rows_is_a_noop(self) -> None:
        db = _session_with([])
        with patch("src.services.outbox.publish_event", new=AsyncMock()) as publish:
            assert await drain_once(db) == (0, 0)
        publish.assert_not_called()

    async def test_a_failed_publish_keeps_the_row_for_retry(self) -> None:
        """The whole point: a blip must not lose the event."""
        db = _session_with([_row(1)])

        with patch(
            "src.services.outbox.publish_event",
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            published, failed = await drain_once(db)

        assert (published, failed) == (0, 1)
        # The delete is not issued, so the row survives to be retried.
        assert db.commit.await_count == 1

    async def test_a_failed_publish_increments_attempts(self) -> None:
        row = _row(1)
        db = _session_with([row])

        with patch(
            "src.services.outbox.publish_event",
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            await drain_once(db)

        assert row.attempts == 1
        assert "redis down" in row.last_error

    async def test_a_failure_does_not_block_the_rest_of_the_batch(self) -> None:
        rows = [_row(1), _row(2, "fraud:shap"), _row(3, "fraud:embeddings")]
        db = _session_with(rows)

        async def flaky(stream: str, _payload: dict) -> None:
            if stream == "fraud:shap":
                raise RuntimeError("nope")

        with patch("src.services.outbox.publish_event", new=AsyncMock(side_effect=flaky)):
            published, failed = await drain_once(db)

        assert (published, failed) == (2, 1)


class TestDrainAgainstARealDatabase:
    """The `WHERE attempts < MAX` and the `LIMIT` are SQL, so a mock cannot check
    them. A mocked session returns whatever rows it is handed and silently
    ignores both clauses, so these two behaviours were untestable until they
    were run against SQLite.
    """

    @pytest_asyncio.fixture
    async def real_db(self, tmp_path: Path):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from src.models.outbox_event import OutboxEvent as _Outbox

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'outbox.db'}")
        async with engine.begin() as conn:
            await conn.run_sync(_Outbox.__table__.create)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
        await engine.dispose()

    async def test_exhausted_rows_are_not_retried_forever(self, real_db) -> None:
        """A payload that cannot be published is a bug, not a retry loop."""
        real_db.add(OutboxEvent(stream_name="fraud:llm", payload="{}", attempts=MAX_ATTEMPTS))
        await real_db.commit()

        with patch("src.services.outbox.publish_event", new=AsyncMock()) as publish:
            await drain_once(real_db)

        publish.assert_not_called()

    async def test_the_batch_is_bounded_by_limit(self, real_db) -> None:
        for i in range(25):
            real_db.add(
                OutboxEvent(
                    stream_name="fraud:llm",
                    payload=f'{{"n": {i}}}',
                )
            )
        await real_db.commit()

        with patch("src.services.outbox.publish_event", new=AsyncMock()) as publish:
            await drain_once(real_db, batch_size=5)

        assert publish.await_count == 5, "LIMIT must cap one drain pass"

    async def test_published_rows_are_deleted(self, real_db) -> None:
        from sqlalchemy import func, select

        real_db.add(OutboxEvent(stream_name="fraud:llm", payload="{}"))
        await real_db.commit()

        with patch("src.services.outbox.publish_event", new=AsyncMock()):
            await drain_once(real_db)

        count = await real_db.scalar(select(func.count()).select_from(OutboxEvent))
        assert count == 0

    async def test_a_failed_publish_leaves_the_row_in_the_table(self, real_db) -> None:
        from sqlalchemy import func, select

        real_db.add(OutboxEvent(stream_name="fraud:llm", payload="{}"))
        await real_db.commit()

        with patch(
            "src.services.outbox.publish_event",
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            published, failed = await drain_once(real_db)

        assert (published, failed) == (0, 1)
        count = await real_db.scalar(select(func.count()).select_from(OutboxEvent))
        assert count == 1, "a failed publish must leave the event queued"


class TestRelay:
    async def test_survives_a_failing_iteration(self) -> None:
        """One blip must not silently stop all event delivery until a deploy."""
        relay = OutboxRelay(_NullSessionFactory(), interval=0.01)
        calls = {"n": 0}

        async def boom(session: object) -> tuple[int, int]:
            calls["n"] += 1
            raise RuntimeError("db gone")

        with patch("src.services.outbox.drain_once", new=boom):
            relay.start()
            await asyncio.sleep(0.08)
            await relay.stop()

        assert calls["n"] > 1, "the relay gave up after one failure"

    async def test_stop_is_clean_when_never_started(self) -> None:
        await OutboxRelay(_NullSessionFactory()).stop()

    async def test_stops_promptly(self) -> None:
        relay = OutboxRelay(_NullSessionFactory(), interval=5.0)
        with patch("src.services.outbox.drain_once", new=AsyncMock(return_value=(0, 0))):
            relay.start()
            await asyncio.sleep(0.02)
            await relay.stop()
        assert relay._task is None


class _NullSessionFactory:
    """Async context manager yielding a session object, for relay tests.

    The relay opens a session before draining, so a plain MagicMock fails at
    `async with` and the drain is never reached.
    """

    def __call__(self) -> "_NullSessionFactory":
        return self

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *exc: object) -> None:
        return None


class TestEndpointStagesInsteadOfPublishing:
    """The endpoint must no longer call Redis at all."""

    def test_scoring_does_not_publish_directly(self) -> None:
        """Guards the refactor at the call site, not just the service.

        A future edit that reintroduces a direct publish_event would restore the
        pre-commit race, and nothing else in the suite would notice.
        """
        path = Path(__file__).resolve().parents[2] / "src" / "api" / "v1" / "transactions.py"
        source = path.read_text(encoding="utf-8")
        # Only the explanatory comment may mention it.
        code_lines = [
            line
            for line in source.splitlines()
            if "publish_event" in line and not line.strip().startswith("#")
        ]
        assert code_lines == [], (
            f"transactions.py calls publish_event directly: {code_lines}"
        )

    def test_three_streams_are_staged(self) -> None:
        path = Path(__file__).resolve().parents[2] / "src" / "api" / "v1" / "transactions.py"
        source = path.read_text(encoding="utf-8")
        for stream in ("fraud:llm", "fraud:shap", "fraud:embeddings"):
            assert f'"{stream}"' in source, f"{stream} is no longer staged"
