"""Startup tests for EmbeddingWorker — R4-001 (audit-wave1-blockers Phase 2).

Proves that ``process_queue()`` can be started without the latent
AttributeError caused by scheduling a non-existent ``_recovery_loop``, and
that a recovery pass is actually scheduled once the worker is running.

All Redis interaction and the heavy sentence-transformer model are mocked,
mirroring the style of ``tests/test_shap_worker.py`` / ``tests/test_llm_worker.py``.
"""

import asyncio
import time
from contextlib import suppress
from unittest.mock import AsyncMock, patch

import pytest

from src.workers.embedding_worker import EmbeddingWorker
from tests.workers.helpers import idle_xreadgroup


async def _wait_for(predicate, timeout: float = 2.0) -> bool:
    """Poll ``predicate`` until truthy or ``timeout`` seconds elapse."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


@pytest.mark.asyncio
async def test_process_queue_starts_without_attribute_error():
    """process_queue() must start cleanly — no AttributeError for _recovery_loop."""
    recover_mock = AsyncMock(return_value=[])

    with patch("src.workers.embedding_worker.MerchantEmbeddingService"), patch(
        "src.workers.embedding_worker.ensure_consumer_group", new=AsyncMock()
    ), patch(
        "src.workers.embedding_worker.recover_pending_messages", new=recover_mock
    ), patch(
        "src.workers.embedding_worker.RECOVERY_INTERVAL", 0.02
    ):
        worker = EmbeddingWorker()
        worker.redis_client = AsyncMock()
        worker.redis_client.xreadgroup = idle_xreadgroup()

        task = asyncio.create_task(worker.process_queue())
        try:
            started = await _wait_for(
                lambda: recover_mock.await_count > 0, timeout=2.0
            )
            assert started, (
                "recovery pass was never scheduled/executed after startup"
            )
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_process_queue_keeps_running_after_startup():
    """The main read loop keeps consuming while the recovery task runs alongside."""
    recover_mock = AsyncMock(return_value=[])

    with patch("src.workers.embedding_worker.MerchantEmbeddingService"), patch(
        "src.workers.embedding_worker.ensure_consumer_group", new=AsyncMock()
    ), patch(
        "src.workers.embedding_worker.recover_pending_messages", new=recover_mock
    ), patch(
        "src.workers.embedding_worker.RECOVERY_INTERVAL", 0.02
    ):
        worker = EmbeddingWorker()
        worker.redis_client = AsyncMock()
        worker.redis_client.xreadgroup = idle_xreadgroup()

        task = asyncio.create_task(worker.process_queue())
        try:
            # Give both loops time to spin; neither may raise.
            await asyncio.sleep(0.1)

            assert not task.done(), (
                f"process_queue exited early: {task.exception()!r}"
            )
            assert recover_mock.await_count >= 1, (
                "recovery task did not run at least one cycle"
            )
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
