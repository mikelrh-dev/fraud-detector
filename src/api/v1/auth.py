"""Authentication endpoints — register, login, refresh, logout."""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.rate_limit import check_rate_limit
from src.core.dependencies import get_current_user, get_db, get_redis
from src.core.security import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    is_token_blacklisted,
)
from src.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from src.services.auth import AuthService, CredentialError, register_user

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register_endpoint(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(check_rate_limit),
) -> UserResponse:
    """Register a new user (public registration)."""
    try:
        user = await register_user(db, request)
        # Handle both enum and string cases for role
        role_value = user.role.value if hasattr(user.role, "value") else user.role
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=role_value,
            is_active=user.is_active,
            created_at=user.created_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e


@router.post("/login", response_model=TokenResponse)
async def login_endpoint(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(check_rate_limit),
) -> TokenResponse:
    """Authenticate and return JWT tokens.

    Login is now email-based (case-insensitive).
    """
    try:
        auth_service = AuthService(db)
        result = await auth_service.login(request)
        return result
    except CredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from exc


@router.post("/refresh", response_model=TokenResponse)
async def refresh_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> TokenResponse:
    """Refresh an access token using a refresh token.

    The refresh token is passed in the Authorization header.
    A new access token and a rotated refresh token are returned.
    The consumed refresh token is blacklisted so it cannot be replayed
    (rotation semantics, R1-002/R1-004).
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    refresh_token = auth_header.removeprefix("Bearer ")
    try:
        payload = decode_refresh_token(refresh_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc

    user_id = payload["sub"]
    role = payload["role"]

    # A replayed (already-consumed) refresh token must be refused.
    if await is_token_blacklisted(redis_client, payload["jti"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Revoke the consumed refresh token for its remaining lifetime.
    try:
        exp = int(payload.get("exp", 0))
        ttl = max(exp - int(time.time()), 60)
    except (TypeError, ValueError):
        ttl = 60
    await blacklist_token(redis_client, payload["jti"], ttl)

    # Issue new tokens (rotated pair)
    new_access = create_access_token(user_id=user_id, role=role)
    new_refresh = create_refresh_token(user_id=user_id, role=role)

    bearer = "bearer"
    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type=bearer,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
    redis_client: Redis = Depends(get_redis),
) -> None:
    """Logout and blacklist the current access token."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ")

    try:
        payload = decode_access_token(token)
        jti = payload["jti"]  # always present since R1-002; missing jti is rejected by get_current_user anyway
        exp = payload.get("exp", 900)
        ttl = max(exp - int(time.time()), 60)
        await blacklist_token(redis_client, jti, ttl)
    except Exception:
        logger.warning("Best-effort token blacklisting failed on logout")
