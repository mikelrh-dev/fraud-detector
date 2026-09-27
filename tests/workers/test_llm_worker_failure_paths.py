"""Worker failure-path tests — the branches that were never asserted.

Three defects lived entirely in the failure path and were invisible to a green
suite:

* a malformed payload raised ``UnboundLocalError`` *inside* the except handler,
  which ``gather(return_exceptions=True)`` swallowed, so the message got no
  ack, no requeue and no DLQ and looped in the PEL forever;
* a redelivered message hit the new unique constraint and could never drain;
* ``send_to_dlq`` swallowed its own exceptions and returned None, and the
  worker ACKed anyway, so a failed DLQ write lost the work silently.
"""

import json
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.workers import llm_worker


def _entry(payload: dict, message_id: bytes = b"1700000000000-0"):
    return (message_id, {b"data": json.dumps(payload).encode()})


def _redis_mock() -> AsyncMock:
    redis = AsyncMock()
    redis.xack = AsyncMock()
    redis.xadd = AsyncMock()
    return redis


def _audit_patch():
    """Patch AuditService so create_entry is awaitable."""
    audit = MagicMock()
    audit.return_value.create_entry = AsyncMock()
    return patch.object(llm_worker, "AuditService", audit)


class TestMalformedPayloadIsRoutedNotDropped:
    """A bad payload must reach retry/DLQ, never vanish."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "fields",
        [
            {b"data": b"\xff\xfe not utf-8"},
            {b"data": b"{not valid json"},
            {b"data": b"[1, 2, 3]"},  # valid JSON, wrong shape
            {},
        ],
        ids=["bad-utf8", "bad-json", "not-a-dict", "missing-data"],
    )
    async def test_malformed_payload_reaches_the_failure_handler(self, fields: dict):
        """The C4 regression: UnboundLocalError inside the except handler."""
        redis = _redis_mock()
        llm_service = MagicMock()

        with patch.object(
            llm_worker, "_handle_failed_report", new=AsyncMock()
        ) as handler:
            # Must not raise: an escaping exception is what silently dropped
            # the message, because gather(return_exceptions=True) eats it.
            await llm_worker._process_message_safe(
                redis, b"1-0", fields, llm_service
            )

        handler.assert_awaited_once()
        # The payload dict must exist and be safe to serialize.
        _, payload = handler.await_args.args[1:]
        assert isinstance(payload, dict)

    @pytest.mark.asyncio
    async def test_malformed_payload_is_never_acked(self):
        redis = _redis_mock()
        with patch.object(llm_worker, "_handle_failed_report", new=AsyncMock()):
            await llm_worker._process_message_safe(
                redis, b"1-0", {b"data": b"{oops"}, MagicMock()
            )
        redis.xack.assert_not_awaited()


class TestRedeliveryIsIdempotent:
    """A report that already exists must drain, not loop."""

    @pytest.mark.asyncio
    async def test_integrity_error_is_treated_as_success(self):
        """The C9 regression: a redelivered report could never drain."""
        llm_service = AsyncMock()
        llm_service.generate_report = AsyncMock(return_value="Informe")
        llm_service._model = "qwen2.5:0.5b"

        session = AsyncMock()
        session.commit = AsyncMock(
            side_effect=IntegrityError("INSERT", {}, Exception("duplicate key"))
        )
        session.rollback = AsyncMock()

        maker = MagicMock()
        maker.return_value.__aenter__ = AsyncMock(return_value=session)
        maker.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch.object(llm_worker, "async_session_maker", maker), _audit_patch():
            result = await llm_worker.process_report_request(
                {"transaction_id": "t-1"}, AsyncMock(), llm_service
            )

        assert result is True, (
            "a redelivered report must report success so the caller ACKs it"
        )
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_successful_write_does_not_rollback(self):
        llm_service = AsyncMock()
        llm_service.generate_report = AsyncMock(return_value="Informe")
        llm_service._model = "m"

        session = AsyncMock()
        maker = MagicMock()
        maker.return_value.__aenter__ = AsyncMock(return_value=session)
        maker.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch.object(llm_worker, "async_session_maker", maker), _audit_patch():
            assert await llm_worker.process_report_request(
                {"transaction_id": "t-2"}, AsyncMock(), llm_service
            ) is True

        session.rollback.assert_not_awaited()


class TestDlqFailureIsNotSwallowed:
    """A failed DLQ write must leave the message recoverable."""

    @pytest.mark.asyncio
    async def test_send_to_dlq_reports_success(self):
        from src.core.stream_dlq import send_to_dlq

        redis = _redis_mock()
        assert (
            await send_to_dlq(
                redis, "fraud:llm", "1-0", "g", "c", "reason", {"a": 1}
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_send_to_dlq_reports_failure_instead_of_raising(self):
        from src.core.stream_dlq import send_to_dlq

        redis = _redis_mock()
        redis.xadd = AsyncMock(side_effect=RuntimeError("redis down"))

        assert (
            await send_to_dlq(
                redis, "fraud:llm", "1-0", "g", "c", "reason", {"a": 1}
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_worker_does_not_ack_when_dlq_write_fails(self):
        """The A20 regression: ack-after-failed-DLQ lost the work silently."""
        redis = _redis_mock()

        with patch.object(
            llm_worker, "send_to_dlq", new=AsyncMock(return_value=False)
        ):
            await llm_worker._handle_failed_report(
                redis, b"1-0", {"retry_count": 99}
            )

        # send_to_dlq is responsible for the ack; on failure nobody may ack.
        redis.xack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_worker_acks_only_once_on_successful_dlq(self):
        redis = _redis_mock()
        with patch.object(
            llm_worker, "send_to_dlq", new=AsyncMock(return_value=True)
        ) as dlq:
            await llm_worker._handle_failed_report(
                redis, b"1-0", {"retry_count": 99}
            )
        dlq.assert_awaited_once()
        redis.xack.assert_not_awaited()


class TestRecoveryPathIsNotASwallow:
    """The recovery loop must use the same decision tree as the consume loop."""

    @pytest.mark.asyncio
    async def test_recovery_failure_routes_to_dlq(self):
        """Previously the handler was a bare logger.error: no retry, no DLQ."""
        redis = _redis_mock()

        with patch.object(
            llm_worker, "process_report_request", new=AsyncMock(return_value=False)
        ), patch.object(
            llm_worker, "async_session_maker"
        ) as maker, patch.object(
            llm_worker, "_handle_failed_report", new=AsyncMock()
        ) as handler:
            session = AsyncMock()
            maker.return_value.__aenter__ = AsyncMock(return_value=session)
            maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await llm_worker._process_message_with_retry(
                redis, b"1-0", _entry({"transaction_id": "t", "retry_count": 0}), MagicMock()
            )

        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recovery_exception_is_routed_not_swallowed(self):
        redis = _redis_mock()

        with patch.object(
            llm_worker,
            "process_report_request",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ), patch.object(
            llm_worker, "async_session_maker"
        ) as maker, patch.object(
            llm_worker, "_handle_failed_report", new=AsyncMock()
        ) as handler:
            session = AsyncMock()
            maker.return_value.__aenter__ = AsyncMock(return_value=session)
            maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await llm_worker._process_message_with_retry(
                redis, b"1-0", _entry({"transaction_id": "t"}), MagicMock()
            )

        handler.assert_awaited_once()
        redis.xack.assert_not_awaited()


class TestFalseResultIsRetried:
    """success=False must requeue, not sit in the PEL."""

    @pytest.mark.asyncio
    async def test_false_result_calls_the_failure_handler(self):
        redis = _redis_mock()
        with patch.object(
            llm_worker, "process_report_request", new=AsyncMock(return_value=False)
        ), patch.object(
            llm_worker, "async_session_maker"
        ) as maker, patch.object(
            llm_worker, "_handle_failed_report", new=AsyncMock()
        ) as handler:
            session = AsyncMock()
            maker.return_value.__aenter__ = AsyncMock(return_value=session)
            maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await llm_worker._process_message_safe(
                redis, b"1-0", _entry({"transaction_id": "t"}), MagicMock()
            )

        handler.assert_awaited_once()
        redis.xack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_true_result_acks(self):
        redis = _redis_mock()
        with patch.object(
            llm_worker, "process_report_request", new=AsyncMock(return_value=True)
        ), patch.object(
            llm_worker, "async_session_maker"
        ) as maker:
            session = AsyncMock()
            maker.return_value.__aenter__ = AsyncMock(return_value=session)
            maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await llm_worker._process_message_safe(
                redis, b"1-0", _entry({"transaction_id": "t"}), MagicMock()
            )

        redis.xack.assert_awaited_once()


class TestRetryCounterAlwaysIncrements:
    """A message must not be able to loop forever through the retry path."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("retry_count", [0, 1, 2])
    async def test_counter_increments_and_reenqueues(self, retry_count: int):
        redis = _redis_mock()
        payload = {"transaction_id": "t", "retry_count": retry_count}

        with patch.object(llm_worker.asyncio, "sleep", new=AsyncMock()):
            await llm_worker._handle_failed_report(redis, b"1-0", payload)

        assert payload["retry_count"] == retry_count + 1
        redis.xadd.assert_awaited_once()
        redis.xack.assert_awaited_once()
