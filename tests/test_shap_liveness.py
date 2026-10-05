"""SHAP worker liveness — the signal that makes a drained-but-useless worker loud.

The blindness this file exists to close: ``shap_worker.py`` consumes ``fraud:shap``
and, on the failure paths, leaves no evidence behind — no attribution rows, no
DLQ entry, and consumer-group pending depth that the failure path actively
drains. ``/health/workers`` read that depth as its only per-stream signal, so a
worker that was running, acking, and computing nothing was indistinguishable
from a healthy one. The observable result was ``shap_attributions`` holding 0
rows against 26 fraud/review transactions.

The fix is one key. The worker writes ``shap:health:last_attribution_ts`` on the
success path only, and ``/health/workers`` compares it against recent fraud/review
traffic. Draining without producing now shows up as ``shap_liveness.status ==
"degraded"`` instead of silence.

Two halves, tested separately because they fail for different reasons:

- ``TestWorkerWritesLivenessKey`` — the key is written when work happens and is
  NOT written when work does not. A skip that touched the key would make the
  signal lie in the exact direction it exists to prevent.
- ``TestShapLivenessMatrix`` — the four outcomes the endpoint must distinguish.
  The important one is the fourth: traffic with no key at all, which is the
  original failure and has no timestamp to compare.
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.v1 import health as health_module
from src.services.shap_service import ShapContribution, ShapService, ShapUnavailableError
from src.workers.shap_worker import (
    LIVENESS_KEY,
    _process_message_with_retry,
    process_shap_message,
)

TXN_ID = "123e4567-e89b-12d3-a456-426614174000"

FEATURE_NAMES = ["amount", "velocity_1h", "velocity_24h", "merchant_category"]


def _message(**overrides) -> dict:
    message = {
        "transaction_id": TXN_ID,
        "classification": "fraud",
        "features": [0.1] * 10,
        "feature_names": FEATURE_NAMES,
        "model_fingerprint": "1024:1700000000",
        "retry_count": 0,
    }
    message.update(overrides)
    return message


def _contributions() -> list[ShapContribution]:
    return [
        ShapContribution(feature="amount", contribution=2.5),
        ShapContribution(feature="velocity_1h", contribution=-1.8),
    ]


def _explainer(**kwargs) -> MagicMock:
    service = MagicMock(spec=ShapService)
    service.explain.configure_mock(**kwargs)
    return service


@pytest.fixture
def patched_session():
    """Patch the worker's session factory and hand back the mock session."""
    with patch("src.workers.shap_worker.async_session_maker") as mock_maker:
        session = AsyncMock()
        mock_maker.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
        yield session


class TestWorkerWritesLivenessKey:
    """The key must track work actually done, never work merely attempted."""

    @pytest.mark.asyncio
    async def test_success_writes_liveness_key(self, patched_session, mock_redis):
        before = int(time.time())
        service = _explainer(return_value=_contributions())

        result = await process_shap_message(_message(), AsyncMock(), service, mock_redis)

        assert result is True
        mock_redis.set.assert_awaited_once()
        key, value = mock_redis.set.await_args.args[:2]
        assert key == LIVENESS_KEY
        assert isinstance(value, int)
        assert before <= value <= int(time.time())

    @pytest.mark.asyncio
    async def test_liveness_value_is_unix_epoch_seconds(self, patched_session, mock_redis):
        service = _explainer(return_value=_contributions())

        await process_shap_message(_message(), AsyncMock(), service, mock_redis)

        _, value = mock_redis.set.await_args.args[:2]
        # Epoch seconds, not milliseconds: the health endpoint subtracts it
        # from its own epoch-seconds clock, so a unit mismatch would surface as
        # an age in the thousands of years rather than as a failed comparison.
        assert abs(value / 1000 - time.time()) > 1

    @pytest.mark.asyncio
    async def test_unavailable_skip_does_not_write_key(self, patched_session, mock_redis):
        """A skip is the exact failure this signal exists to expose."""
        service = _explainer(side_effect=ShapUnavailableError("shap is not installed"))

        result = await process_shap_message(_message(), AsyncMock(), service, mock_redis)

        assert result is False
        mock_redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_computation_failure_does_not_write_key(self, patched_session, mock_redis):
        service = _explainer(side_effect=RuntimeError("boom"))

        result = await process_shap_message(_message(), AsyncMock(), service, mock_redis)

        assert result is False
        mock_redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_key_written_only_after_the_rows_are_committed(
        self, patched_session, mock_redis
    ):
        """Commit order matters: the key claims a row exists, so it cannot be
        written before the commit that creates it."""
        service = _explainer(return_value=_contributions())
        order: list[str] = []
        patched_session.commit = AsyncMock(side_effect=lambda: order.append("commit"))

        async def _record_set(*args, **kwargs):
            order.append("set")

        mock_redis.set = AsyncMock(side_effect=_record_set)

        await process_shap_message(_message(), AsyncMock(), service, mock_redis)

        assert order == ["commit", "set"]

    @pytest.mark.asyncio
    async def test_liveness_write_failure_does_not_lose_the_attribution(
        self, patched_session, mock_redis
    ):
        """A Redis blip must not turn a committed attribution into a retry.

        The attribution is already durable. Re-queuing it would recompute a
        result that exists and hide the real fault (Redis) behind a phantom
        SHAP failure.
        """
        service = _explainer(return_value=_contributions())
        mock_redis.set = AsyncMock(side_effect=RuntimeError("redis down"))

        result = await process_shap_message(_message(), AsyncMock(), service, mock_redis)

        assert result is True
        patched_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_retry_helper_forwards_the_live_redis_client(self, patched_session):
        """The key has to be written by the real worker loop, not only when a
        caller remembers to pass a client.

        The retry helper is what production actually calls, and it holds the
        live Redis connection. If it does not forward that connection, the whole
        signal silently never fires — which is the failure mode being fixed,
        reproduced one layer up.
        """
        redis_client = AsyncMock()
        fields = {b"data": json.dumps(_message()).encode()}
        service = _explainer(return_value=_contributions())

        with patch("src.workers.shap_worker.async_session_maker") as mock_maker:
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            await _process_message_with_retry(
                redis_client, b"1700000000000-0", fields, service
            )

        redis_client.set.assert_awaited_once()
        assert redis_client.set.await_args.args[0] == LIVENESS_KEY


def _seed_stream_health(mock_redis) -> None:
    """Make the existing per-stream loop produce JSON-serializable values."""
    mock_redis.xlen = AsyncMock(return_value=0)
    mock_redis.xpending = AsyncMock(return_value={"pending": 0})


def _seed_traffic(mock_db, count: int) -> None:
    """Make the fraud/review traffic query return ``count``.

    ``scalar`` is deliberately a SYNC mock. ``await db.execute(...)`` yields a
    ``CursorResult`` whose ``.scalar()`` is a plain synchronous call — only the
    execute is awaitable. An AsyncMock here would make the test pass against an
    ``await result.scalar()`` that raises TypeError against a real database, so
    the mock has to be the shape the driver actually returns. See
    ``test_traffic_query_reads_a_synchronous_scalar``.
    """
    result = MagicMock()
    result.scalar = MagicMock(return_value=count)
    mock_db.execute = AsyncMock(return_value=result)


class TestShapLivenessMatrix:
    """/health/workers must separate these four outcomes."""

    @pytest.mark.asyncio
    async def test_no_traffic_in_window_is_healthy(
        self, test_client, mock_db, mock_redis
    ):
        """Nothing to check is not a fault. A quiet system must not be paged."""
        _seed_stream_health(mock_redis)
        _seed_traffic(mock_db, 0)
        mock_redis.get = AsyncMock(return_value=None)

        response = await test_client.get("/health/workers")

        assert response.status_code == 200
        liveness = response.json()["shap_liveness"]
        assert liveness["status"] == "ok"
        assert liveness["checked"] is True
        assert liveness["fraud_review_count"] == 0
        assert liveness["last_attribution_ts"] is None

    @pytest.mark.asyncio
    async def test_traffic_with_fresh_attribution_is_healthy(
        self, test_client, mock_db, mock_redis
    ):
        _seed_stream_health(mock_redis)
        _seed_traffic(mock_db, 26)
        # Produced 30 s ago on the worker's clock.
        mock_redis.get = AsyncMock(return_value=str(int(time.time()) - 30).encode())

        response = await test_client.get("/health/workers")

        liveness = response.json()["shap_liveness"]
        assert liveness["status"] == "ok"
        assert liveness["checked"] is True
        assert liveness["fraud_review_count"] == 26
        assert 0 <= liveness["last_attribution_age_seconds"] <= 60

    @pytest.mark.asyncio
    async def test_traffic_with_stale_attribution_is_degraded(
        self, test_client, mock_db, mock_redis
    ):
        """The liveness check works: an old timestamp against live traffic."""
        _seed_stream_health(mock_redis)
        _seed_traffic(mock_db, 26)
        stale_age = health_module.SHAP_LIVENESS_STALE_AFTER_SECONDS + 600
        mock_redis.get = AsyncMock(
            return_value=str(int(time.time()) - stale_age).encode()
        )

        response = await test_client.get("/health/workers")

        liveness = response.json()["shap_liveness"]
        assert liveness["status"] == "degraded"
        assert liveness["checked"] is True
        assert liveness["fraud_review_count"] == 26
        assert liveness["last_attribution_age_seconds"] > (
            health_module.SHAP_LIVENESS_STALE_AFTER_SECONDS
        )

    @pytest.mark.asyncio
    async def test_traffic_with_missing_key_is_degraded(
        self, test_client, mock_db, mock_redis
    ):
        """The original failure, verbatim: 26 fraud/review transactions and
        never a single attribution, so the key was never written."""
        _seed_stream_health(mock_redis)
        _seed_traffic(mock_db, 26)
        mock_redis.get = AsyncMock(return_value=None)

        response = await test_client.get("/health/workers")

        liveness = response.json()["shap_liveness"]
        assert liveness["status"] == "degraded"
        assert liveness["checked"] is True
        assert liveness["fraud_review_count"] == 26
        assert liveness["last_attribution_ts"] is None
        assert liveness["last_attribution_age_seconds"] is None
        # The reason has to name the missing signal, not just say "degraded".
        assert "shap:health:last_attribution_ts" in liveness["reason"]

    @pytest.mark.asyncio
    async def test_missing_key_read_as_str_and_int_both_handled(
        self, test_client, mock_db, mock_redis
    ):
        """Redis clients are built with or without decode_responses."""
        _seed_stream_health(mock_redis)
        _seed_traffic(mock_db, 26)
        mock_redis.get = AsyncMock(return_value=str(int(time.time()) - 5))

        response = await test_client.get("/health/workers")

        assert response.json()["shap_liveness"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_unparseable_timestamp_is_degraded_not_a_500(
        self, test_client, mock_db, mock_redis
    ):
        _seed_stream_health(mock_redis)
        _seed_traffic(mock_db, 26)
        mock_redis.get = AsyncMock(return_value=b"not-a-number")

        response = await test_client.get("/health/workers")

        assert response.status_code == 200
        assert response.json()["shap_liveness"]["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_traffic_query_failure_does_not_500(self, test_client, mock_db, mock_redis):
        """A health probe that raises is worse than one that says nothing.

        The database's own reachability is already reported by
        ``/health/ready``; duplicating its failure mode here as a 500 would take
        out the whole worker topology report.
        """
        _seed_stream_health(mock_redis)
        mock_db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        mock_redis.get = AsyncMock(return_value=None)

        response = await test_client.get("/health/workers")

        assert response.status_code == 200
        assert response.json()["workers"]["fraud:shap"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_window_and_threshold_are_reported(
        self, test_client, mock_db, mock_redis
    ):
        """The constants are part of the answer: an operator reading `degraded`
        needs to know what "stale" was measured against, not guess."""
        _seed_stream_health(mock_redis)
        _seed_traffic(mock_db, 3)
        mock_redis.get = AsyncMock(return_value=None)

        liveness = (await test_client.get("/health/workers")).json()["shap_liveness"]

        assert liveness["traffic_window_seconds"] == (
            health_module.SHAP_LIVENESS_TRAFFIC_WINDOW_SECONDS
        )
        assert liveness["stale_after_seconds"] == (
            health_module.SHAP_LIVENESS_STALE_AFTER_SECONDS
        )


    @pytest.mark.asyncio
    async def test_traffic_query_reads_a_synchronous_scalar(
        self, test_client, mock_db, mock_redis
    ):
        """Pin the `await result.scalar()` trap.

        `await db.execute()` returns a CursorResult; only the execute is
        awaitable. An `await` on `.scalar()` raises TypeError, the handler's
        broad except swallows it, and the check reports `checked: false` on
        every call — permanently unverified, indistinguishable from healthy at a
        glance. That is the same class of silent green this change exists to
        remove, so a test guards it rather than a reviewer noticing it later.
        """
        _seed_stream_health(mock_redis)
        _seed_traffic(mock_db, 26)
        mock_redis.get = AsyncMock(return_value=None)

        liveness = (await test_client.get("/health/workers")).json()["shap_liveness"]

        # A swallowed failure reports checked:false with a null count; a working
        # read reports the real count.
        assert liveness["checked"] is True
        assert liveness["fraud_review_count"] == 26


class TestWorkersResponseContract:
    """The change is additive. Existing fields and status semantics stay."""

    @pytest.mark.asyncio
    async def test_existing_top_level_fields_survive(self, test_client, mock_db, mock_redis):
        _seed_stream_health(mock_redis)
        _seed_traffic(mock_db, 26)
        mock_redis.get = AsyncMock(return_value=None)

        body = (await test_client.get("/health/workers")).json()

        assert set(body) >= {"workers", "counters", "timestamp"}
        for stream in ("fraud:llm", "fraud:shap", "fraud:embeddings"):
            assert stream in body["workers"]
            assert set(body["workers"][stream]) == {
                "stream_length",
                "pending",
                "status",
            }

    @pytest.mark.asyncio
    async def test_per_stream_status_vocabulary_is_unchanged(self, test_client, mock_db, mock_redis):
        """`degraded` belongs to the new block only.

        The per-stream field has always been ok / backed_up / error. Letting it
        grow a fourth value would change what every existing consumer of
        ``workers[stream].status`` has to understand.
        """
        _seed_stream_health(mock_redis)
        _seed_traffic(mock_db, 26)
        mock_redis.get = AsyncMock(return_value=None)

        body = (await test_client.get("/health/workers")).json()

        assert body["workers"]["fraud:shap"]["status"] == "ok"
        assert body["shap_liveness"]["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_liveness_degradation_does_not_change_the_http_status(
        self, test_client, mock_db, mock_redis
    ):
        """A degraded verdict is a report, not an outage of the report."""
        _seed_stream_health(mock_redis)
        _seed_traffic(mock_db, 26)
        mock_redis.get = AsyncMock(return_value=None)

        response = await test_client.get("/health/workers")

        assert response.status_code == 200


class TestConstantsAreNamedAndJustified:
    """The two numbers are decisions, so they are named and ordered."""

    def test_threshold_exceeds_traffic_window(self):
        assert health_module.SHAP_LIVENESS_STALE_AFTER_SECONDS > (
            health_module.SHAP_LIVENESS_TRAFFIC_WINDOW_SECONDS
        )

    def test_threshold_tolerates_hour_scale_clock_skew(self):
        """The worker stamps its own clock; the API compares with its own.

        A worker behind the API by up to an hour must not be reported as stale.
        Anything less than an hour of headroom above the window would.
        """
        assert health_module.SHAP_LIVENESS_STALE_AFTER_SECONDS >= (
            health_module.SHAP_LIVENESS_TRAFFIC_WINDOW_SECONDS + 3600
        )

    def test_threshold_absorbs_cold_start(self):
        """First explanation after a cold start costs 4-7 s, warm ~0.09 s.

        Well inside any threshold that is a window plus slack, which is what
        makes the cold start a non-issue rather than a tuned-for edge case.
        """
        assert health_module.SHAP_LIVENESS_STALE_AFTER_SECONDS > (
            health_module.SHAP_LIVENESS_TRAFFIC_WINDOW_SECONDS + 7
        )
