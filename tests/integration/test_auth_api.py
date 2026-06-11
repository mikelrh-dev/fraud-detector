"""Auth API integration tests — register, login, refresh, logout, role enforcement.

Uses the test client with mocked DB and Redis dependencies.
"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock

from src.core.security import hash_password


pytestmark = pytest.mark.asyncio


class TestAuthLogin:
    """POST /api/v1/auth/login endpoint."""

    async def test_successful_login_returns_tokens(self, test_client: AsyncClient, mock_db: AsyncMock):
        """Valid credentials should return access and refresh tokens."""
        # Arrange: user exists in DB
        mock_result = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "test-user-uuid"
        mock_user.username = "test_analyst"
        mock_user.hashed_password = hash_password("test_password_123")
        mock_user.role = MagicMock()
        mock_user.role.value = "analyst"
        mock_user.is_active = True
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "test_analyst", "password": "test_password_123"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_invalid_credentials_returns_401(self, test_client: AsyncClient, mock_db: AsyncMock):
        """Invalid credentials should return 401."""
        # Arrange: no user found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "nonexistent", "password": "wrong_password"},
        )

        # Assert
        assert response.status_code == 401

    async def test_missing_fields_returns_422(self, test_client: AsyncClient):
        """Missing username/password should return 422."""
        response = await test_client.post(
            "/api/v1/auth/login",
            json={},
        )
        assert response.status_code == 422


class TestAuthRegister:
    """POST /api/v1/auth/register endpoint."""

    async def test_admin_can_register_user(self, test_client: AsyncClient, mock_db: AsyncMock, admin_headers: dict):
        """Admin can register a new user."""
        # Arrange: no existing user
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        response = await test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "new_user",
                "email": "new@example.com",
                "password": "secure_password_123",
                "role": "analyst",
            },
            headers=admin_headers,
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "password" not in data
        assert data["email"] == "new@example.com"

    async def test_duplicate_email_returns_409(self, test_client: AsyncClient, mock_db: AsyncMock, admin_headers: dict):
        """Duplicate email should return 409."""
        # Arrange: existing user found
        mock_result = MagicMock()
        existing_user = MagicMock()
        existing_user.email = "existing@example.com"
        mock_result.scalar_one_or_none.return_value = existing_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        response = await test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "another_user",
                "email": "existing@example.com",
                "password": "secure_password_123",
                "role": "analyst",
            },
            headers=admin_headers,
        )
        assert response.status_code == 409


class TestAuthProtectedAccess:
    """Authenticated access to protected endpoints."""

    async def test_valid_token_allows_access(self, test_client: AsyncClient, auth_headers: dict):
        """Valid token should allow access."""
        response = await test_client.get("/api/v1/health", headers=auth_headers)
        assert response.status_code == 200

    async def test_no_token_returns_401(self, test_client: AsyncClient):
        """Missing token should return 401."""
        response = await test_client.get("/api/v1/transactions")
        assert response.status_code == 401

    async def test_invalid_token_returns_401(self, test_client: AsyncClient):
        """Invalid token should return 401."""
        response = await test_client.get(
            "/api/v1/transactions",
            headers={"Authorization": "Bearer invalid_token_here"},
        )
        assert response.status_code == 401

    async def test_analyst_cannot_delete(self, test_client: AsyncClient, auth_headers: dict):
        """Analyst cannot access admin-only DELETE endpoint."""
        response = await test_client.delete(
            "/api/v1/transactions/00000000-0000-0000-0000-000000000001",
            headers=auth_headers,
        )
        assert response.status_code == 403


class TestAuthRefresh:
    """POST /api/v1/auth/refresh endpoint."""

    async def test_refresh_with_valid_token(self, test_client: AsyncClient):
        """Valid refresh token returns new tokens."""
        from src.core.security import create_access_token

        token = create_access_token(user_id="test-user", role="analyst")

        response = await test_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_refresh_with_expired_token(self, test_client: AsyncClient):
        """Expired refresh token returns 401."""
        from datetime import datetime, timedelta, timezone
        from jose import jwt as jose_jwt
        from src.core.config import settings

        past = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        token = jose_jwt.encode(
            {"sub": "test-user", "role": "analyst", "exp": past, "iat": past - timedelta(hours=1)},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        response = await test_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


class TestAuthLogout:
    """POST /api/v1/auth/logout endpoint."""

    async def test_logout_returns_204(self, test_client: AsyncClient, auth_headers: dict):
        """Logout should return 204 No Content."""
        response = await test_client.post(
            "/api/v1/auth/logout",
            headers=auth_headers,
        )
        assert response.status_code == 204
