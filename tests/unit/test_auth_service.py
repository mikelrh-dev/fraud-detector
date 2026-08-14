"""Tests for the auth service (register, login, token management)."""

from unittest.mock import AsyncMock, MagicMock

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

    @staticmethod
    def _seed_admin_user(mock_db: AsyncMock) -> None:
        """Seed mock_db so the seeded admin (admin@fraud.local / admin123) is found."""
        from src.core.security import hash_password

        mock_result = MagicMock()
        admin = MagicMock(spec=User)
        admin.id = "admin-uuid"
        admin.username = "admin"
        admin.email = "admin@fraud.local"
        admin.hashed_password = hash_password("admin123")
        admin.role = UserRole.ADMIN
        admin.is_active = True
        mock_result.scalar_one_or_none.return_value = admin
        mock_db.execute = AsyncMock(return_value=mock_result)

    async def test_login_by_email_returns_access_and_refresh_tokens(self, mock_db, auth_service):
        """auth_service.login with a valid email + password should return both tokens.

        Once the service migrates to email login, calling
        auth_service.login(LoginRequest(email="admin@fraud.local", password="admin123"))
        must return a TokenResponse with non-empty access_token and refresh_token
        and token_type "bearer".
        """
        self._seed_admin_user(mock_db)

        result = await auth_service.login(
            LoginRequest(email="admin@fraud.local", password="admin123")
        )

        assert result.token_type == "bearer"
        assert result.access_token, "login must return a non-empty access token"
        assert result.refresh_token, "login must return a non-empty refresh token"

    async def test_login_email_case_insensitive(self, mock_db, auth_service):
        """Email lookup must be case-insensitive: ADMIN@FRAUD.LOCAL matches the stored email.

        auth_service.login(LoginRequest(email="ADMIN@FRAUD.LOCAL", password="admin123"))
        must return the same tokens as the lowercase email.
        """
        self._seed_admin_user(mock_db)

        result = await auth_service.login(
            LoginRequest(email="ADMIN@FRAUD.LOCAL", password="admin123")
        )

        assert result.token_type == "bearer"
        assert result.access_token, "login must return a non-empty access token"
        assert result.refresh_token, "login must return a non-empty refresh token"

    async def test_login_wrong_password_raises_credential_error(self, mock_db, auth_service):
        """Login with a wrong password must raise CredentialError, not ValueError.

        The service should surface a dedicated CredentialError for invalid
        credentials so the API layer maps it to 401 without leaking whether the
        email exists.
        """
        from src.services.auth import CredentialError

        self._seed_admin_user(mock_db)

        with pytest.raises(CredentialError, match="Invalid credentials"):
            await auth_service.login(
                LoginRequest(email="admin@fraud.local", password="wrong_password")
            )
