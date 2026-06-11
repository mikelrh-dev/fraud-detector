"""Authentication service — registration, login, token management."""

from uuid import uuid4

from sqlalchemy import select
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


class AuthService:
    """Authentication business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db


async def register_user(db: AsyncSession, request: RegisterRequest) -> User:
    """Register a new user. Raises ValueError if email already exists."""
    # Check for existing user by email
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise ValueError(f"User with email '{request.email}' already exists")

    user = User(
        id=uuid4(),
        username=request.username,
        email=request.email,
        hashed_password=hash_password(request.password),
        role=UserRole(request.role),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def login(db: AsyncSession, request: LoginRequest) -> TokenResponse:
    """Authenticate a user and return JWT tokens.

    Raises ValueError if credentials are invalid.
    """
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise ValueError("Invalid credentials")

    if not verify_password(request.password, user.hashed_password):
        raise ValueError("Invalid credentials")

    access_token = create_access_token(
        user_id=str(user.id),
        role=user.role.value,
    )
    refresh_token = create_access_token(
        user_id=str(user.id),
        role=user.role.value,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
