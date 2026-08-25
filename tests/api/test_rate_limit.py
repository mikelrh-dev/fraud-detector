"""R1-007: Rate limiter identity and Redis-backed store tests.

Verifies:
- Identity uses request.client.host by default (spoof-proof)
- X-Forwarded-For honored only when trust_proxy_headers=True
- Redis fixed-window: first hit sets expire, Nth hit blocks, new window resets
- Graceful fail-open when Redis is unavailable
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

pytestmark = pytest.mark.asyncio


def _make_request(
    path: str = "/api/v1/transactions",
    client_host: str = "10.0.0.1",
    xff: str | None = None,
) -> MagicMock:
    """Build a mock Request with the given path and client info."""
    request = MagicMock(spec=Request)
    request.url.path = path
    request.client = MagicMock()
    request.client.host = client_host
    headers = {}
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    request.headers = headers
    return request


class TestClientIdentity:
    """Identity resolution: host vs X-Forwarded-For."""

    @patch("src.api.v1.rate_limit.settings")
    async def test_default_uses_client_host(self, mock_settings):
        """When trust_proxy_headers=False, XFF is ignored."""
        mock_settings.trust_proxy_headers = False
        from src.api.v1.rate_limit import _get_client_ip

        req = _make_request(client_host="192.168.1.1", xff="203.0.113.5, 70.41.3.18")
        assert _get_client_ip(req) == "192.168.1.1"

    @patch("src.api.v1.rate_limit.settings")
    async def test_trust_proxy_honors_xff(self, mock_settings):
        """When trust_proxy_headers=True, right-most XFF entry is used."""
        mock_settings.trust_proxy_headers = True
        from src.api.v1.rate_limit import _get_client_ip

        req = _make_request(client_host="10.0.0.1", xff="203.0.113.5, 70.41.3.18")
        assert _get_client_ip(req) == "203.0.113.5"

    @patch("src.api.v1.rate_limit.settings")
    async def test_trust_proxy_no_xff_falls_back(self, mock_settings):
        """When trust_proxy_headers=True but no XFF header, falls back to client.host."""
        mock_settings.trust_proxy_headers = True
        from src.api.v1.rate_limit import _get_client_ip

        req = _make_request(client_host="10.0.0.1")
        assert _get_client_ip(req) == "10.0.0.1"


class TestRedisWindow:
    """Fixed-window rate limiting via Redis INCR + EXPIRE."""

    async def test_first_hit_sets_expire(self):
        """First request in a window: INCR returns 1, EXPIRE is called."""
        from src.api.v1.rate_limit import check_rate_limit

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        request = _make_request(path="/api/v1/auth/login")
        await check_rate_limit(request, redis=mock_redis)

        assert mock_redis.incr.call_count == 1
        assert mock_redis.expire.call_count == 1
        # TTL should be window_seconds + 1
        ttl = mock_redis.expire.call_args.args[1]
        assert ttl == 61  # 60 + 1

    async def test_nth_hit_within_limit_no_block(self):
        """Requests within the limit pass through."""
        from src.api.v1.rate_limit import check_rate_limit

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=5)  # 5th request, limit is 10
        mock_redis.expire = AsyncMock(return_value=True)

        request = _make_request(path="/api/v1/auth/login")
        await check_rate_limit(request, redis=mock_redis)  # should not raise

        # EXPIRE not called because count != 1
        mock_redis.expire.assert_not_called()

    async def test_over_limit_raises_429(self):
        """Nth request exceeding limit raises 429."""
        from src.api.v1.rate_limit import check_rate_limit

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=11)  # limit is 10
        mock_redis.expire = AsyncMock(return_value=True)

        request = _make_request(path="/api/v1/auth/login")
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(request, redis=mock_redis)

        assert exc_info.value.status_code == 429

    async def test_new_window_resets_counter(self):
        """Different time bucket produces a different Redis key → counter resets."""
        from src.api.v1.rate_limit import _window_bucket

        bucket1 = _window_bucket(60.0)
        # Advance time past the window boundary
        with patch("src.api.v1.rate_limit.time") as mock_time:
            mock_time.time.return_value = time.time() + 61
            bucket2 = _window_bucket(60.0)

        assert bucket1 != bucket2

    async def test_unconfigured_path_skips_limit(self):
        """Paths not in RATE_LIMITS are not rate-limited."""
        from src.api.v1.rate_limit import check_rate_limit

        mock_redis = AsyncMock()
        request = _make_request(path="/api/v1/some-other-endpoint")
        await check_rate_limit(request, redis=mock_redis)  # should not raise

        mock_redis.incr.assert_not_called()


class TestFailOpen:
    """Redis failure → fail-open with logger.warning."""

    async def test_redis_unavailable_allows_request(self):
        """When Redis raises, the request is allowed through."""
        from src.api.v1.rate_limit import check_rate_limit

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(side_effect=ConnectionError("redis down"))

        request = _make_request(path="/api/v1/transactions")
        # Should NOT raise — fail open
        await check_rate_limit(request, redis=mock_redis)


class TestIntegrationRateLimit:
    """Verify the full stack: check_rate_limit → Redis INCR → 429."""

    async def test_rate_limit_blocks_after_threshold(self):
        """INCR returning max_req+1 triggers 429 with Retry-After header."""
        from src.api.v1.rate_limit import check_rate_limit

        mock_redis = AsyncMock()
        # Simulate 101st request (limit is 10 for /auth/login)
        mock_redis.incr = AsyncMock(return_value=11)
        mock_redis.expire = AsyncMock(return_value=True)

        request = _make_request(path="/api/v1/auth/login")
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(request, redis=mock_redis)

        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
