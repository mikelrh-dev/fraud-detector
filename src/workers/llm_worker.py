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

from src.core.config import settings
from src.core.database import async_session_maker
from src.core.stream_publisher import ensure_consumer_group
from src.models.llm_report import LLMReport, LLMReportStatus
from src.services.audit import AuditService
from src.services.llm import LLMService

logger = logging.getLogger(__name__)

STREAM_NAME = "fraud:llm"
GROUP_NAME = "llm-workers"
CONSUMER_NAME = "llm-worker-1"
MAX_RETRIES = 3


async def process_report_request(
    message: dict[str, Any],
    db: Any,
    llm_service: LLMService,
) -> bool:
    """Process a single report request from the stream.

    Returns:
        True if processed (success or permanent failure),
        False if should retry.
    """
    transaction_id = message.get("transaction_id", "unknown")
    score_breakdown = message.get("score_breakdown", {})
    transaction = message.get("transaction", {})

    try:
        report_text = await llm_service.generate_report(
            transaction_id=transaction_id,
            score_breakdown=score_breakdown,
            transaction=transaction,
        )

        # Determine status
        is_error = report_text.startswith("Error:")
        status = LLMReportStatus.FAILED if is_error else LLMReportStatus.COMPLETED

        # Persist report
        report = LLMReport(
            transaction_id=transaction_id,
            report_text=report_text,
            model_name=llm_service._model,
            status=status,
            generation_time_ms=None,
            retry_count=0,
        )

        async with async_session_maker() as session:
            session.add(report)

            # Audit entry
            audit = AuditService()
            action = "report_failed" if is_error else "report_generated"
            await audit.create_entry(
                db=session,
                action_type=action,
                transaction_id=transaction_id,
                details={
                    "model": llm_service._model,
                    "status": status.value,
                },
            )

            await session.commit()

        logger.info(
            "LLM report %s for transaction %s",
            status.value,
            transaction_id,
        )
        return True

    except Exception as exc:
        logger.exception(
            "LLM report generation failed for transaction %s: %s",
            transaction_id,
            exc,
        )
        return False  # Retry


async def worker_loop(redis_client: redis.Redis) -> None:
    """Main worker loop — consume from stream with consumer group."""
    await ensure_consumer_group(STREAM_NAME, GROUP_NAME)
    llm_service = LLMService()

    logger.info("LLM worker started: stream=%s, group=%s", STREAM_NAME, GROUP_NAME)

    while True:
        try:
            # XREADGROUP: blocking read from consumer group
            messages = await redis_client.xreadgroup(
                GROUP_NAME,
                CONSUMER_NAME,
                {STREAM_NAME: ">"},  # ">" means new messages only
                count=1,
                block=1000,  # 1 second timeout
            )

            if not messages:
                continue

            # Process each message
            for stream_name, msg_list in messages:
                for message_id, fields in msg_list:
                    try:
                        # Decode message
                        data_json = fields.get(b"data", b"{}").decode("utf-8")
                        message_data = json.loads(data_json)

                        # Process
                        async with async_session_maker() as db:
                            success = await process_report_request(
                                message_data,
                                db,
                                llm_service,
                            )

                        # ACK if success
                        if success:
                            await redis_client.xack(STREAM_NAME, GROUP_NAME, message_id)
                            logger.debug("LLM message ACKed: %s", message_id)
                        else:
                            logger.warning("LLM message will retry: %s", message_id)

                    except Exception as exc:
                        logger.error("Error processing LLM message: %s", exc)

        except Exception as exc:
            logger.error("Error in LLM worker loop: %s", exc)
            await asyncio.sleep(1)  # Backoff


async def main() -> None:
    """Entry point."""
    redis_client = await redis.from_url(settings.redis_url)

    try:
        await worker_loop(redis_client)
    except KeyboardInterrupt:
        logger.info("LLM worker stopped by user")
    finally:
        await redis_client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
