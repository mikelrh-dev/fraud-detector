"""Refresh endpoint token-typing tests — R1-004 (audit wave 2).

A stolen access token must not be able to hit /auth/refresh, and the
refresh response must return a rotated pair (new access + new refresh).
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)

pytestmark = pytest.mark.asyncio


class TestRefreshEndpointTyping:
    """POST /api/v1/auth/refresh enforces typ=refresh."""

    async def test_access_token_cannot_refresh(self, test_client: AsyncClient):
        """An access token presented at /auth/refresh must be rejected."""
        access = create_access_token(user_id="u1", role="analyst")

        response = await test_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {access}"},
        )

        assert response.status_code == 401

    async def test_refresh_returns_rotated_pair(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_user_row
    ):
        """A valid refresh token returns a NEW access+refresh pair."""
        # A1: /auth/refresh loads the user, and `sub` is `str(user.id)`, a UUID.
        user_id = str(uuid4())
        mock_user_row(mock_db, user_id, role="analyst")
        refresh = create_refresh_token(user_id=user_id, role="analyst")

        response = await test_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {refresh}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] != refresh  # rotation happened
        assert data["refresh_token"] != refresh
        assert decode_access_token(data["access_token"])["sub"] == user_id
        assert decode_refresh_token(data["refresh_token"])["typ"] == "refresh"

    async def test_refresh_token_rejected_on_logout(self, test_client: AsyncClient):
        """A refresh token must not authenticate protected endpoints."""
        refresh = create_refresh_token(user_id="u1", role="analyst")

        response = await test_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {refresh}"},
        )

        assert response.status_code == 401
