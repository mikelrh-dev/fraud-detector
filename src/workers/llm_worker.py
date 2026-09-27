"""LLM Worker — Asynchronous fraud report generation with Redis Streams.

Consumes fraud report requests from Redis Streams (fraud:llm) and generates
reports via Ollama.

Consumer group: "llm-workers"
Stream: "fraud:llm"
"""

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis
from sqlalchemy.exc import IntegrityError

from src.core.config import settings
from src.core.database import async_session_maker
from src.core.stream_dlq import (
    get_consumer_group_status,
    recover_pending_messages,
    send_to_dlq,
)
from src.core.stream_publisher import ensure_consumer_group
from src.models.llm_report import LLMReport, LLMReportStatus
from src.services.audit import AuditService
from src.services.llm import LLMService

logger = logging.getLogger(__name__)

STREAM_NAME = "fraud:llm"
GROUP_NAME = "llm-workers"
CONSUMER_NAME = "llm-worker-1"
MAX_RETRIES = 3  # total retries before DLQ (actual attempts = MAX_RETRIES + 1: original + retries)
RECOVERY_INTERVAL = 60
BACKOFF_CAP_SECONDS = 60
# Backlog thresholds for the recovery-loop lag monitor (C14).
STREAM_BACKLOG_THRESHOLD = 50000
PENDING_BACKLOG_THRESHOLD = 100


def _backoff_delay(retry_count: int) -> int:
    """Exponential backoff before re-enqueueing a failed report."""
    return min(2**retry_count, BACKOFF_CAP_SECONDS)


async def process_report_request(
    message: dict[str, Any],
    db: Any,
    llm_service: LLMService,
) -> bool:
    """Process a single report request from the stream.

    Returns:
        True if processed successfully.
    Raises:
        Exception: On any failure (LLM error, DB error). The caller is
            responsible for retry/DLQ handling.
    """
    transaction_id = message.get("transaction_id", "unknown")
    score_breakdown = message.get("score_breakdown", {})
    transaction = message.get("transaction", {})

    report_text = await llm_service.generate_report(
        transaction_id=transaction_id,
        score_breakdown=score_breakdown,
        transaction=transaction,
    )

    # Persist report.
    #
    # The write must be idempotent. A redelivered message (lost XACK, worker
    # restart, XAUTOCLAIM after the commit landed) raises IntegrityError against
    # uq_llm_reports_transaction_id, which the caller routed into its retry path
    # — so a report that already existed could never drain and the PEL entry
    # looped forever. Handling the conflict here keeps the code dialect-agnostic
    # (an INSERT .. ON CONFLICT would be PostgreSQL-only) and is equally final.
    report = LLMReport(
        transaction_id=transaction_id,
        report_text=report_text,
        model_name=llm_service._model,
        status=LLMReportStatus.COMPLETED,
        generation_time_ms=None,
        retry_count=0,
    )

    async with async_session_maker() as session:
        session.add(report)

        # Audit entry
        audit = AuditService()
        await audit.create_entry(
            db=session,
            action_type="report_generated",
            transaction_id=transaction_id,
            details={
                "model": llm_service._model,
                "status": LLMReportStatus.COMPLETED.value,
            },
        )

        try:
            await session.commit()
        except IntegrityError:
            # The report is already there: the desired end state is reached.
            # Roll back the audit insert too, so a redelivery does not
            # duplicate the audit trail, and report success.
            await session.rollback()
            logger.info(
                "LLM report for transaction %s already exists — treating "
                "redelivery as success",
                transaction_id,
            )
            return True

    logger.info(
        "LLM report generated for transaction %s",
        transaction_id,
    )
    return True


async def worker_loop(redis_client: redis.Redis) -> None:
    """Main worker loop — consume from stream with consumer group."""
    await ensure_consumer_group(STREAM_NAME, GROUP_NAME)
    llm_service = LLMService()

    logger.info("LLM worker started: stream=%s, group=%s", STREAM_NAME, GROUP_NAME)

    recovery_task = asyncio.create_task(_recovery_loop(redis_client))

    try:
        await _consume_loop(redis_client, llm_service)
    finally:
        recovery_task.cancel()


async def _consume_loop(redis_client: redis.Redis, llm_service: LLMService) -> None:
    """Consume new messages from the stream until cancelled."""
    while True:
        try:
            # XREADGROUP: blocking read from consumer group
            # count=10 for concurrency: process multiple messages in parallel
            messages = await redis_client.xreadgroup(
                GROUP_NAME,
                CONSUMER_NAME,
                {STREAM_NAME: ">"},  # ">" means new messages only
                count=10,
                block=1000,  # 1 second timeout
            )

            if not messages:
                continue

            # Process each message concurrently with bounded parallelism
            tasks = []
            for stream_name, msg_list in messages:
                for message_id, fields in msg_list:
                    tasks.append(
                        _process_message_safe(redis_client, message_id, fields, llm_service)
                    )

            # Wait for all messages in this batch to complete
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as exc:
            logger.error("Error in LLM worker loop: %s", exc)
            await asyncio.sleep(1)  # Backoff


async def _process_message_safe(
    redis_client: redis.Redis,
    message_id: bytes | str,
    fields: dict,
    llm_service: LLMService,
) -> None:
    """Process a message with full error handling and DLQ routing.

    Any exception during processing is caught and routed to retry/DLQ.
    This prevents poison-pill infinite loops.
    """
    # Bound BEFORE the try: the except handler needs it, and a malformed payload
    # (bad utf-8, invalid JSON) used to raise UnboundLocalError *inside* the
    # handler. asyncio.gather(return_exceptions=True) swallowed that, so the
    # message got no ack, no requeue and no DLQ — it sat in the PEL and was
    # re-claimed by XAUTOCLAIM every 60s forever.
    message_data: dict[str, Any] = {}
    try:
        data_json = fields.get(b"data", b"{}").decode("utf-8")
        parsed = json.loads(data_json)
        if isinstance(parsed, dict):
            message_data = parsed
        else:
            message_data = {"_raw": parsed}

        # Process
        async with async_session_maker() as db:
            success = await process_report_request(
                message_data,
                db,
                llm_service,
            )

        # ACK on success
        if success:
            await redis_client.xack(STREAM_NAME, GROUP_NAME, message_id)
            logger.debug("LLM message ACKed: %s", message_id)
        else:
            # The processor reported "not done, retryable". Without this the
            # entry was neither acked nor requeued, so it only moved again when
            # XAUTOCLAIM happened to reclaim it.
            await _handle_failed_report(redis_client, message_id, message_data)

    except Exception as exc:
        logger.error("Error processing LLM message %s: %s", message_id, exc)
        # Route to retry/DLQ instead of leaving in PEL forever
        await _handle_failed_report(redis_client, message_id, message_data)


async def main() -> None:
    """Entry point."""
    redis_client = await redis.from_url(settings.redis_url)

    try:
        await worker_loop(redis_client)
    except KeyboardInterrupt:
        logger.info("LLM worker stopped by user")
    finally:
        await redis_client.close()


async def _handle_failed_report(
    redis_client: redis.Redis,
    message_id,
    message_data: dict,
) -> None:
    """Retry with backoff, or DLQ once retries are exhausted (R4-002)."""
    retry_count = message_data.get("retry_count", 0)

    if retry_count >= MAX_RETRIES:
        dlq_message_id = (
            message_id.decode("utf-8")
            if isinstance(message_id, bytes)
            else str(message_id)
        )
        # send_to_dlq already ACKs the original entry. It returns False when the
        # DLQ write failed, in which case the entry must stay in the PEL so the
        # recovery loop tries again — ACKing here anyway (as the code did) is how
        # work disappeared with no record in the DLQ.
        delivered = await send_to_dlq(
            redis_client,
            STREAM_NAME,
            dlq_message_id,
            GROUP_NAME,
            CONSUMER_NAME,
            f"Max retries ({MAX_RETRIES}) exceeded",
            message_data,
        )
        if delivered:
            logger.warning(
                "LLM message sent to DLQ: %s (retries: %d)", message_id, retry_count
            )
        else:
            logger.error(
                "LLM message %s could not be written to the DLQ — left pending "
                "for recovery",
                message_id,
            )
        return

    message_data["retry_count"] = retry_count + 1
    await asyncio.sleep(_backoff_delay(retry_count))
    await redis_client.xadd(
        STREAM_NAME,
        {"data": json.dumps(message_data)},
        maxlen=100000,
        approximate=True,
    )
    await redis_client.xack(STREAM_NAME, GROUP_NAME, message_id)
    logger.info(
        "LLM message re-queued for retry: %s (attempt %d/%d)",
        message_id,
        retry_count + 1,
        MAX_RETRIES,
    )


async def _recovery_loop(redis_client: redis.Redis) -> None:
    """Claim stale PEL entries and reprocess them (R4-003).

    Claimed messages are routed through _process_message_with_retry so that
    permanently-failing messages reach the DLQ instead of looping forever (R3).
    Also monitors consumer lag and alerts when the stream is backing up.
    """
    llm_service = LLMService()

    while True:
        try:
            await asyncio.sleep(RECOVERY_INTERVAL)

            # Monitor consumer lag
            try:
                stream_len = await redis_client.xlen(STREAM_NAME)
                status = await get_consumer_group_status(
                    redis_client, STREAM_NAME, GROUP_NAME
                )
                pending_count = int(status.get("pending_count", 0) or 0)
                if stream_len > STREAM_BACKLOG_THRESHOLD or pending_count > PENDING_BACKLOG_THRESHOLD:
                    logger.warning(
                        "LLM stream backing up: stream_len=%d, pending=%d",
                        stream_len,
                        pending_count,
                    )
            except Exception as exc:
                # Monitoring must never break recovery.
                logger.debug("LLM lag monitoring unavailable: %s", exc)

            recovered = await recover_pending_messages(
                redis_client,
                STREAM_NAME,
                GROUP_NAME,
                CONSUMER_NAME,
            )

            for claimed_id, fields in recovered:
                logger.info("Reprocessing stale LLM message: %s", claimed_id)
                await _process_message_with_retry(
                    redis_client, claimed_id, fields, llm_service
                )

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Error in LLM recovery loop: %s", exc)


async def _process_message_with_retry(
    redis_client: redis.Redis,
    message_id: bytes | str,
    fields: dict,
    llm_service: LLMService,
) -> None:
    """Process a message with automatic retry and DLQ handling (R3).

    Delegates to the same path the consume loop uses, so the recovery loop
    cannot diverge from it. Previously this was a near-verbatim copy whose
    handler was a bare ``logger.error``: an exception here produced no ack, no
    retry, no requeue and no DLQ, so the entry stayed in the PEL and was
    re-claimed every RECOVERY_INTERVAL forever, burning one Ollama generation
    per pass.
    """
    await _process_message_safe(redis_client, message_id, fields, llm_service)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
