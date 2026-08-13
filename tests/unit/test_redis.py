"""Tests for Redis connection pool and queue helpers."""

import json
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import ConnectionPool, Redis

from src.core.redis import enqueue_for_retry, get_redis, redis_pool


def test_redis_pool_is_connection_pool():
    """Redis pool should be a ConnectionPool."""
    assert isinstance(redis_pool, ConnectionPool)


def test_get_redis_returns_redis_instance():
    """get_redis should return a Redis instance."""
    redis_client = get_redis()
    assert isinstance(redis_client, Redis)
    assert redis_client.connection_pool is redis_pool


@pytest.mark.asyncio
async def test_enqueue_for_retry_increments_retry_count():
    """Re-enqueue must increment retry_count and push to the queue."""
    redis_client = AsyncMock()
    message = {"transaction_id": "abc", "retry_count": 0}

    await enqueue_for_retry(redis_client, message, "fraud:shap")

    redis_client.lpush.assert_awaited_once_with(
        "fraud:shap", json.dumps({"transaction_id": "abc", "retry_count": 1})
    )


@pytest.mark.asyncio
async def test_enqueue_for_retry_defaults_retry_count_to_one():
    """A message without retry_count should be re-enqueued as retry 1."""
    redis_client = AsyncMock()

    await enqueue_for_retry(redis_client, {"transaction_id": "abc"}, "fraud:shap")

    _, payload = redis_client.lpush.await_args.args
    assert json.loads(payload)["retry_count"] == 1

