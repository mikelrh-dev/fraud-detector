"""Auth API integration tests — register, login, refresh, logout, role enforcement.

Uses the test client with mocked DB and Redis dependencies.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.core.security import hash_password

pytestmark = pytest.mark.asyncio


# OAuth2 standard response value (RFC 6749); not a credential.
EXPECTED_AUTH_SCHEME = "bearer"


class TestAuthLogin:
    """POST /api/v1/auth/login endpoint."""

    async def test_successful_login_returns_tokens(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ):
        """Valid email credentials should return access and refresh tokens."""
        # Arrange: user exists in DB
        mock_result = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "test-user-uuid"
        mock_user.username = "test_analyst"
        mock_user.email = "test_analyst@example.com"
        mock_user.hashed_password = hash_password("test_password_123")
        mock_user.role = MagicMock()
        mock_user.role.value = "analyst"
        mock_user.is_active = True
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"email": "test_analyst@example.com", "password": "test_password_123"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == EXPECTED_AUTH_SCHEME

    async def test_invalid_credentials_returns_401(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ):
        """Invalid credentials should return 401."""
        # Arrange: no user found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@example.com", "password": "wrong_password"},
        )

        # Assert
        assert response.status_code == 401

    async def test_missing_fields_returns_422(self, test_client: AsyncClient):
        """Missing email/password should return 422."""
        response = await test_client.post(
            "/api/v1/auth/login",
            json={},
        )
        assert response.status_code == 422

    async def test_login_by_email_valid_credentials(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ):
        """Login with a valid email + password should return 200 with both tokens.

        After the email migration, POST /api/v1/auth/login with
        {"email": "admin@frauddetector.dev", "password": "admin123"} must authenticate the
        seeded admin user and return access_token, refresh_token and token_type "bearer".
        """
        # Arrange: seeded admin user (admin@frauddetector.dev / admin123) exists in DB
        mock_result = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "admin-uuid"
        mock_user.username = "admin"
        mock_user.email = "admin@frauddetector.dev"
        mock_user.hashed_password = hash_password("admin123")
        mock_user.role = MagicMock()
        mock_user.role.value = "admin"
        mock_user.is_active = True
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@frauddetector.dev", "password": "admin123"},
        )

        # Assert
        assert response.status_code == 200, (
            f"expected 200 for valid email login, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["access_token"], "response must include a non-empty access_token"
        assert data["refresh_token"], "response must include a non-empty refresh_token"
        assert data["token_type"] == EXPECTED_AUTH_SCHEME

    async def test_login_by_email_case_insensitive(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ):
        """Email lookup must be case-insensitive: ADMIN@frauddetector.dev == admin@frauddetector.dev.

        POST /api/v1/auth/login with an uppercase version of the stored email must
        still return 200 with both tokens.
        """
        # Arrange: seeded admin user (admin@frauddetector.dev / admin123) exists in DB
        mock_result = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "admin-uuid"
        mock_user.username = "admin"
        mock_user.email = "admin@frauddetector.dev"
        mock_user.hashed_password = hash_password("admin123")
        mock_user.role = MagicMock()
        mock_user.role.value = "admin"
        mock_user.is_active = True
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"email": "ADMIN@frauddetector.dev", "password": "admin123"},
        )

        # Assert
        assert response.status_code == 200, (
            f"expected 200 for case-insensitive email login, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["access_token"], "response must include a non-empty access_token"
        assert data["refresh_token"], "response must include a non-empty refresh_token"
        assert data["token_type"] == EXPECTED_AUTH_SCHEME

    async def test_login_by_email_unknown_returns_401(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ):
        """Login with an email that does not exist must return 401, never 200 or 422.

        POST /api/v1/auth/login with {"email": "nonexistent@test.com", "password": "x"}
        must return 401 Unauthorized without revealing whether the account exists.
        """
        # Arrange: no user found for that email
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@test.com", "password": "x"},
        )

        # Assert
        assert response.status_code == 401, (
            f"expected 401 for unknown email, got {response.status_code}: {response.text}"
        )

    async def test_login_old_username_field_still_fails(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ):
        """After the email migration the legacy username field must no longer be accepted.

        POST /api/v1/auth/login with {"username": "admin", "password": "admin123"}
        must return 422 (validation error) because username is not a recognized
        login field anymore — even though the admin user exists in the DB.
        """
        # Arrange: admin exists and would be found by username if the field were still honored
        mock_result = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "admin-uuid"
        mock_user.username = "admin"
        mock_user.email = "admin@frauddetector.dev"
        mock_user.hashed_password = hash_password("admin123")
        mock_user.role = MagicMock()
        mock_user.role.value = "admin"
        mock_user.is_active = True
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )

        # Assert
        assert response.status_code == 422, (
            f"expected 422 (username field not recognized), got {response.status_code}: {response.text}"
        )


class TestAuthRegister:
    """POST /api/v1/auth/register endpoint."""

    async def test_admin_can_register_user(
        self, test_client: AsyncClient, mock_db: AsyncMock, admin_headers: dict
    ):
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

    async def test_duplicate_email_returns_409(
        self, test_client: AsyncClient, mock_db: AsyncMock, admin_headers: dict
    ):
        """Duplicate email should return 409 without echoing the email address.

        The 409 detail MUST be generic (enumeration-safe): it must not contain
        the submitted email, otherwise an attacker can probe which accounts exist.
        """
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
        assert "existing@example.com" not in response.text, (
            f"409 detail must not echo the email address, got: {response.text}"
        )


class TestAuthRegisterSecurity:
    """POST /api/v1/auth/register — security hardening scenarios.

    Task 4.1 RED tests: rate limiting, enumeration-safe 409, SQLi rejection.
    Register is a PUBLIC endpoint (no auth required), so these tests exercise
    it exactly as an unauthenticated attacker would — no admin headers.
    """

    async def test_register_rate_limit_exceeded(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ):
        """After N register attempts in T seconds, return 429 Too Many Requests.

        The register endpoint must be rate limited the same way login is
        (RATE_LIMITS in src/api/v1/rate_limit.py — currently register is missing
        from that table, so the 11th request is NOT limited today).
        """
        # Arrange: no existing user → each request would succeed (201)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Use a TEST-NET-3 reserved IP (RFC 5737) so the rate-limit bucket is
        # isolated from the other tests in this file.
        headers = {"X-Forwarded-For": "203.0.113.50"}
        payload = {
            "username": "burst_user",
            "email": "burst@example.com",
            "password": "secure_password_123",
            "role": "analyst",
        }

        # Act: fire 11 rapid requests (expected limit: 10 per minute)
        responses = [
            await test_client.post(
                "/api/v1/auth/register", json=payload, headers=headers
            )
            for _ in range(11)
        ]

        # Assert
        assert all(r.status_code != 429 for r in responses[:10]), (
            "rate limit must not trigger before the limit is reached"
        )
        assert responses[-1].status_code == 429, (
            f"expected 429 on request 11, got {responses[-1].status_code}: {responses[-1].text}"
        )
        assert responses[-1].headers.get("Retry-After") is not None, (
            "429 response must include a Retry-After header"
        )

    async def test_register_duplicate_email_returns_generic_409(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ):
        """409 for duplicate email must NOT echo the email address.

        Current behavior echoes it: "User with email 'test@example.com' already exists"
        (src/services/auth.py). That is an email-enumeration vector. The detail must
        be a generic message with no account identifiers.
        """
        # Arrange: first call → no existing user (201); second call → existing user (409)
        no_user = MagicMock()
        no_user.scalar_one_or_none.return_value = None
        existing_user = MagicMock()
        existing_user.email = "test@example.com"
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_user
        mock_db.execute = AsyncMock(side_effect=[no_user, existing_result])

        payload = {
            "username": "user1",
            "email": "test@example.com",
            "password": "secure_password_123",
            "role": "analyst",
        }

        # Act
        first = await test_client.post("/api/v1/auth/register", json=payload)
        assert first.status_code == 201, (
            f"expected 201 on first register, got {first.status_code}: {first.text}"
        )

        second = await test_client.post(
            "/api/v1/auth/register",
            json={**payload, "username": "user2"},
        )

        # Assert
        assert second.status_code == 409, (
            f"expected 409 on duplicate email, got {second.status_code}: {second.text}"
        )
        detail = second.json().get("detail", "")
        assert detail, "409 detail must contain a generic message"
        assert "test@example.com" not in detail, (
            f"409 detail must not echo the email address, got: {detail!r}"
        )

    async def test_register_sqli_in_email_field_rejected(
        self, test_client: AsyncClient
    ):
        """SQLi payload in email field should be rejected with 422, never 500.

        The email field is validated by Pydantic EmailStr, so a malformed
        injection payload like "' OR 1=1 -- @example.com" must fail validation
        (422) before it ever reaches the database layer.
        """
        # Act
        response = await test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "hacker",
                "email": "' OR 1=1 -- @example.com",
                "password": "secure_password_123",
                "role": "analyst",
            },
        )

        # Assert
        assert response.status_code == 422, (
            f"expected 422 for SQLi email payload, got {response.status_code}: {response.text}"
        )

    async def test_register_sqli_in_username_field_rejected(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ):
        """SQLi payload in username field should be rejected with 422, never 500.

        The username field currently accepts any string (only min/max length), so
        "'; DROP TABLE users; --" sails through validation today and is stored as a
        literal username by the parameterized ORM query — returning 201 instead of
        rejecting it. A public register endpoint must reject injection metacharacters
        with 422 so payloads never reach the query layer.
        """
        # Arrange: mock says no existing user (would otherwise be 201 today)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        response = await test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "'; DROP TABLE users; --",
                "email": "test@example.com",
                "password": "secure_password_123",
                "role": "analyst",
            },
        )

        # Assert
        assert response.status_code == 422, (
            f"expected 422 for SQLi username payload, got {response.status_code}: {response.text}"
        )


class TestAuthProtectedAccess:
    """Authenticated access to protected endpoints."""

    async def test_valid_token_allows_access(
        self, test_client: AsyncClient, auth_headers: dict
    ):
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

    async def test_analyst_cannot_delete(
        self, test_client: AsyncClient, auth_headers: dict
    ):
        """Analyst cannot access admin-only DELETE endpoint."""
        response = await test_client.delete(
            "/api/v1/transactions/00000000-0000-0000-0000-000000000001",
            headers=auth_headers,
        )
        assert response.status_code == 403


class TestAuthRefresh:
    """POST /api/v1/auth/refresh endpoint."""

    async def test_refresh_with_valid_token(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_user_row
    ):
        """Valid refresh token returns new tokens."""
        from src.core.security import create_refresh_token

        # A1: `sub` is `str(user.id)` and `User.id` is a UUID, so a
        # legitimately issued token always carries a UUID. The endpoint now
        # parses it to load the user row.
        user_id = str(uuid4())
        token = create_refresh_token(user_id=user_id, role="analyst")
        mock_user_row(mock_db, user_id, role="analyst")

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
            {
                "sub": str(uuid4()),
                "role": "analyst",
                "exp": past,
                "iat": past - timedelta(hours=1),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        response = await test_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


class TestAuthRefreshReadsDatabase:
    """A1: refresh must consult the user, not trust the token.

    Before this, deactivating an account, soft-deleting it or demoting an
    admin changed nothing: the endpoint read `sub` and `role` from the JWT and
    minted a new pair without touching the database, so an old refresh token
    kept minting access tokens for up to 24 hours.
    """

    async def test_inactive_user_cannot_refresh(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_user_row
    ):
        from src.core.security import create_refresh_token

        user_id = str(uuid4())
        token = create_refresh_token(user_id=user_id, role="analyst")
        mock_user_row(mock_db, user_id, role="analyst", is_active=False)

        response = await test_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert "inactive" in response.json()["detail"].lower()

    async def test_deleted_user_cannot_refresh(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_user_row
    ):
        """A soft-deleted row never matches the query, so it reads as missing."""
        from src.core.security import create_refresh_token

        user_id = str(uuid4())
        token = create_refresh_token(user_id=user_id, role="analyst")
        mock_user_row(mock_db, user_id, role="analyst", missing=True)

        response = await test_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    async def test_unknown_user_cannot_refresh(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_user_row
    ):
        from src.core.security import create_refresh_token

        token = create_refresh_token(user_id=str(uuid4()), role="analyst")
        mock_user_row(mock_db, str(uuid4()), missing=True)

        response = await test_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    async def test_demoted_role_takes_effect_on_refresh(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_user_row
    ):
        """The new access token must carry the role in the DB, not the token."""
        from src.core.security import create_refresh_token, decode_access_token

        user_id = str(uuid4())
        # The token still claims admin; the database says analyst.
        token = create_refresh_token(user_id=user_id, role="admin")
        mock_user_row(mock_db, user_id, role="analyst")

        response = await test_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        payload = decode_access_token(response.json()["access_token"])
        assert payload["role"] == "analyst", (
            "the access token must reflect the current database role"
        )

    async def test_malformed_sub_is_rejected(self, test_client: AsyncClient):
        """A `sub` that is not a UUID cannot belong to a real user."""
        from src.core.security import create_refresh_token

        token = create_refresh_token(user_id="not-a-uuid", role="admin")

        response = await test_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    async def test_refresh_issues_token_for_the_requested_user(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_user_row
    ):
        """The minted token must be bound to the user loaded from the DB."""
        from src.core.security import create_refresh_token, decode_access_token

        user_id = str(uuid4())
        token = create_refresh_token(user_id=user_id, role="analyst")
        mock_user_row(mock_db, user_id, role="analyst")

        response = await test_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert decode_access_token(response.json()["access_token"])["sub"] == user_id


class TestAuthLogout:
    """POST /api/v1/auth/logout endpoint."""

    async def test_logout_returns_204(
        self, test_client: AsyncClient, auth_headers: dict
    ):
        """Logout should return 204 No Content."""
        response = await test_client.post(
            "/api/v1/auth/logout",
            headers=auth_headers,
        )
        assert response.status_code == 204
