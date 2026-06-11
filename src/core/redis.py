"""Redis async connection pool and queue helpers."""

import json
from typing import Any

from redis.asyncio import ConnectionPool, Redis

from src.core.config import settings

redis_pool = ConnectionPool.from_url(
    settings.redis_url,
    max_connections=20,
    decode_responses=True,
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
