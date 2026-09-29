"""VelocityStore — Redis-backed sliding-window velocity counts.

Records each created transaction into a Redis Sorted Set keyed
``velocity:{user_id}:tx`` (score = epoch ms of the transaction timestamp,
member = str(transaction id)) and reads 5-minute / 1-hour counts in a single
pipeline round trip. Falls back to Postgres when Redis is unavailable.

Accepted divergence (VEL-STORE-006): the Redis path MAY count soft-deleted
transactions until they are trimmed by the 24-hour window, while the Postgres
fallback excludes them (``deleted_at IS NULL``). Soft-deleted transactions are
never removed from the set on delete (deferred by design).
"""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.clock import Clock, SystemClock
from src.core.config import settings
from src.core.redis import get_redis
from src.models.transaction import Transaction

logger = logging.getLogger(__name__)

# ZSET key TTL in seconds: 25h — covers the 24h trim window plus slack so a
# set that stops receiving writes still expires (no unbounded growth).
VELOCITY_TTL_SECONDS = 90_000
# Members older than this (seconds) are trimmed before counting.
TRIM_SECONDS = 86_400
# Velocity windows in seconds — scores are epoch milliseconds (x1000).
WINDOW_5MIN = 300
WINDOW_1H = 3_600

# Error family that means "Redis unavailable" — swallowed, never raised into
# the request path. RedisError covers connection/timeout errors; OSError covers
# socket-level escapes. A programming bug in this store must still fail loudly,
# so bare Exception is intentionally NOT caught.
_REDIS_UNAVAILABLE = (RedisError, TimeoutError, OSError)


class VelocityStore:
    """Redis ZSET velocity counter with Postgres fallback.

    ``redis=None`` (default) resolves a client from the shared connection pool
    on every call — mirroring the ``enqueue`` precedent, so the store can be
    constructed once and reused across requests.

    ``clock`` is the other wall-clock reader. Velocity counts are derived from
    elapsed time, so a test that crosses a 5-minute or 1-hour window boundary
    is at the mercy of when it runs unless it supplies its own. Pass a
    :class:`~src.core.clock.FrozenClock` to pin it.
    """

    def __init__(self, redis: Redis | None = None, clock: Clock | None = None) -> None:
        self._redis = redis
        self._clock: Clock = clock or SystemClock()

    @staticmethod
    def _key(user_id: UUID) -> str:
        return f"velocity:{user_id}:tx"

    @staticmethod
    def _score(created_at: datetime) -> int:
        return int(created_at.timestamp() * 1000)

    async def record_transaction(
        self,
        user_id: UUID,
        transaction_id: UUID,
        created_at: datetime | None = None,
    ) -> None:
        """Record a transaction into the user's velocity set (best-effort).

        ZADD + EXPIRE renewal + 24h trim in one pipeline round trip. Never
        raises when Redis is unavailable (VEL-STORE-001); logging only.
        """
        if not settings.velocity_store_enabled:
            return
        created_at = created_at or self._clock.now_utc()
        key = self._key(user_id)
        score = self._score(created_at)
        now_ms = self._score(self._clock.now_utc())
        try:
            redis = self._redis if self._redis is not None else get_redis()
            pipe = redis.pipeline()
            pipe.zadd(key, {str(transaction_id): score})
            pipe.expire(key, VELOCITY_TTL_SECONDS)
            pipe.zremrangebyscore(key, "-inf", now_ms - TRIM_SECONDS * 1000)
            await pipe.execute()
        except _REDIS_UNAVAILABLE:
            logger.warning(
                "velocity: failed to record transaction %s for user %s (Redis unavailable)",
                transaction_id,
                user_id,
            )

    async def get_counts(
        self,
        user_id: UUID,
        db: AsyncSession,
        *,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Return ``{"5min": n, "1h": m}`` for the user.

        Reads via a single pipeline RTT: trim >24h, then inclusive ZCOUNT for
        the 5-minute and 1-hour windows (lower bound included). On Redis
        failure, falls back to Postgres (VEL-STORE-005) or, when the toggle is
        disabled, skips Redis entirely (VEL-STORE-007).
        """
        now = now or self._clock.now_utc()
        if not settings.velocity_store_enabled:
            return await self._pg_counts(user_id, db, now=now)
        key = self._key(user_id)
        now_ms = self._score(now)
        try:
            redis = self._redis if self._redis is not None else get_redis()
            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, "-inf", now_ms - TRIM_SECONDS * 1000)
            pipe.zcount(key, now_ms - WINDOW_5MIN * 1000, "+inf")
            pipe.zcount(key, now_ms - WINDOW_1H * 1000, "+inf")
            _, count_5min, count_1h = await pipe.execute()
            return {"5min": int(count_5min), "1h": int(count_1h)}
        except _REDIS_UNAVAILABLE:
            logger.warning(
                "velocity: Redis unavailable for user %s, falling back to Postgres",
                user_id,
            )
            return await self._pg_counts(user_id, db, now=now)

    async def _pg_counts(
        self,
        user_id: UUID,
        db: AsyncSession,
        *,
        now: datetime,
    ) -> dict[str, int]:
        """Postgres fallback — one query over the last hour, split at 5 min.

        Mirrors the removed Query A semantics: excludes soft-deleted rows.
        """
        one_hour_ago = now - timedelta(seconds=WINDOW_1H)
        five_min_ago = now - timedelta(seconds=WINDOW_5MIN)
        result = await db.execute(
            select(Transaction.created_at).where(
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
                Transaction.created_at >= one_hour_ago,
            )
        )
        timestamps = list(result.scalars().all())
        count_5min = sum(1 for ts in timestamps if ts >= five_min_ago)
        return {"5min": count_5min, "1h": len(timestamps)}