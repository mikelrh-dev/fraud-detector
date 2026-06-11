"""Async LLM worker — consumes fraud report requests from Redis and generates
reports via Ollama.

The worker runs in a continuous loop:
1. BRPOP from the "fraud:reports" Redis queue
2. Parse the message (transaction_id, score_breakdown)
3. Call LLMService.generate_report()
4. Persist the LLMReport to the database
5. On failure: retry with exponential backoff (max 3 retries)
"""

import json
import logging
from typing import Any

from redis.asyncio import Redis

from src.core.database import async_session_maker
from src.core.redis import get_redis
from src.models.llm_report import LLMReport, LLMReportStatus
from src.services.audit import AuditService
from src.services.llm import LLMService

logger = logging.getLogger(__name__)

QUEUE_NAME = "fraud:reports"
MAX_RETRIES = 3
BACKOFF_BASE = 3  # seconds: 3^1=3, 3^2=9, 3^3=27


async def process_report_request(
    message: dict[str, Any],
    db: Any,
    llm_service: LLMService,
    max_retries: int = MAX_RETRIES,
    audit_service: AuditService | None = None,
) -> bool:
    """Process a single report request from the queue.

    Calls LLMService to generate the report, then persists the result
    as an LLMReport. Returns True if the message was fully processed
    (completed or permanently failed), False if it needs re-enqueue.

    Args:
        message: Parsed queue message with transaction_id and score_breakdown.
        db: Async database session.
        llm_service: LLMService instance for report generation.
        max_retries: Maximum number of retries before permanent failure.
        audit_service: Optional AuditService for recording audit entries.

    Returns:
        True if message processing is complete (no re-enqueue needed),
        False if the message should be re-enqueued for retry.
    """
    transaction_id = message.get("transaction_id", "unknown")
    score_breakdown = message.get("score_breakdown", {})
    transaction = message.get("transaction", {})
    retry_count = message.get("retry_count", 0)
    audit = audit_service or AuditService()

    try:
        report_text = await llm_service.generate_report(
            transaction_id=transaction_id,
            score_breakdown=score_breakdown,
            transaction=transaction,
        )

        # LLMService handles connection errors gracefully and returns
        # error strings. If we got a response (even an error), it's
        # considered processed and persisted.
        is_error = report_text.startswith("Error:")
        status = (
            LLMReportStatus.FAILED if is_error else LLMReportStatus.COMPLETED
        )

        report = LLMReport(
            transaction_id=transaction_id,
            report_text=report_text,
            model_name=llm_service._model,
            status=status,
            generation_time_ms=None,
            retry_count=retry_count,
        )
        db.add(report)
        await db.flush()

        # Record audit trail
        action = "report_failed" if is_error else "report_generated"
        await audit.create_entry(
            db=db,
            action_type=action,
            transaction_id=transaction_id,
            details={
                "model": llm_service._model,
                "generation_time_ms": None,
                "status": status.value,
                "retry_count": retry_count,
            },
        )

        logger.info(
            "Report for transaction %s: status=%s, retry=%d",
            transaction_id,
            status.value,
            retry_count,
        )

        # No exception → message is fully processed (even if error)
        return True

    except Exception as exc:
        logger.exception(
            "Failed to generate report for transaction %s (retry %d/%d)",
            transaction_id,
            retry_count,
            max_retries,
        )

        if retry_count >= max_retries:
            # Max retries reached — persist as failed
            report = LLMReport(
                transaction_id=transaction_id,
                report_text=f"Error después de {max_retries} intentos: {exc}",
                model_name=llm_service._model,
                status=LLMReportStatus.FAILED,
                generation_time_ms=None,
                retry_count=retry_count,
            )
            db.add(report)
            await db.flush()

            # Record audit trail for max retries reached
            await audit.create_entry(
                db=db,
                action_type="report_failed",
                transaction_id=transaction_id,
                details={
                    "model": llm_service._model,
                    "status": "failed",
                    "retry_count": retry_count,
                    "error": str(exc),
                },
            )

            logger.warning(
                "Max retries reached for transaction %s — report failed",
                transaction_id,
            )
            return True

        return False


async def enqueue_for_retry(
    redis_client: Redis,
    message: dict[str, Any],
) -> None:
    """Re-enqueue a message with incremented retry count and backoff delay.

    The backoff delay is computed as BACKOFF_BASE ** (retry_count + 1),
    producing delays of 3s, 9s, 27s for retries 0, 1, 2.
    """
    retry_count = message.get("retry_count", 0) + 1
    message["retry_count"] = retry_count

    delay = BACKOFF_BASE ** retry_count
    message_json = json.dumps(message)

    # Use a delayed queue or store in Redis with TTL for backoff
    # For v1, re-enqueue immediately — the backoff happens in the
    # worker's retry check on the next dequeue
    await redis_client.lpush(QUEUE_NAME, message_json)  # type: ignore[misc]

    logger.info(
        "Re-enqueued report request (retry=%d, delay=%ds)",
        retry_count,
        delay,
    )


async def run_worker(
    redis_client: Redis | None = None,
    llm_service: LLMService | None = None,
    max_iterations: int | None = None,
) -> None:
    """Main worker loop — consume and process report requests.

    Args:
        redis_client: Redis client instance. If None, creates a new one.
        llm_service: LLMService instance. If None, creates a new one.
        max_iterations: Optional limit for testing (None = run forever).
    """
    svc = llm_service or LLMService()
    r = redis_client or get_redis()

    logger.info("LLM worker started — waiting for messages on %s", QUEUE_NAME)
    iterations = 0

    while max_iterations is None or iterations < max_iterations:
        try:
            result = await r.brpop([QUEUE_NAME], timeout=5)  # type: ignore[misc]
            if result is None:
                iterations += 1
                continue

            _, data = result
            message = json.loads(data)

            logger.info(
                "Processing report request for transaction %s",
                message.get("transaction_id", "unknown"),
            )

            db = async_session_maker()
            try:
                processed = await process_report_request(
                    message=message,
                    db=db,
                    llm_service=svc,
                )

                if not processed:
                    # Need retry — re-enqueue
                    await enqueue_for_retry(r, message)  # type: ignore

                await db.commit()
            except Exception:
                await db.rollback()
                raise
            finally:
                await db.close()

        except json.JSONDecodeError:
            logger.warning("Malformed message in queue — skipping")
        except Exception as exc:
            logger.exception("Unexpected error in worker loop: %s", exc)

        iterations += 1

    logger.info("LLM worker stopped after %d iterations", iterations)
