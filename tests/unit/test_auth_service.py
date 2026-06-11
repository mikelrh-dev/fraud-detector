"""Tests for the auth service (register, login, token management)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User, UserRole
from src.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from src.services.auth import AuthService, login, register_user


@pytest.fixture
def mock_db():
    """Mock async database session."""
    db = AsyncMock(spec=AsyncSession)
    return db


@pytest.fixture
def auth_service(mock_db):
    """AuthService instance with mocked dependencies."""
    return AuthService(db=mock_db)


# Module-level asyncio marker for all tests in this file
pytestmark = pytest.mark.asyncio


class TestAuthService:
    """Auth service unit tests."""

    async def test_register_user_creates_user(self, mock_db):
        """Register should create a user with hashed password."""
        # Mock the query result: scalar_one_or_none returns None (no existing user)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        request = RegisterRequest(
            username="new_analyst",
            email="analyst@example.com",
            password="secure_pass_123",
            role="analyst",
        )

        result = await register_user(mock_db, request)

        assert result.username == "new_analyst"
        assert result.email == "analyst@example.com"
        assert result.role == UserRole.ANALYST
        assert result.hashed_password != "secure_pass_123"  # Should be hashed
        assert mock_db.add.called
        assert mock_db.flush.called

    async def test_register_duplicate_email_raises(self, mock_db):
        """Register with existing email should raise conflict error."""
        existing_user = MagicMock(spec=User)
        existing_user.email = "analyst@example.com"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        request = RegisterRequest(
            username="new_analyst",
            email="analyst@example.com",
            password="secure_pass_123",
            role="analyst",
        )

        with pytest.raises(ValueError, match="already exists"):
            await register_user(mock_db, request)

    async def test_login_valid_credentials(self, mock_db):
        """Login with valid credentials should return tokens."""
        from src.core.security import hash_password

        hashed_pw = hash_password("secure_pass_123")
        user = MagicMock(spec=User)
        user.username = "analyst1"
        user.hashed_password = hashed_pw
        user.role = UserRole.ANALYST
        user.id = "test-uuid"
        user.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute = AsyncMock(return_value=mock_result)

        request = LoginRequest(username="analyst1", password="secure_pass_123")
        result = await login(mock_db, request)

        assert isinstance(result, TokenResponse)
        assert result.token_type == "bearer"
        assert result.access_token is not None
        assert result.refresh_token is not None

    async def test_login_invalid_password_raises(self, mock_db):
        """Login with wrong password should raise unauthorized."""
        from src.core.security import hash_password

        hashed_pw = hash_password("secure_pass_123")
        user = MagicMock(spec=User)
        user.username = "analyst1"
        user.hashed_password = hashed_pw
        user.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute = AsyncMock(return_value=mock_result)

        request = LoginRequest(username="analyst1", password="wrong_password")
        with pytest.raises(ValueError, match="Invalid credentials"):
            await login(mock_db, request)

    async def test_login_inactive_user_raises(self, mock_db):
        """Login with inactive user should raise unauthorized."""
        user = MagicMock(spec=User)
        user.username = "inactive_user"
        user.is_active = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute = AsyncMock(return_value=mock_result)

        request = LoginRequest(username="inactive_user", password="any_pass")
        with pytest.raises(ValueError, match="Invalid credentials"):
            await login(mock_db, request)

    async def test_login_user_not_found_raises(self, mock_db):
        """Login with non-existent username should raise unauthorized."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        request = LoginRequest(username="nonexistent", password="any_pass")
        with pytest.raises(ValueError, match="Invalid credentials"):
            await login(mock_db, request)
