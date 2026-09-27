"""Token revocation tests — R1-002 (audit wave 2).

Logout must actually revoke the presented access token, and a rotated
refresh token must not be reusable. Uses a small stateful Redis stand-in so
blacklist writes are visible across requests within a test.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.core.dependencies import get_redis
from src.core.security import create_access_token, create_refresh_token

pytestmark = pytest.mark.asyncio


class _StatefulFakeRedis:
    """Minimal async Redis stand-in persisting keys within a test."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0


@pytest.fixture()
def fake_redis(test_client: AsyncClient) -> _StatefulFakeRedis:
    """Swap the mocked redis for a stateful one after client setup."""
    fake = _StatefulFakeRedis()
    from src.api.main import app

    async def _override():
        yield fake

    app.dependency_overrides[get_redis] = _override
    return fake


class TestLogoutRevokesAccess:
    """POST /auth/logout must invalidate the presented access token."""

    async def test_logged_out_token_is_rejected(
        self, test_client: AsyncClient, fake_redis: _StatefulFakeRedis
    ):
        token = create_access_token(user_id="u1", role="analyst")
        headers = {"Authorization": f"Bearer {token}"}

        first = await test_client.post("/api/v1/auth/logout", headers=headers)
        assert first.status_code == 204

        # Same token must now be refused anywhere auth is required.
        second = await test_client.post("/api/v1/auth/logout", headers=headers)
        assert second.status_code == 401
        assert "revoked" in second.json()["detail"].lower()


class TestRefreshRotationReplay:
    """A consumed refresh token must not grant another pair."""

    async def test_used_refresh_token_cannot_be_replayed(
        self,
        test_client: AsyncClient,
        fake_redis: _StatefulFakeRedis,
        mock_db: AsyncMock,
        mock_user_row,
    ):
        # A1: /auth/refresh now loads the user, and `sub` is `str(user.id)`,
        # which is a UUID. The previous "u1" could not pass either check.
        user_id = str(uuid4())
        mock_user_row(mock_db, user_id, role="analyst")

        refresh = create_refresh_token(user_id=user_id, role="analyst")
        headers = {"Authorization": f"Bearer {refresh}"}

        first = await test_client.post("/api/v1/auth/refresh", headers=headers)
        assert first.status_code == 200

        replay = await test_client.post("/api/v1/auth/refresh", headers=headers)
        assert replay.status_code == 401
