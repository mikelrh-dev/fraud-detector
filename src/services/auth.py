"""Authentication service — registration, login, token management."""

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from src.models.user import User, UserRole
from src.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)


class CredentialError(Exception):
    """Raised when login credentials are invalid."""

    pass


class AuthService:
    """Authentication business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def login(self, request: LoginRequest) -> TokenResponse:
        """Authenticate a user via email and return JWT tokens.

        Raises CredentialError if credentials are invalid.
        """
        return await login(self.db, request)


async def register_user(db: AsyncSession, request: RegisterRequest) -> User:
    """Register a new user. Raises ValueError if email already exists.
    
    Email is stored in lowercase to ensure case-insensitive uniqueness.
    """
    email_lower = request.email.lower()
    # Check for existing user by email (case-insensitive)
    result = await db.execute(
        select(User).where(func.lower(User.email) == email_lower)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise ValueError("Email ya registrado")  # Generic, no email echo

    user = User(
        id=uuid4(),
        username=request.username,
        email=email_lower,
        hashed_password=hash_password(request.password),
        role=UserRole(request.role),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def login(db: AsyncSession, request: LoginRequest) -> TokenResponse:
    """Authenticate a user and return JWT tokens.

    Login is now email-based (case-insensitive). 
    Raises CredentialError if credentials are invalid.
    """
    email_lower = request.email.lower()
    result = await db.execute(
        select(User).where(func.lower(User.email) == email_lower)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise CredentialError("Invalid credentials")

    if not verify_password(request.password, user.hashed_password):
        raise CredentialError("Invalid credentials")

    # Handle both enum and string cases for role
    role_value = user.role.value if hasattr(user.role, 'value') else user.role

    access_token = create_access_token(
        user_id=str(user.id),
        role=role_value,
    )
    refresh_token = create_access_token(
        user_id=str(user.id),
        role=role_value,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
