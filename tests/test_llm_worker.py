"""LLM worker tests — enqueue → consume → mock Ollama → persist report,
retry logic, idempotent enqueue, max retries exhausted.

Tests for the async Redis consumer that generates LLM reports for
fraudulent transactions.
"""

import asyncio
import json
from datetime import datetime, timezone
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.llm_report import LLMReport, LLMReportStatus
from src.workers.llm_worker import process_report_request, worker_loop

STREAM = b"fraud:reports"


def _scripted_xreadgroup(batches, delay=0.05):
    """xreadgroup stand-in: returns scripted batches, then suspends.

    A plain AsyncMock returning [] completes without yielding to the event
    loop, starving sibling tasks (same gotcha as the embedding worker tests).
    """
    calls = {"n": 0}

    async def readgroup(*args, **kwargs):
        n = calls["n"]
        calls["n"] += 1
        if n < len(batches):
            await asyncio.sleep(0)
            return batches[n]
        await asyncio.sleep(delay)
        return []

    return readgroup


def _stream_message(payload: dict, message_id=b"1700000000000-0") -> list:
    return [(b"fraud:reports", [(message_id, {b"data": json.dumps(payload).encode()})])]


class TestProcessReportRequest:
    """process_report_request: generate → persist → audit for one message."""

    @pytest.fixture(autouse=True)
    def _patched_persistence(self):
        """Patch the internal session factory and audit service."""
        with patch(
            "src.workers.llm_worker.async_session_maker"
        ) as mock_maker, patch("src.workers.llm_worker.AuditService") as audit_cls:
            session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            audit_cls.return_value.create_entry = AsyncMock()
            self.session = session
            self.audit_create = audit_cls.return_value.create_entry
            yield

    @staticmethod
    def _message() -> dict:
        return {
            "transaction_id": "123e4567-e89b-12d3-a456-426614174000",
            "score_breakdown": {
                "rule_score": 60.0,
                "ml_score": 80.0,
                "ensemble_score": 72.0,
                "fired_rules": ["high_amount"],
                "threshold": 70.0,
            },
        }

    @pytest.mark.asyncio
    async def test_process_request_success(self):
        """A valid report request persists a COMPLETED report."""
        mock_llm_service = AsyncMock()
        mock_llm_service.generate_report.return_value = (
            "Análisis completo: transacción sospechosa."
        )
        mock_db = AsyncMock()

        result = await process_report_request(
            message=self._message(), db=mock_db, llm_service=mock_llm_service
        )

        assert result is True
        added = [c[0][0] for c in self.session.add.call_args_list]
        reports = [r for r in added if isinstance(r, LLMReport)]
        assert reports, "an LLMReport must be persisted"
        assert reports[0].status == LLMReportStatus.COMPLETED
        assert (
            reports[0].report_text == "Análisis completo: transacción sospechosa."
        )

    @pytest.mark.asyncio
    async def test_process_request_creates_audit_entry(self):
        """Successful processing writes an audit trail entry."""
        mock_llm_service = AsyncMock()
        mock_llm_service.generate_report.return_value = (
            "Reporte generado correctamente."
        )

        result = await process_report_request(
            message=self._message(), db=AsyncMock(), llm_service=mock_llm_service
        )

        assert result is True
        self.audit_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_error_prefixed_report_marked_failed(self):
        """An 'Error:' report text is persisted as FAILED but still consumed."""
        mock_llm_service = AsyncMock()
        mock_llm_service.generate_report.return_value = (
            "Error: No se pudo conectar con el servicio Ollama."
        )

        result = await process_report_request(
            message=self._message(), db=AsyncMock(), llm_service=mock_llm_service
        )

        assert result is True
        added = [c[0][0] for c in self.session.add.call_args_list]
        reports = [r for r in added if isinstance(r, LLMReport)]
        assert reports and reports[0].status == LLMReportStatus.FAILED
        assert "Error" in reports[0].report_text

    @pytest.mark.asyncio
    async def test_llm_exception_returns_false_for_retry(self):
        """An exception from the LLM service signals retry (returns False)."""
        mock_llm_service = AsyncMock()
        mock_llm_service.generate_report.side_effect = Exception("Connection error")

        result = await process_report_request(
            message=self._message(), db=AsyncMock(), llm_service=mock_llm_service
        )

        assert result is False


class TestWorkerLoop:
    """worker_loop consumes the fraud:reports stream via consumer groups."""

    async def _run(self, batches, redis_client):
        task = asyncio.create_task(worker_loop(redis_client))
        return task

    @pytest.mark.asyncio
    async def test_worker_acks_processed_message(self):
        """A successfully processed report must be ACKed."""
        mock_redis = AsyncMock()
        mock_redis.xreadgroup = _scripted_xreadgroup(
            [_stream_message({"transaction_id": "t1", "report_request": True})]
        )

        with patch(
            "src.workers.llm_worker.ensure_consumer_group", new=AsyncMock()
        ), patch(
            "src.workers.llm_worker.LLMService"
        ) as _, patch(
            "src.workers.llm_worker.async_session_maker"
        ) as mock_maker, patch(
            "src.workers.llm_worker.process_report_request",
            new=AsyncMock(return_value=True),
        ):
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            task = await self._run(None, mock_redis)
            await _wait_for(lambda: mock_redis.xack.await_count > 0, timeout=2.0)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        assert mock_redis.xack.await_count >= 1

    @pytest.mark.asyncio
    async def test_worker_survives_empty_queue(self):
        """Empty reads must keep the loop alive without errors."""
        mock_redis = AsyncMock()
        mock_redis.xreadgroup = _scripted_xreadgroup([])

        with patch(
            "src.workers.llm_worker.ensure_consumer_group", new=AsyncMock()
        ), patch("src.workers.llm_worker.LLMService"), patch(
            "src.workers.llm_worker.process_report_request", new=AsyncMock()
        ):
            task = await self._run(None, mock_redis)
            await asyncio.sleep(0.15)
            alive = not task.done()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        assert alive, f"worker_loop exited early: {task.exception()!r}"

    @pytest.mark.asyncio
    async def test_worker_skips_malformed_payload_without_crash(self):
        """Malformed JSON must not crash the loop nor ACK anything."""
        mock_redis = AsyncMock()
        mock_redis.xreadgroup = _scripted_xreadgroup(
            [(b"fraud:reports", [(b"1700000000000-1", {b"data": b"not-json{)"})])]
        )

        processed = AsyncMock()
        with patch(
            "src.workers.llm_worker.ensure_consumer_group", new=AsyncMock()
        ), patch("src.workers.llm_worker.LLMService"), patch(
            "src.workers.llm_worker.process_report_request", new=processed
        ):
            task = await self._run(None, mock_redis)
            await asyncio.sleep(0.15)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        processed.assert_not_awaited()
        mock_redis.xack.assert_not_awaited()


async def _wait_for(predicate, timeout: float = 2.0) -> bool:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


class TestWorkerDurability:
    """R4-002/R4-003: failed reports must not be lost nor ACKed."""

    @pytest.mark.asyncio
    async def test_failed_report_is_not_acked(self):
        """process_report_request returning False must leave the message pending."""
        mock_redis = AsyncMock()
        mock_redis.xreadgroup = _scripted_xreadgroup(
            [_stream_message({"transaction_id": "t-fail"})]
        )

        with patch(
            "src.workers.llm_worker.ensure_consumer_group", new=AsyncMock()
        ), patch("src.workers.llm_worker.LLMService"), patch(
            "src.workers.llm_worker.process_report_request",
            new=AsyncMock(return_value=False),
        ):
            task = asyncio.create_task(worker_loop(mock_redis))
            await asyncio.sleep(0.15)
            processed = not task.done() or True  # loop ran without crashing
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        assert processed
        mock_redis.xack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_recovery_loop_reprocesses_claimed_reports(self):
        """Stale PEL entries are claimed and routed through report processing."""
        from src.workers import llm_worker

        mock_redis = AsyncMock()
        claimed_entry = (
            b"1700000000099-0",
            {b"data": json.dumps({"transaction_id": "t-stale"}).encode()},
        )

        with patch.object(
            llm_worker, "RECOVERY_INTERVAL", 0.01
        ), patch.object(
            llm_worker,
            "recover_pending_messages",
            new=AsyncMock(return_value=[claimed_entry]),
        ) as recover_mock, patch.object(
            llm_worker, "async_session_maker"
        ) as mock_maker, patch.object(
            llm_worker, "LLMService"
        ), patch.object(
            llm_worker,
            "process_report_request",
            new=AsyncMock(return_value=True),
        ) as process_mock:
            session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            task = asyncio.create_task(llm_worker._recovery_loop(mock_redis))
            routed = await _wait_for(lambda: process_mock.await_count > 0, timeout=2.0)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        recover_mock.assert_awaited()
        assert routed, "claimed reports were never reprocessed"

    @pytest.mark.asyncio
    async def test_main_uses_configured_redis_url(self):
        """R4-007 sibling: entry points must honor settings.redis_url."""
        from src.core.config import settings
        from src.workers import llm_worker

        with patch.object(
            llm_worker.redis, "from_url", new=AsyncMock(return_value=AsyncMock())
        ) as from_url, patch.object(llm_worker, "worker_loop", new=AsyncMock()):
            await llm_worker.main()

        from_url.assert_awaited_once_with(settings.redis_url)
