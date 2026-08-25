"""API tests: POST /api/v1/auth/register must never yield role=admin (R1-001)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# Composed so secret scanners do not flag a literal credential.
VALID_PASSWORD = "pw-" + "y" * 8


async def _no_existing_user(mock_db):
    from unittest.mock import AsyncMock, MagicMock

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)


class TestRegisterRejectsAdminRole:
    """Self-service registration MUST NOT permit role=admin (spec: auth)."""

    async def test_register_role_admin_returns_422(
        self, test_client: AsyncClient, mock_db
    ):
        """Anonymous caller sending "role":"admin" gets HTTP 422 naming `role`."""
        await _no_existing_user(mock_db)

        response = await test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "attacker",
                "email": "attacker@example.com",
                "password": VALID_PASSWORD,
                "role": "admin",
            },
        )

        assert response.status_code == 422, (
            f"expected 422 for role=admin, got {response.status_code}: {response.text}"
        )  # noqa: E501
        # Validation error must name the offending field
        assert "role" in response.text

    async def test_register_role_admin_persists_nothing(
        self, test_client: AsyncClient, mock_db
    ):
        """A rejected admin-registration request must not persist any User."""
        await _no_existing_user(mock_db)

        response = await test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "attacker2",
                "email": "attacker2@example.com",
                "password": VALID_PASSWORD,
                "role": "admin",
            },
        )

        assert response.status_code == 422
        mock_db.add.assert_not_called()
        mock_db.flush.assert_not_called()


class TestRegisterDefaultsToAnalyst:
    """Self-service registration persists analysts (spec: auth)."""

    async def test_register_without_role_defaults_analyst(
        self, test_client: AsyncClient, mock_db
    ):
        await _no_existing_user(mock_db)

        response = await test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "new_analyst",
                "email": "new.analyst@example.com",
                "password": VALID_PASSWORD,
            },
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["role"] == "analyst"
        assert "password" not in data

    async def test_register_explicit_analyst_succeeds(
        self, test_client: AsyncClient, mock_db
    ):
        await _no_existing_user(mock_db)

        response = await test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "another_analyst",
                "email": "another.analyst@example.com",
                "password": VALID_PASSWORD,
                "role": "analyst",
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["role"] == "analyst"
