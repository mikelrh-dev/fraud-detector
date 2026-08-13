"""SHAP worker tests — process a fraud:shap message → persist top-5 rows,
audit trail, retry logic, idempotent re-run, and max retries exhausted.

Mirrors tests/test_llm_worker.py: the worker consumes Redis messages and
persists ShapAttribution rows via a mocked session and a fake explainer.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.audit_entry import AuditEntry
from src.models.shap_attribution import ShapAttribution
from src.services.shap_service import ShapContribution, ShapService, ShapUnavailableError
from src.workers.shap_worker import process_shap_message, run_worker

TXN_ID = "123e4567-e89b-12d3-a456-426614174000"

FEATURE_NAMES = [
    "amount",
    "velocity_1h",
    "velocity_24h",
    "merchant_category",
    "hour_of_day",
    "day_of_week",
    "card_last4",
    "country",
    "channel",
    "device",
]


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


def _five_contributions() -> list[ShapContribution]:
    return [
        ShapContribution(feature="amount", contribution=2.5),
        ShapContribution(feature="velocity_1h", contribution=-1.8),
        ShapContribution(feature="merchant_category", contribution=0.9),
        ShapContribution(feature="hour_of_day", contribution=-0.4),
        ShapContribution(feature="device", contribution=0.2),
    ]


def _audit_entries(mock_db) -> list[AuditEntry]:
    return [
        call[0][0]
        for call in mock_db.add.call_args_list
        if isinstance(call[0][0], AuditEntry)
    ]


class TestProcessShapMessage:
    """Processing a single SHAP message from the queue."""

    @pytest.mark.asyncio
    async def test_success_persists_five_rows_and_audits(self):
        mock_db = AsyncMock()
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.return_value = _five_contributions()

        result = await process_shap_message(_message(), mock_db, mock_service)

        assert result is True
        # Delete-then-insert: existing rows removed first
        stmt = mock_db.execute.await_args.args[0]
        assert "DELETE FROM shap_attributions" in str(stmt)
        # Exactly 5 rows with ranks 1..5, signed values preserved
        rows = mock_db.add_all.call_args[0][0]
        assert len(rows) == 5
        assert [row.rank for row in rows] == [1, 2, 3, 4, 5]
        assert rows[0].feature == "amount"
        assert rows[0].contribution == 2.5
        assert rows[1].contribution == -1.8
        assert all(isinstance(row, ShapAttribution) for row in rows)
        mock_db.flush.assert_awaited()
        # Audit entry for success
        entries = _audit_entries(mock_db)
        assert any(e.action_type == "shap_computed" for e in entries)

    @pytest.mark.asyncio
    async def test_unavailable_skips_without_retry_or_rows(self):
        mock_db = AsyncMock()
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.side_effect = ShapUnavailableError("shap is not installed")

        result = await process_shap_message(_message(), mock_db, mock_service)

        # SHP-005: message done (no re-enqueue), nothing persisted, no audit
        assert result is True
        mock_db.add_all.assert_not_called()
        mock_db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_returns_false_for_retry(self):
        mock_db = AsyncMock()
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.side_effect = RuntimeError("boom")

        result = await process_shap_message(_message(), mock_db, mock_service)

        # Needs re-enqueue (retry_count 0 < max 3)
        assert result is False

    @pytest.mark.asyncio
    async def test_max_retries_audits_failed_with_error_type(self):
        mock_db = AsyncMock()
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.side_effect = RuntimeError("still failing")

        result = await process_shap_message(
            _message(retry_count=3), mock_db, mock_service, max_retries=3
        )

        assert result is True
        failed = [e for e in _audit_entries(mock_db) if e.action_type == "shap_failed"]
        assert len(failed) == 1
        assert failed[0].details["error_type"] == "RuntimeError"
        assert failed[0].details["retry_count"] == 3

    @pytest.mark.asyncio
    async def test_idempotent_rerun_replaces_rows(self):
        mock_db = AsyncMock()
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.return_value = _five_contributions()

        await process_shap_message(_message(), mock_db, mock_service)
        deletes_after_first = mock_db.execute.await_count
        await process_shap_message(_message(), mock_db, mock_service)

        # Each run issues the delete + insert path → rows are replaced, not appended
        assert mock_db.execute.await_count == deletes_after_first + 1
        assert mock_db.add_all.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_features_handled_gracefully(self):
        """A message without features must not crash the caller."""
        mock_db = AsyncMock()
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.side_effect = RuntimeError("no features")

        result = await process_shap_message(
            _message(features=[]), mock_db, mock_service
        )

        assert result is False


class TestRunWorker:
    """Worker loop — consuming SHAP messages from Redis."""

    @pytest.mark.asyncio
    async def test_worker_processes_one_message(self):
        mock_redis = AsyncMock()
        mock_redis.brpop = AsyncMock(
            side_effect=[
                ("fraud:shap", json.dumps(_message())),
                None,
            ]
        )
        mock_db = AsyncMock()
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.return_value = _five_contributions()

        with patch("src.workers.shap_worker.async_session_maker") as mock_session_maker:
            mock_session_maker.return_value = mock_db
            await run_worker(
                redis_client=mock_redis,
                shap_service=mock_service,
                max_iterations=1,
            )

        mock_redis.brpop.assert_called()
        mock_db.add_all.assert_called_once()
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_worker_handles_empty_queue(self):
        mock_redis = AsyncMock()
        mock_redis.brpop = AsyncMock(return_value=None)

        with patch("src.workers.shap_worker.async_session_maker") as mock_session_maker:
            mock_session_maker.return_value = AsyncMock()
            await run_worker(
                redis_client=mock_redis,
                shap_service=MagicMock(spec=ShapService),
                max_iterations=1,
            )

        mock_redis.brpop.assert_called_once()

    @pytest.mark.asyncio
    async def test_worker_handles_malformed_json(self):
        mock_redis = AsyncMock()
        mock_redis.brpop = AsyncMock(
            side_effect=[
                ("fraud:shap", "this is not valid json"),
                None,
            ]
        )

        with patch("src.workers.shap_worker.async_session_maker") as mock_session_maker:
            mock_session_maker.return_value = AsyncMock()
            await run_worker(
                redis_client=mock_redis,
                shap_service=MagicMock(spec=ShapService),
                max_iterations=1,
            )

        # Worker should not crash on malformed payloads
        mock_redis.brpop.assert_called()

    @pytest.mark.asyncio
    async def test_worker_reenqueues_with_incremented_retry(self):
        mock_redis = AsyncMock()
        mock_redis.brpop = AsyncMock(
            side_effect=[
                ("fraud:shap", json.dumps(_message(retry_count=0))),
                None,
            ]
        )
        mock_db = AsyncMock()
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.side_effect = RuntimeError("boom")

        with patch("src.workers.shap_worker.async_session_maker") as mock_session_maker:
            mock_session_maker.return_value = mock_db
            await run_worker(
                redis_client=mock_redis,
                shap_service=mock_service,
                max_iterations=1,
            )

        mock_redis.lpush.assert_awaited_once()
        queue_name, payload = mock_redis.lpush.await_args.args
        assert queue_name == "fraud:shap"
        assert json.loads(payload)["retry_count"] == 1
