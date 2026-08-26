"""Redis-backed rate limiter — fixed-window counters per IP + endpoint.

Uses Redis INCR + EXPIRE for cross-process, crash-safe counters.
Fails open (allows request) if Redis is unavailable — documented choice
matching the best-effort pattern used elsewhere in this codebase.

Designed for FastAPI dependency injection.
"""

import logging
import time
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from src.core.config import settings
from src.core.dependencies import get_redis

logger = logging.getLogger(__name__)

# Rate limits: (path_prefix, max_requests, window_seconds)
RATE_LIMITS: dict[str, tuple[int, float]] = {
    "/api/v1/auth/login": (10, 60.0),  # 10 attempts per 60 seconds
    "/api/v1/auth/register": (10, 60.0),  # 10 attempts per 60 seconds
    "/api/v1/auth/refresh": (5, 60.0),  # 5 attempts per 60 seconds (F5)
    "/api/v1/transactions": (100, 60.0),
    "/api/v1/alerts": (60, 60.0),
}


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request.

    When ``settings.trust_proxy_headers`` is ``True``, reads the
    ``X-Real-IP`` header first (a single-value header set by a trusted
    reverse proxy like nginx — not spoofable by clients). Falls back to
    the leftmost ``X-Forwarded-For`` entry if ``X-Real-IP`` is absent.

    When ``trust_proxy_headers`` is ``False`` (default), uses
    ``request.client.host`` directly — spoof-proof.
    """
    if settings.trust_proxy_headers:
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

    client = getattr(request, "client", None)
    if client is not None:
        host = getattr(client, "host", None)
        if host is not None:
            return host
    return "unknown"


def _window_bucket(window_seconds: float) -> str:
    """Return a string bucket key for the current time window."""
    return str(int(time.time() // window_seconds))


async def check_rate_limit(
    request: Request,
    redis: Redis = Depends(get_redis),
) -> None:
    """FastAPI dependency — checks rate limit for the request path.

    Uses Redis INCR + EXPIRE for a fixed-window counter keyed by
    ``(client_ip, path_prefix, window_bucket)``.  The first hit in a
    window sets the TTL; subsequent hits increment the counter.

    Redis is injected via FastAPI DI so test fixtures can override it.

    Raises 429 Too Many Requests if the limit is exceeded.
    Fails open on Redis errors (logger.warning).
    """
    path = request.url.path
    client_ip = _get_client_ip(request)

    # Find matching rate limit
    limit_key = None
    max_req = 0
    window = 0.0
    for prefix, (mr, w) in RATE_LIMITS.items():
        if path.startswith(prefix):
            limit_key = prefix
            max_req = mr
            window = w
            break

    if limit_key is None:
        return  # no rate limit configured for this path

    bucket = _window_bucket(window)
    redis_key = f"ratelimit:{client_ip}:{limit_key}:{bucket}"

    try:
        count = await redis.incr(redis_key)  # type: ignore[misc]
        if count == 1:
            # First request in this window — set TTL.
            await redis.expire(redis_key, int(window) + 1)  # type: ignore[misc]

        if count > max_req:
            retry_after = max(1, int(window - (time.time() % window)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
    except HTTPException:
        raise  # re-raise 429 — not a Redis error
    except Exception:
        logger.warning(
            "Redis unavailable for rate limiting on %s — failing open",
            path,
            exc_info=True,
        )


def rate_limit_middleware(
    max_requests: int,
    window_seconds: float = 60.0,
) -> Callable[[Request], None]:
    """Factory for rate-limit dependencies with custom limits.

    Uses in-memory counters (per-process) — suitable for single-worker
    dev servers or endpoints that need isolated limits.

    Usage::

        @router.post("/endpoint")
        async def handler(
            request: Request,
            _: None = Depends(rate_limit_middleware(30, 60)),
        ):
            ...
    """
    from collections import defaultdict

    _custom_log: dict[tuple[str, str], list[float]] = defaultdict(list)

    def dependency(request: Request) -> None:
        client_ip = _get_client_ip(request)
        path = request.url.path
        now = time.time()
        log_key = (client_ip, path)

        _custom_log[log_key] = [
            t for t in _custom_log[log_key] if t > now - window_seconds
        ]

        if len(_custom_log[log_key]) >= max_requests:
            retry_after = int(window_seconds - (now - _custom_log[log_key][0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        _custom_log[log_key].append(now)

    return dependency
