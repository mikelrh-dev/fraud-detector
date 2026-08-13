"""Redis async connection pool and queue helpers."""

import json
import logging
from typing import Any

from redis.asyncio import ConnectionPool, Redis

from src.core.config import settings

logger = logging.getLogger(__name__)

redis_pool = ConnectionPool.from_url(
    settings.redis_url,
    max_connections=20,
    decode_responses=True,
    # Bound socket calls: a wedged Redis must not hang the hot path indefinitely.
    # redis-py temporarily disables the timeout for blocking BRPOP/BLPOP, so
    # dequeue() is unaffected.
    socket_connect_timeout=2.0,
    socket_timeout=2.0,
)


def get_redis() -> Redis:
    """Return a Redis client using the shared connection pool."""
    return Redis(connection_pool=redis_pool)


async def enqueue(queue_name: str, message: dict[str, Any]) -> None:
    """Push a JSON-serialized message onto a Redis list (LPUSH)."""
    redis_client = get_redis()
    await redis_client.lpush(queue_name, json.dumps(message))  # type: ignore[misc]


async def dequeue(queue_name: str, timeout: int = 0) -> dict[str, Any] | None:
    """Block and pop a message from a Redis list (BRPOP).

    Returns the parsed message dict, or None if the timeout expires.
    """
    redis_client = get_redis()
    result = await redis_client.brpop([queue_name], timeout=timeout)  # type: ignore[misc]
    if result is None:
        return None
    _, data = result
    return json.loads(data)


async def enqueue_for_retry(
    redis_client: Redis,
    message: dict[str, Any],
    queue_name: str,
    backoff_base: int = 3,
) -> None:
    """Re-enqueue a message with incremented retry count and backoff delay.

    The backoff delay is computed as ``backoff_base ** retry_count``
    (3s, 9s, 27s for retries 1, 2, 3). For v1 the message is re-enqueued
    immediately — the computed delay is informational only.

    Shared by the LLM and SHAP workers; mirrors the logic the LLM worker
    historically kept inline.
    """
    retry_count = message.get("retry_count", 0) + 1
    message["retry_count"] = retry_count

    delay = backoff_base**retry_count
    message_json = json.dumps(message)

    await redis_client.lpush(queue_name, message_json)  # type: ignore[misc]

    logger.info(
        "Re-enqueued %s message (retry=%d, delay=%ds)",
        queue_name,
        retry_count,
        delay,
    )
