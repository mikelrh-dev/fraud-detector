"""Recovery behavior tests for EmbeddingWorker._recovery_loop — R4-001.

Proves the XAUTOCLAIM-based recovery semantics:
- a stale PEL entry (> PENDING_TIMEOUT_MS idle) is claimed, reprocessed through
  process_message, and ACKed out of the PEL;
- a fresh PEL entry (idle < threshold) is NOT claimed — nothing is processed
  or ACKed for it.
"""

import asyncio
import json
import time
from contextlib import suppress
from unittest.mock import AsyncMock, patch

import pytest

from src.core.stream_dlq import PENDING_TIMEOUT_MS
from src.workers.embedding_worker import (
    CONSUMER_NAME,
    GROUP_NAME,
    STREAM_NAME,
    EmbeddingWorker,
)
from tests.workers.helpers import idle_xreadgroup

STALE_MESSAGE_ID = "1526569495631-0"
TXN_ID = "txn-recovered-1"


async def _wait_for(predicate, timeout: float = 2.0) -> bool:
    """Poll ``predicate`` until truthy or ``timeout`` seconds elapse."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


def _stale_fields() -> dict:
    """Stream fields shape as stored by the publisher (bytes keys)."""
    payload = {"transaction_id": TXN_ID, "merchant_name": "AMAZ0N_STORE"}
    return {b"data": json.dumps(payload).encode("utf-8")}


@pytest.mark.asyncio
async def test_stale_pel_entry_is_claimed_processed_and_acked():
    """Stale PEL entry: claimed → processed → result persisted → ACKed."""
    recover_mock = AsyncMock(return_value=[(STALE_MESSAGE_ID, _stale_fields())])

    with (
        patch("src.workers.embedding_worker.MerchantEmbeddingService") as service_cls,
        patch("src.workers.embedding_worker.ensure_consumer_group", new=AsyncMock()),
        patch(
            "src.workers.embedding_worker.recover_pending_messages", new=recover_mock
        ),
        patch("src.workers.embedding_worker.RECOVERY_INTERVAL", 0.02),
    ):
        service_cls.return_value.detect_spoofing.return_value = (
            False,
            "Amazon",
            0.91,
        )
        redis_mock = AsyncMock()
        redis_mock.xreadgroup = idle_xreadgroup()
        worker = EmbeddingWorker()
        worker.redis_client = redis_mock

        task = asyncio.create_task(worker.process_queue())
        try:
            acked = await _wait_for(
                lambda: redis_mock.xack.await_count > 0, timeout=2.0
            )

            # Claimed from PEL via the shared XAUTOCLAIM helper...
            recover_mock.assert_awaited()
            assert acked, "stale message was never ACKed after recovery"

            # ...reprocessed through process_message (result persisted)...
            assert redis_mock.setex.await_count >= 1
            key, ttl, raw_result = redis_mock.setex.await_args.args
            assert key == f"embedding_result:{TXN_ID}"
            assert ttl == 3600
            result = json.loads(raw_result)
            assert result["transaction_id"] == TXN_ID
            assert result["merchant_name"] == "AMAZ0N_STORE"
            assert result["is_spoofed"] is False

            # ...and ACKed with the exact stream/group/message coordinates.
            redis_mock.xack.assert_any_call(STREAM_NAME, GROUP_NAME, STALE_MESSAGE_ID)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_fresh_pel_entry_with_low_idle_time_is_not_claimed():
    """XAUTOCLAIM returning no messages (idle < threshold) must process/ACK nothing.

    Exercises the real ``recover_pending_messages`` helper against a mocked Redis
    client whose xautoclaim reports an empty claim batch.
    """
    redis_client = AsyncMock()
    redis_client.xreadgroup = idle_xreadgroup()
    redis_client.xautoclaim.return_value = ["0-0", []]  # nothing claimed yet

    with (
        patch("src.workers.embedding_worker.MerchantEmbeddingService"),
        patch("src.workers.embedding_worker.ensure_consumer_group", new=AsyncMock()),
        patch("src.workers.embedding_worker.RECOVERY_INTERVAL", 0.02),
    ):
        worker = EmbeddingWorker()
        worker.redis_client = redis_client

        task = asyncio.create_task(worker.process_queue())
        try:
            claimed = await _wait_for(
                lambda: redis_client.xautoclaim.await_count > 0, timeout=2.0
            )
            assert claimed, "recovery cycle never issued XAUTOCLAIM"

            # Claim attempt used the correct stream/group/consumer coordinates
            # and the stale threshold — but claimed nothing fresh.
            call = redis_client.xautoclaim.await_args
            assert call.args[:3] == (STREAM_NAME, GROUP_NAME, CONSUMER_NAME)
            assert call.kwargs.get("min_idle_time") == PENDING_TIMEOUT_MS

            await asyncio.sleep(0.05)
            assert redis_client.xack.await_count == 0, "fresh message must not be ACKed"
            assert redis_client.setex.await_count == 0, (
                "fresh message must not be processed"
            )
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


class TestFailureSemantics:
    """R4-005: processing failures must NOT be ACKed as success."""

    @pytest.mark.asyncio
    async def test_process_message_propagates_errors(self):
        """detect_spoofing raising must surface instead of being swallowed."""
        with patch(
            "src.workers.embedding_worker.MerchantEmbeddingService"
        ) as service_cls:
            service_cls.return_value.detect_spoofing.side_effect = RuntimeError("db down")
            worker = EmbeddingWorker()

            with pytest.raises(RuntimeError):
                await worker.process_message(
                    {"transaction_id": "t1", "merchant_name": "X"}
                )

    @pytest.mark.asyncio
    async def test_failing_message_stays_pending_unacked(self):
        """A failing message must remain unACKed so recovery can retry it."""
        with patch(
            "src.workers.embedding_worker.MerchantEmbeddingService"
        ) as service_cls, patch(
            "src.workers.embedding_worker.ensure_consumer_group", new=AsyncMock()
        ), patch(
            "src.workers.embedding_worker.recover_pending_messages",
            new=AsyncMock(return_value=[]),
        ), patch(
            "src.workers.embedding_worker.RECOVERY_INTERVAL", 0.02
        ):
            service_cls.return_value.detect_spoofing.side_effect = RuntimeError("db down")
            redis_mock = AsyncMock()
            redis_mock.xreadgroup = idle_xreadgroup()
            worker = EmbeddingWorker()
            worker.redis_client = redis_mock

            task = asyncio.create_task(worker.process_queue())
            await _wait_for(
                lambda: service_cls.return_value.detect_spoofing.call_count > 0,
                timeout=2.0,
            )
            await asyncio.sleep(0.05)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        redis_mock.xack.assert_not_awaited()


class TestEmbeddingMainRedisUrl:
    """R4-007 sibling: entry points honor settings.redis_url."""

    @pytest.mark.asyncio
    async def test_embedding_main_uses_settings_url(self):
        from src.core.config import settings
        from src.workers import embedding_worker

        stub_client = AsyncMock()

        async def fake_from_url(url):
            assert url == settings.redis_url
            return stub_client

        async def fake_run(self):
            pass

        async def fake_connect(self):
            self.redis_client = stub_client

        with patch.object(embedding_worker.redis, "from_url", fake_from_url), patch.object(
            embedding_worker.EmbeddingWorker, "run", fake_run
        ):
            await embedding_worker.main()
