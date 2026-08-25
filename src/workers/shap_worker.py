"""SHAP Attribution Worker — consumes Redis Streams (fraud:shap) and computes feature attribution.

Uses Redis Consumer Groups (XREADGROUP) for scaling horizontally.
Consumer group: "shap-workers"
Stream: "fraud:shap"

Features:
- Automatic recovery of stuck messages (XAUTOCLAIM)
- Dead-letter queue for failed messages after MAX_RETRIES
- At-least-once delivery semantics
"""

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis
from sqlalchemy import delete

from src.core.database import async_session_maker
from src.core.stream_dlq import (
    get_consumer_group_status,
    recover_pending_messages,
    send_to_dlq,
)
from src.core.stream_publisher import ensure_consumer_group
from src.models.shap_attribution import ShapAttribution
from src.services.shap_service import ShapService, ShapUnavailableError

logger = logging.getLogger(__name__)

STREAM_NAME = "fraud:shap"
GROUP_NAME = "shap-workers"
CONSUMER_NAME = "shap-worker-1"
MAX_RETRIES = 3
RECOVERY_INTERVAL = 60  # Check for stuck messages every 60 seconds
BACKOFF_CAP_SECONDS = 60  # Upper bound for retry backoff (R4-004)


def _backoff_delay(retry_count: int) -> int:
    """Exponential backoff before re-enqueueing a failed message."""
    return min(2**retry_count, BACKOFF_CAP_SECONDS)


async def process_shap_message(
    message: dict[str, Any],
    db: Any,
    shap_service: ShapService,
) -> bool:
    """Process a single SHAP request from the stream.

    Returns:
        True if processed (success or permanent failure — no re-enqueue),
        False if must be retried.
    """
    transaction_id = message.get("transaction_id", "unknown")
    features = message.get("features", [])
    feature_names = message.get("feature_names")

    try:
        # CPU-bound work runs async
        contributions = await asyncio.to_thread(
            shap_service.explain,
            features,
            feature_names,
        )

        # Persist to DB (delete old, insert new — idempotent)
        async with async_session_maker() as session:
            # Delete old attributions for this transaction
            await session.execute(
                delete(ShapAttribution).where(
                    ShapAttribution.transaction_id == transaction_id
                )
            )

            # Insert new attributions (top 5)
            for rank, contrib in enumerate(contributions[:5], 1):
                attr = ShapAttribution(
                    transaction_id=transaction_id,
                    feature=contrib.feature,
                    contribution=float(contrib.contribution),
                    rank=rank,
                )
                session.add(attr)

            await session.commit()

        logger.info(
            "SHAP computed for transaction %s: %d features",
            transaction_id,
            len(contributions),
        )
        return True

    except ShapUnavailableError as exc:
        logger.warning(
            "SHAP unavailable for transaction %s: %s — skipping",
            transaction_id,
            exc,
        )
        return True

    except Exception as exc:
        logger.exception(
            "SHAP computation failed for transaction %s: %s",
            transaction_id,
            exc,
        )
        return False  # Retry


async def worker_loop(redis_client: redis.Redis) -> None:
    """Main worker loop — consume from stream with consumer group.

    Features:
    - Processes new messages from XREADGROUP
    - Recovers stuck messages via XAUTOCLAIM every 60s
    - Sends failed messages to DLQ after MAX_RETRIES
    """
    await ensure_consumer_group(STREAM_NAME, GROUP_NAME)
    shap_service = ShapService()

    logger.info("SHAP worker started: stream=%s, group=%s", STREAM_NAME, GROUP_NAME)

    # Task to recover pending messages periodically
    recovery_task = asyncio.create_task(_recovery_loop(redis_client))

    try:
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
                for _stream_name, msg_list in messages:
                    for message_id, fields in msg_list:
                        await _process_message_with_retry(
                            redis_client,
                            message_id,
                            fields,
                            shap_service,
                        )

            except Exception as exc:
                logger.error("Error in SHAP worker loop: %s", exc)
                await asyncio.sleep(1)  # Backoff

    finally:
        recovery_task.cancel()
        await redis_client.close()


async def _process_message_with_retry(
    redis_client: redis.Redis,
    message_id: bytes,
    fields: dict,
    shap_service: ShapService,
) -> None:
    """Process a message with automatic retry and DLQ handling."""
    try:
        # Decode message
        data_json = fields.get(b"data", b"{}").decode("utf-8")
        message_data = json.loads(data_json)

        retry_count = message_data.get("retry_count", 0)
        transaction_id = message_data.get("transaction_id", "unknown")

        # Try to process
        async with async_session_maker() as db:
            success = await process_shap_message(message_data, db, shap_service)

        if success:
            # Success: ACK and remove from pending
            await redis_client.xack(STREAM_NAME, GROUP_NAME, message_id)
            logger.debug("SHAP message ACKed: %s", message_id)
        else:
            # Failure: check retry count
            if retry_count >= MAX_RETRIES:
                # Max retries exceeded: send to DLQ
                dlq_message_id = (
                    message_id.decode("utf-8")
                    if isinstance(message_id, bytes)
                    else str(message_id)
                )
                await send_to_dlq(
                    redis_client,
                    STREAM_NAME,
                    dlq_message_id,
                    GROUP_NAME,
                    CONSUMER_NAME,
                    f"Max retries ({MAX_RETRIES}) exceeded",
                    message_data,
                )
                logger.warning(
                    "SHAP message sent to DLQ: %s (retries: %d)",
                    transaction_id,
                    retry_count,
                )
            else:
                # Retry: increment counter, back off, then re-enqueue (R4-004)
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
                    "SHAP message re-queued for retry: %s (attempt %d/%d)",
                    transaction_id,
                    retry_count + 1,
                    MAX_RETRIES,
                )

    except Exception as exc:
        logger.error("Error processing SHAP message: %s", exc)


async def _recovery_loop(redis_client: redis.Redis) -> None:
    """Periodically recover stuck messages from the pending list."""
    while True:
        try:
            await asyncio.sleep(RECOVERY_INTERVAL)

            # Get status
            status = await get_consumer_group_status(
                redis_client, STREAM_NAME, GROUP_NAME
            )
            if status.get("pending_count", 0) > 0:
                logger.info(
                    "Found %d pending messages, attempting recovery",
                    status["pending_count"],
                )

                # Recover stuck messages
                recovered = await recover_pending_messages(
                    redis_client,
                    STREAM_NAME,
                    GROUP_NAME,
                    CONSUMER_NAME,
                )

                if recovered:
                    logger.info("Recovered %d stuck messages", len(recovered))
                    # R4-003: route claimed entries through the retry pipeline
                    # instead of dropping them back into the PEL forever.
                    shap_service = ShapService()
                    for claimed_id, claimed_fields in recovered:
                        await _process_message_with_retry(
                            redis_client,
                            claimed_id,
                            claimed_fields,
                            shap_service,
                        )

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Error in recovery loop: %s", exc)  # Backoff


async def main() -> None:
    """Entry point."""
    from src.core.config import settings

    redis_client = await redis.from_url(settings.redis_url)

    try:
        await worker_loop(redis_client)
    except KeyboardInterrupt:
        logger.info("SHAP worker stopped by user")
    finally:
        await redis_client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
