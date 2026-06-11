"""Tests for Redis connection pool and queue helpers."""

from redis.asyncio import ConnectionPool, Redis

from src.core.redis import get_redis, redis_pool


def test_redis_pool_is_connection_pool():
    """Redis pool should be a ConnectionPool."""
    assert isinstance(redis_pool, ConnectionPool)


def test_get_redis_returns_redis_instance():
    """get_redis should return a Redis instance."""
    redis_client = get_redis()
    assert isinstance(redis_client, Redis)
    assert redis_client.connection_pool is redis_pool
