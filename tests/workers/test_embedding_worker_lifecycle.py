"""Lifecycle tests for EmbeddingWorker._recovery_loop — R4-001.

Verifies that the recovery loop:
- logs an exception on every failed iteration instead of crashing, and
- is cancelled cleanly on shutdown without unhandled-exception warnings.
"""

import asyncio
import logging
import time
from contextlib import suppress
from unittest.mock import AsyncMock, patch

import pytest

from src.workers.embedding_worker import EmbeddingWorker
from tests.workers.helpers import idle_xreadgroup

WORKER_LOGGER = "src.workers.embedding_worker"


async def _wait_for(predicate, timeout: float = 2.0) -> bool:
    """Poll ``predicate`` until truthy or ``timeout`` seconds elapse."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


def _make_worker() -> EmbeddingWorker:
    """Worker with mocked Redis client and stubbed embedding model."""
    with patch("src.workers.embedding_worker.MerchantEmbeddingService"):
        worker = EmbeddingWorker()
    worker.redis_client = AsyncMock()
    worker.redis_client.xreadgroup = idle_xreadgroup()
    return worker


@pytest.mark.asyncio
async def test_recovery_loop_logs_exception_on_every_iteration(caplog):
    """A failing recovery helper must be logged per iteration, never crash the loop."""
    failing_recover = AsyncMock(side_effect=RuntimeError("redis blew up"))
    worker = _make_worker()
    recovery_loop = getattr(worker, "_recovery_loop", None)
    assert recovery_loop is not None, "_recovery_loop is not implemented"

    with patch(
        "src.workers.embedding_worker.recover_pending_messages", new=failing_recover
    ), patch("src.workers.embedding_worker.RECOVERY_INTERVAL", 0.01), caplog.at_level(
        logging.ERROR, logger=WORKER_LOGGER
    ):
        task = asyncio.create_task(recovery_loop())
        ran_cycles = await _wait_for(
            lambda: failing_recover.await_count >= 3, timeout=2.0
        )
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    assert ran_cycles, "recovery loop died before completing several iterations"
    errors = [
        record
        for record in caplog.records
        if record.levelno == logging.ERROR and "redis blew up" in record.getMessage()
    ]
    assert errors, "recovery-loop exception was not logged"
    assert len(errors) >= 2, (
        "exception must be logged on every iteration, not just the first"
    )


@pytest.mark.asyncio
async def test_process_queue_shutdown_cancels_recovery_task_cleanly():
    """Cancelling process_queue must reap the recovery task — no strays, no errors."""
    recover_mock = AsyncMock(return_value=[])

    with patch(
        "src.workers.embedding_worker.ensure_consumer_group", new=AsyncMock()
    ), patch(
        "src.workers.embedding_worker.recover_pending_messages", new=recover_mock
    ), patch("src.workers.embedding_worker.RECOVERY_INTERVAL", 0.02):
        worker = _make_worker()

        task = asyncio.create_task(worker.process_queue())
        started = await _wait_for(lambda: recover_mock.await_count >= 1, timeout=2.0)
        assert started, "worker never reached its first recovery cycle"

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

        # Let the cancelled recovery task settle before inspecting the event loop.
        await asyncio.sleep(0.05)
        current = asyncio.current_task()
        strays = [t for t in asyncio.all_tasks() if t is not current]

    assert strays == [], (
        f"recovery task outlived process_queue shutdown: {strays}"
    )
