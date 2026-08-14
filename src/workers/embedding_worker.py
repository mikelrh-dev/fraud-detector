"""Embedding Worker — Asynchronous merchant spoofing detection.

Processes transactions from Redis queue and performs merchant spoofing analysis
using sentence embeddings. Results are stored for later retrieval by the API.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import redis.asyncio as redis

from src.core.config import settings
from src.services.merchant_embedding_service import MerchantEmbeddingService

logger = logging.getLogger(__name__)


class EmbeddingWorker:
    """Async worker for merchant embedding analysis."""

    def __init__(self):
        """Initialize the embedding worker."""
        self.redis_client: redis.Redis | None = None
        self.embedding_service = MerchantEmbeddingService()
        self.queue_key = "fraud:embeddings"
        self.result_key_prefix = "embedding_result"

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
        """Process embedding queue continuously.
        
        Listens for messages on the embedding queue and performs
        spoofing detection for each transaction.
        """
        if not self.redis_client:
            await self.connect()

        logger.info("Starting embedding worker, listening on queue: %s", self.queue_key)

        while True:
            try:
                # Blocking pop from queue (waits up to 1 second)
                result = await self.redis_client.brpop(self.queue_key, timeout=1)

                if result is None:
                    # No message, check health periodically
                    continue

                queue_name, message = result
                await self.process_message(message.decode("utf-8"))

            except Exception as exc:
                logger.error("Error in embedding worker loop: %s", exc)
                await asyncio.sleep(1)  # Backoff on error

    async def process_message(self, message_json: str) -> None:
        """Process a single embedding task.
        
        Args:
            message_json: JSON string with transaction data
        """
        try:
            message = json.loads(message_json)
            transaction_id = message.get("transaction_id")
            merchant_name = message.get("merchant_name")

            if not merchant_name:
                logger.warning("Received message without merchant_name: %s", transaction_id)
                return

            # Perform spoofing detection
            is_spoofed, matched_merchant, similarity = self.embedding_service.detect_spoofing(
                merchant_name
            )

            # Store result
            result = {
                "transaction_id": transaction_id,
                "merchant_name": merchant_name,
                "is_spoofed": is_spoofed,
                "matched_merchant": matched_merchant,
                "similarity_score": similarity,
                "processed_at": datetime.now(tz=timezone.utc).isoformat(),
            }

            result_key = f"{self.result_key_prefix}:{transaction_id}"
            await self.redis_client.setex(
                result_key,
                86400,  # Expire after 24 hours
                json.dumps(result),
            )

            logger.info(
                "Processed embedding for transaction %s: spoofed=%s, match=%s, similarity=%.3f",
                transaction_id,
                is_spoofed,
                matched_merchant,
                similarity or 0.0,
            )

        except json.JSONDecodeError as exc:
            logger.error("Failed to parse message: %s", exc)
        except Exception as exc:
            logger.error("Error processing embedding message: %s", exc)


async def main() -> None:
    """Entry point for the embedding worker."""
    worker = EmbeddingWorker()

    try:
        await worker.connect()
        await worker.process_queue()
    except KeyboardInterrupt:
        logger.info("Embedding worker stopped by user")
    except Exception as exc:
        logger.error("Embedding worker crashed: %s", exc)
    finally:
        await worker.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
