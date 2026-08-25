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

    with patch(
        "src.workers.embedding_worker.MerchantEmbeddingService"
    ) as service_cls, patch(
        "src.workers.embedding_worker.ensure_consumer_group", new=AsyncMock()
    ), patch(
        "src.workers.embedding_worker.recover_pending_messages", new=recover_mock
    ), patch(
        "src.workers.embedding_worker.RECOVERY_INTERVAL", 0.02
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
            redis_mock.xack.assert_any_call(
                STREAM_NAME, GROUP_NAME, STALE_MESSAGE_ID
            )
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

    with patch("src.workers.embedding_worker.MerchantEmbeddingService"), patch(
        "src.workers.embedding_worker.ensure_consumer_group", new=AsyncMock()
    ), patch("src.workers.embedding_worker.RECOVERY_INTERVAL", 0.02):
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
            assert redis_client.xack.await_count == 0, (
                "fresh message must not be ACKed"
            )
            assert redis_client.setex.await_count == 0, (
                "fresh message must not be processed"
            )
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
