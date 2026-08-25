"""Embedding Worker - Async merchant spoofing detection with Redis Streams.

Processing failures (R4-005) propagate to the caller so messages stay
unACKed in the PEL for the XAUTOCLAIM recovery loop to reprocess.
"""

import asyncio
import contextlib
import json
import logging
from datetime import datetime, timezone

import redis.asyncio as redis

from src.core.config import settings
from src.core.stream_dlq import recover_pending_messages
from src.core.stream_publisher import ensure_consumer_group
from src.services.merchant_embedding_service import MerchantEmbeddingService

logger = logging.getLogger(__name__)

STREAM_NAME = "fraud:embeddings"
GROUP_NAME = "embedding-workers"
CONSUMER_NAME = "embedding-worker-1"
RECOVERY_INTERVAL = 60  # Check for stuck messages every 60 seconds


class EmbeddingWorker:
    """Async worker for merchant embedding analysis with Redis Streams."""

    def __init__(self):
        """Initialize the embedding worker."""
        self.redis_client: redis.Redis | None = None
        self.embedding_service = MerchantEmbeddingService()

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self.redis_client = await redis.from_url(settings.redis_url)
            await self.redis_client.ping()
            logger.info("Connected to Redis for embedding worker")
        except Exception as exc:
            logger.error("Failed to connect to Redis: %s", exc)
            raise

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Disconnected from Redis")

    async def process_queue(self) -> None:
        """Process embedding stream continuously using consumer groups.

        Listens for messages on the embedding stream and performs
        spoofing detection for each transaction.
        """
        if not self.redis_client:
            await self.connect()
        redis_client = self.redis_client
        if redis_client is None:  # Defensive: connect() raises on failure.
            raise RuntimeError("Embedding worker Redis client is not connected")

        # Ensure consumer group exists
        await ensure_consumer_group(STREAM_NAME, GROUP_NAME)

        logger.info(
            "Starting embedding worker: stream=%s, group=%s, consumer=%s",
            STREAM_NAME,
            GROUP_NAME,
            CONSUMER_NAME,
        )

        # Start recovery task
        recovery_task = asyncio.create_task(self._recovery_loop())

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
                            try:
                                # Decode message
                                data_json = fields.get(b"data", b"{}").decode("utf-8")
                                message_data = json.loads(data_json)

                                # Process
                                await self.process_message(message_data)

                                # ACK if success
                                await redis_client.xack(
                                    STREAM_NAME, GROUP_NAME, message_id
                                )
                                logger.debug("Embedding message ACKed: %s", message_id)

                            except Exception as exc:
                                logger.error(
                                    "Error processing embedding message: %s", exc
                                )

                except Exception as exc:
                    logger.error("Error in embedding worker loop: %s", exc)
                    await asyncio.sleep(1)  # Backoff

        finally:
            recovery_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await recovery_task

    async def process_message(self, message: dict) -> None:
        """Process a single embedding task.

        Args:
            message: Dict with transaction data

        Raises:
            Exception: any processing failure propagates to the caller so
                the message stays pending (unACKed) and can be recovered
                later (R4-005 - failures must not be ACKed as success).
        """
        transaction_id = message.get("transaction_id")
        merchant_name = message.get("merchant_name")

        if not merchant_name:
            logger.warning("Received message without merchant_name: %s", transaction_id)
            return

        # Perform spoofing detection (R4-005: errors propagate, no swallow)
        is_spoofed, matched_merchant, similarity = (
            self.embedding_service.detect_spoofing(merchant_name)
        )

        # Store result in Redis (for API retrieval)
        if self.redis_client:
            result = {
                "transaction_id": transaction_id,
                "merchant_name": merchant_name,
                "is_spoofed": is_spoofed,
                "matched_merchant": matched_merchant,
                "similarity_score": similarity,
                "processed_at": datetime.now(tz=timezone.utc).isoformat(),
            }

            result_key = f"embedding_result:{transaction_id}"
            await self.redis_client.setex(
                result_key,
                3600,  # 1 hour TTL
                json.dumps(result),
            )

        logger.info(
            "Embedding processed: transaction=%s, spoofed=%s, similarity=%.2f",
            transaction_id,
            is_spoofed,
            similarity,
        )

    async def _recovery_loop(self) -> None:
        """Periodically recover stale pending messages via XAUTOCLAIM.

        Claims PEL entries idle for more than ``PENDING_TIMEOUT_MS`` from other
        consumers in the group, reprocesses them through ``process_message``,
        and ACKs them on success. Exceptions are logged per iteration and never
        crash the loop; cancellation propagates cleanly.
        """
        redis_client = self.redis_client
        if redis_client is None:
            raise RuntimeError("Embedding worker Redis client is not connected")

        while True:
            try:
                claimed = await recover_pending_messages(
                    redis_client,
                    STREAM_NAME,
                    GROUP_NAME,
                    CONSUMER_NAME,
                )

                for message_id, fields in claimed:
                    try:
                        data_json = fields.get(b"data", b"{}").decode("utf-8")
                        message_data = json.loads(data_json)

                        await self.process_message(message_data)
                        await redis_client.xack(STREAM_NAME, GROUP_NAME, message_id)
                        logger.debug(
                            "Recovered embedding message ACKed: %s", message_id
                        )
                    except Exception as exc:
                        logger.error(
                            "Error recovering embedding message %s: %s",
                            message_id,
                            exc,
                        )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Error in embedding recovery loop: %s", exc)

            await asyncio.sleep(RECOVERY_INTERVAL)

    async def run(self) -> None:
        """Run the worker (entry point)."""
        await self.connect()
        try:
            await self.process_queue()
        except KeyboardInterrupt:
            logger.info("Embedding worker stopped by user")
        finally:
            await self.disconnect()


async def main() -> None:
    """Entry point."""
    worker = EmbeddingWorker()
    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
