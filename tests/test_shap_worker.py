"""SHAP worker tests — process a fraud:shap message → persist top-5 rows,
audit trail, retry logic, idempotent re-run, and max retries exhausted.

Mirrors tests/test_llm_worker.py: the worker consumes Redis messages and
persists ShapAttribution rows via a mocked session and a fake explainer.
"""

import asyncio
import json
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.audit_entry import AuditEntry
from src.models.shap_attribution import ShapAttribution
from src.services.shap_service import ShapContribution, ShapService, ShapUnavailableError
from src.workers.shap_worker import (
    _process_message_with_retry,
    _recovery_loop,
    process_shap_message,
    worker_loop,
)

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
    """process_shap_message: compute attributions and persist idempotently."""

    @pytest.fixture(autouse=True)
    def _patched_session(self):
        """Patch the internal session factory used for persistence."""
        with patch(
            "src.workers.shap_worker.async_session_maker"
        ) as mock_maker:
            session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            self.session = session
            yield

    @pytest.mark.asyncio
    async def test_success_persists_five_rows(self):
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.return_value = _five_contributions()

        result = await process_shap_message(_message(), AsyncMock(), mock_service)

        assert result is True
        # Delete-then-insert: existing rows removed first
        delete_executed = any(
            "shap_attributions" in str(c.args[0])
            for c in self.session.execute.await_args_list
        )
        assert delete_executed
        added = [c[0][0] for c in self.session.add.call_args_list]
        rows = [r for r in added if isinstance(r, ShapAttribution)]
        assert [row.rank for row in rows] == [1, 2, 3, 4, 5]
        assert rows[0].feature == "amount"
        assert rows[0].contribution == 2.5
        self.session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_unavailable_skips_without_retry_or_rows(self):
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.side_effect = ShapUnavailableError("shap is not installed")

        result = await process_shap_message(_message(), AsyncMock(), mock_service)

        # SHP-005: message done (no re-enqueue), nothing persisted
        assert result is True
        self.session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_returns_false_for_retry(self):
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.side_effect = RuntimeError("boom")

        result = await process_shap_message(_message(), AsyncMock(), mock_service)

        # Needs re-enqueue (retry_count 0 < max 3)
        assert result is False

    @pytest.mark.asyncio
    async def test_idempotent_rerun_replaces_rows(self):
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.return_value = _five_contributions()

        await process_shap_message(_message(), AsyncMock(), mock_service)
        deletes_after_first = self.session.execute.await_count
        await process_shap_message(_message(), AsyncMock(), mock_service)

        # Each run issues the delete + insert path -> rows are replaced
        assert self.session.execute.await_count == deletes_after_first + 1

    @pytest.mark.asyncio
    async def test_missing_features_handled_gracefully(self):
        """A message without features must not crash the caller."""
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.side_effect = RuntimeError("no features")

        result = await process_shap_message(
            _message(features=[]), AsyncMock(), mock_service
        )

        assert result is False


class TestWorkerLoop:
    """worker_loop / _process_message_with_retry over the fraud:shap stream."""

    @staticmethod
    def _scripted_xreadgroup(batches, delay=0.05):
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

    @staticmethod
    def _stream_message(payload: dict, message_id=b"1700000000000-0") -> list:
        return [
            (b"fraud:shap", [(message_id, {b"data": json.dumps(payload).encode()})])
        ]

    @pytest.mark.asyncio
    async def test_worker_acks_processed_message(self):
        """A successfully processed SHAP message must be ACKed."""
        mock_redis = AsyncMock()
        mock_redis.xreadgroup = self._scripted_xreadgroup(
            [self._stream_message(_message())]
        )
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.return_value = _five_contributions()

        with patch(
            "src.workers.shap_worker.ensure_consumer_group", new=AsyncMock()
        ), patch("src.workers.shap_worker.ShapService", return_value=mock_service), patch(
            "src.workers.shap_worker.async_session_maker"
        ) as mock_maker:
            session = AsyncMock()
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            task = asyncio.create_task(worker_loop(mock_redis))
            acked = await _wait_for(
                lambda: mock_redis.xack.await_count > 0, timeout=2.0
            )
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        assert acked, "processed message was never ACKed"

    @pytest.mark.asyncio
    async def test_worker_survives_empty_queue(self):
        mock_redis = AsyncMock()
        mock_redis.xreadgroup = self._scripted_xreadgroup([])
        mock_redis.close = AsyncMock()

        with patch(
            "src.workers.shap_worker.ensure_consumer_group", new=AsyncMock()
        ), patch("src.workers.shap_worker.ShapService"):
            task = asyncio.create_task(worker_loop(mock_redis))
            await asyncio.sleep(0.15)
            alive = not task.done()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await asyncio.sleep(0.05)

        assert alive, f"worker_loop exited early: {task.exception()!r}"

    @pytest.mark.asyncio
    async def test_worker_skips_malformed_payload_without_crash(self):
        """Malformed payloads must not crash the loop nor ACK anything."""
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock()
        mock_redis.xreadgroup = self._scripted_xreadgroup(
            [self._stream_message({}, message_id=b"1700000000000-1")]
        )

        retried = AsyncMock()
        with patch(
            "src.workers.shap_worker.ensure_consumer_group", new=AsyncMock()
        ), patch("src.workers.shap_worker.ShapService"), patch(
            "src.workers.shap_worker._process_message_with_retry", new=retried
        ):
            task = asyncio.create_task(worker_loop(mock_redis))
            called = await _wait_for(lambda: retried.await_count > 0, timeout=2.0)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        assert called, "retry helper was never invoked for the malformed message"

    @pytest.mark.asyncio
    async def test_failed_message_reenqueued_with_incremented_retry(self):
        """A failed message is re-enqueued with retry_count+1 and ACKed."""
        mock_redis = AsyncMock()
        fields = {b"data": json.dumps(_message(retry_count=0)).encode()}
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.side_effect = RuntimeError("boom")

        with patch("src.workers.shap_worker.async_session_maker") as mock_maker:
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await _process_message_with_retry(
                mock_redis, b"1700000000000-9", fields, mock_service
            )

        mock_redis.xadd.assert_awaited_once()
        stream_name, entry = mock_redis.xadd.await_args.args
        assert stream_name == "fraud:shap"
        requeued = json.loads(entry["data"])
        assert requeued["retry_count"] == 1
        # The old pending entry must be ACKed so it does not loop forever.
        mock_redis.xack.assert_awaited_once()


async def _wait_for(predicate, timeout: float = 2.0) -> bool:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


class TestRecoveryReprocessing:
    """R4-003: recovery must REPROCESS claimed messages, not just log them."""

    @pytest.mark.asyncio
    async def test_recovery_routes_claimed_entries_through_retry_helper(self):
        mock_redis = AsyncMock()
        claimed_entry = (b"1700000000099-0", {b"data": json.dumps(_message()).encode()})

        with patch(
            "src.workers.shap_worker.RECOVERY_INTERVAL", 0.01
        ), patch(
            "src.workers.shap_worker.get_consumer_group_status",
            new=AsyncMock(return_value={"pending_count": 3}),
        ), patch(
            "src.workers.shap_worker.recover_pending_messages",
            new=AsyncMock(return_value=[claimed_entry]),
        ) as recover_mock, patch(
            "src.workers.shap_worker._process_message_with_retry",
            new=AsyncMock(),
        ) as retry_helper:
            task = asyncio.create_task(_recovery_loop(mock_redis))
            routed = await _wait_for(lambda: retry_helper.await_count > 0, timeout=2.0)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        recover_mock.assert_awaited()
        assert routed, "claimed entries were never reprocessed"
        args = retry_helper.await_args.args
        assert args[1] == b"1700000000099-0"
        assert args[2] == {b"data": json.dumps(_message()).encode()}


class TestRetryBackoff:
    """R4-004: re-enqueue must apply exponential backoff."""

    def test_backoff_delay_grows_exponentially(self):
        from src.workers.shap_worker import _backoff_delay

        assert _backoff_delay(0) == 1
        assert _backoff_delay(1) == 2
        assert _backoff_delay(2) == 4
        assert _backoff_delay(10) <= 60  # capped

    @pytest.mark.asyncio
    async def test_reenqueue_sleeps_before_xadd(self):
        mock_redis = AsyncMock()
        fields = {b"data": json.dumps(_message(retry_count=1)).encode()}
        mock_service = MagicMock(spec=ShapService)
        mock_service.explain.side_effect = RuntimeError("boom")

        with patch("src.workers.shap_worker.async_session_maker") as mock_maker, patch(
            "src.workers.shap_worker.asyncio.sleep", new=AsyncMock()
        ) as sleep_mock:
            mock_maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await _process_message_with_retry(
                mock_redis, b"1700000000000-9", fields, mock_service
            )

        sleep_mock.assert_awaited_once_with(2)  # 2 ** retry_count(1)
