"""In-memory rate limiter — tracks requests per IP + endpoint window.

Simple dict-based implementation that avoids external dependencies.
Windows reset every `window_seconds`. Designed for FastAPI dependency injection.
"""

import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import HTTPException, Request, status

# (ip, path_prefix) → list of timestamps
_request_log: dict[tuple[str, str], list[float]] = defaultdict(list)

# Rate limits: (path_prefix, max_requests, window_seconds)
RATE_LIMITS: dict[str, tuple[int, float]] = {
    "/api/v1/auth/login": (10, 60.0),
    "/api/v1/transactions": (100, 60.0),
    "/api/v1/alerts": (60, 60.0),
}


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request headers or direct connection."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # Use host as fallback when client is not directly available
    client = getattr(request, "client", None)
    if client is not None:
        host = getattr(client, "host", None)
        if host is not None:
            return host
    return "unknown"


def _cleanup(window_seconds: float) -> None:
    """Remove expired timestamps from all logs."""
    now = time.time()
    cutoff = now - window_seconds
    for key in list(_request_log.keys()):
        _request_log[key] = [t for t in _request_log[key] if t > cutoff]
        if not _request_log[key]:
            del _request_log[key]


def check_rate_limit(request: Request) -> None:
    """FastAPI dependency — checks rate limit for the request path.

    Raises 429 Too Many Requests if the limit is exceeded.
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

    now = time.time()
    log_key = (client_ip, limit_key)

    # Clean expired entries for this key
    _request_log[log_key] = [t for t in _request_log[log_key] if t > now - window]

    if len(_request_log[log_key]) >= max_req:
        retry_after = int(window - (now - _request_log[log_key][0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    _request_log[log_key].append(now)
    _cleanup(window)


def rate_limit_middleware(
    max_requests: int,
    window_seconds: float = 60.0,
) -> Callable[[Request], None]:
    """Factory for rate-limit dependencies with custom limits.

    Usage:
        @router.post("/endpoint")
        async def handler(request: Request, _: None = Depends(rate_limit_middleware(30, 60))):
            ...
    """
    _custom_log: dict[tuple[str, str], list[float]] = defaultdict(list)

    def dependency(request: Request) -> None:
        client_ip = _get_client_ip(request)
        path = request.url.path
        now = time.time()
        log_key = (client_ip, path)

        _custom_log[log_key] = [t for t in _custom_log[log_key] if t > now - window_seconds]

        if len(_custom_log[log_key]) >= max_requests:
            retry_after = int(window_seconds - (now - _custom_log[log_key][0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        _custom_log[log_key].append(now)

    return dependency
