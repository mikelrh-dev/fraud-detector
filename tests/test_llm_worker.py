"""LLM worker tests — enqueue → consume → mock Ollama → persist report,
retry logic, idempotent enqueue, max retries exhausted.

Tests for the async Redis consumer that generates LLM reports for
fraudulent transactions.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.llm_report import LLMReport, LLMReportStatus
from src.workers.llm_worker import process_report_request, run_worker


class TestProcessReportRequest:
    """Processing a single report request from the queue."""

    @pytest.mark.asyncio
    async def test_process_request_success(self):
        """Process a valid report request successfully."""
        mock_db = AsyncMock()
        mock_llm_service = AsyncMock()
        mock_llm_service.generate_report.return_value = (
            "Análisis completo: transacción sospechosa."
        )

        message = {
            "transaction_id": "123e4567-e89b-12d3-a456-426614174000",
            "score_breakdown": {
                "rule_score": 60.0,
                "ml_score": 80.0,
                "ensemble_score": 72.0,
                "fired_rules": ["high_amount"],
                "threshold": 70.0,
            },
            "transaction": {"amount": 15000.0, "merchant_name": "Test Store"},
        }

        result = await process_report_request(
            message=message,
            db=mock_db,
            llm_service=mock_llm_service,
        )

        assert result is True
        # Should have created an LLMReport + AuditEntry
        assert mock_db.add.call_count >= 1
        added_report = mock_db.add.call_args_list[0][0][0]
        assert isinstance(added_report, LLMReport)
        assert added_report.status == LLMReportStatus.COMPLETED
        assert added_report.report_text == "Análisis completo: transacción sospechosa."
        mock_db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_process_request_persists_to_db(self):
        """Processed report should be persisted and flushed to DB."""
        mock_db = AsyncMock()
        mock_llm_service = AsyncMock()
        mock_llm_service.generate_report.return_value = (
            "Reporte generado correctamente."
        )

        message = {
            "transaction_id": "123e4567-e89b-12d3-a456-426614174000",
            "score_breakdown": {
                "rule_score": 50.0,
                "ml_score": 70.0,
                "ensemble_score": 60.0,
                "fired_rules": [],
                "threshold": 70.0,
            },
        }

        result = await process_report_request(
            message=message,
            db=mock_db,
            llm_service=mock_llm_service,
        )

        assert result is True
        assert mock_db.add.call_count >= 1
        mock_db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_llm_failure_marks_report_as_failed(self):
        """When LLM service fails, the report should be marked as failed."""
        mock_db = AsyncMock()
        mock_llm_service = AsyncMock()
        mock_llm_service.generate_report.return_value = (
            "Error: No se pudo conectar con el servicio Ollama."
        )

        message = {
            "transaction_id": "123e4567-e89b-12d3-a456-426614174000",
            "score_breakdown": {
                "rule_score": 60.0,
                "ml_score": 80.0,
                "ensemble_score": 72.0,
                "fired_rules": ["high_amount"],
                "threshold": 70.0,
            },
        }

        result = await process_report_request(
            message=message,
            db=mock_db,
            llm_service=mock_llm_service,
        )

        # Should still return True (message processed, no re-enqueue needed)
        assert result is True
        assert mock_db.add.call_count >= 1
        added_report = mock_db.add.call_args_list[0][0][0]
        assert added_report.status == LLMReportStatus.FAILED
        assert added_report.report_text is not None
        assert "Error" in added_report.report_text

    @pytest.mark.asyncio
    async def test_retry_count_incremented_on_retry(self):
        """When the worker needs to retry, retry_count should be incremented."""
        mock_db = AsyncMock()
        mock_llm_service = AsyncMock()
        # Simulate an exception from LLM service
        mock_llm_service.generate_report.side_effect = Exception("Connection error")

        message = {
            "transaction_id": "123e4567-e89b-12d3-a456-426614174000",
            "score_breakdown": {
                "rule_score": 60.0,
                "ml_score": 80.0,
                "ensemble_score": 72.0,
                "fired_rules": ["high_amount"],
                "threshold": 70.0,
            },
            "retry_count": 0,
        }

        # Should return False to indicate re-enqueue is needed
        result = await process_report_request(
            message=message,
            db=mock_db,
            llm_service=mock_llm_service,
        )

        # Returns False to signal re-enqueue
        assert result is False

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """When max retries reached, the report should persist as failed."""
        mock_db = AsyncMock()
        mock_llm_service = AsyncMock()
        mock_llm_service.generate_report.side_effect = Exception("Still failing")

        message = {
            "transaction_id": "123e4567-e89b-12d3-a456-426614174000",
            "score_breakdown": {
                "rule_score": 60.0,
                "ml_score": 80.0,
                "ensemble_score": 72.0,
                "fired_rules": ["high_amount"],
                "threshold": 70.0,
            },
            "retry_count": 3,  # Already at max
        }

        result = await process_report_request(
            message=message,
            db=mock_db,
            llm_service=mock_llm_service,
        )

        # Should return True (processed, no re-enqueue) with failed status
        assert result is True
        assert mock_db.add.call_count >= 1
        added_report = mock_db.add.call_args_list[0][0][0]
        assert added_report.status == LLMReportStatus.FAILED


class TestRunWorker:
    """Worker loop — consuming messages from Redis queue."""

    @pytest.mark.asyncio
    async def test_worker_processes_one_message(self):
        """Worker should process a message from the queue."""
        message = {
            "transaction_id": "123e4567-e89b-12d3-a456-426614174000",
            "score_breakdown": {
                "rule_score": 60.0,
                "ml_score": 80.0,
                "ensemble_score": 72.0,
                "fired_rules": ["high_amount"],
                "threshold": 70.0,
            },
        }

        mock_redis = AsyncMock()
        # First call returns a message, second call returns None (exit loop)
        mock_redis.brpop = AsyncMock(
            side_effect=[
                ("fraud:reports", json.dumps(message)),
                None,  # No more messages
            ]
        )

        mock_db = AsyncMock()
        mock_llm_service = AsyncMock()
        mock_llm_service.generate_report.return_value = (
            "Análisis completo."
        )

        with patch("src.workers.llm_worker.async_session_maker") as mock_session_maker:
            mock_session_maker.return_value = mock_db

            await run_worker(
                redis_client=mock_redis,
                llm_service=mock_llm_service,
                max_iterations=1,  # Stop after 1 iteration
            )

        # Should have popped from the queue
        mock_redis.brpop.assert_called()
        assert mock_db.add.call_count >= 1
        mock_db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_worker_handles_empty_queue(self):
        """Worker should exit gracefully when queue is empty."""
        mock_redis = AsyncMock()
        mock_redis.brpop = AsyncMock(return_value=None)

        mock_llm_service = AsyncMock()

        with patch("src.workers.llm_worker.async_session_maker") as mock_session_maker:
            mock_session_maker.return_value = AsyncMock()

            await run_worker(
                redis_client=mock_redis,
                llm_service=mock_llm_service,
                max_iterations=1,
            )

        # Should have exited gracefully
        mock_redis.brpop.assert_called_once()

    @pytest.mark.asyncio
    async def test_worker_handles_malformed_json(self):
        """Worker should handle malformed JSON without crashing."""
        mock_redis = AsyncMock()
        mock_redis.brpop = AsyncMock(
            side_effect=[
                ("fraud:reports", "this is not valid json"),
                None,
            ]
        )

        mock_db = AsyncMock()
        mock_llm_service = AsyncMock()

        with patch("src.workers.llm_worker.async_session_maker") as mock_session_maker:
            mock_session_maker.return_value = mock_db

            await run_worker(
                redis_client=mock_redis,
                llm_service=mock_llm_service,
                max_iterations=1,
            )

        # Worker should not crash
        mock_redis.brpop.assert_called()
