"""Authentication endpoints — register, login, refresh, logout."""

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.rate_limit import check_rate_limit
from src.core.dependencies import get_current_user, get_db, get_redis
from src.core.security import (
    blacklist_token,
    consume_token_once,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)
from src.models.user import User
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
    _rate_limit: None = Depends(check_rate_limit),
) -> TokenResponse:
    """Refresh an access token using a refresh token.

    The refresh token is passed in the Authorization header.
    A new access token and a rotated refresh token are returned.
    The consumed refresh token is blacklisted so it cannot be replayed
    (rotation semantics, R1-002/R1-004).

    A1: this endpoint used to trust the token for everything. It took ``sub``
    and ``role`` straight from the JWT and minted a new pair without touching
    the database, so deactivating an account, soft-deleting it or demoting an
    admin changed nothing: a refresh token issued before the change kept
    minting access tokens for up to 24 hours. The user row is now read, the
    account must exist, not be soft-deleted and be active, and the new token
    carries the role currently stored in the database rather than the one
    baked into the token.

    The read is here and not in ``get_current_user`` on purpose. Adding it to
    every authenticated request would couple the whole API to Postgres: a
    database blip would turn into a total outage and a per-request query.
    Reading only on refresh bounds the exposure window to the 15-minute
    access token instead of the 24-hour refresh token, at zero cost per
    request.
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

    # A1: the token is a claim, not proof the account still exists.
    try:
        user_uuid = uuid.UUID(user_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc

    result = await db.execute(
        select(User).where(User.id == user_uuid, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        # Deliberately not claiming the token: rejecting is enough to stop it,
        # and burning it would lock out a user that an admin re-activates.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive or no longer exists",
        )

    # A2: claim the token atomically. This replaces the old
    # is_token_blacklisted() + blacklist_token() pair, which were two awaits
    # with an event-loop yield between them, so N concurrent replays all saw
    # "not blacklisted" and all minted a fresh pair.
    #
    # The claim is placed here, after the database validation, so a token that
    # would be rejected anyway is never consumed: an inactive account that is
    # re-activated still has a working token, and a burst of requests against a
    # revoked account does not race to burn it before the reason is known.
    try:
        exp = int(payload.get("exp", 0))
        ttl = max(exp - int(time.time()), 60)
    except (TypeError, ValueError):
        ttl = 60

    if not await consume_token_once(redis_client, payload["jti"], ttl):
        # Someone else already consumed this exact token. That is either a
        # replay or a legitimate concurrent refresh; either way only one pair
        # may be issued, and the loser must not receive one.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Mint from the role currently in the database, not the one in the token, so
    # a demotion takes effect on the next refresh.
    role = user.role.value if hasattr(user.role, "value") else user.role

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
    _rate_limit: None = Depends(check_rate_limit),
) -> None:
    """Logout and blacklist the current access token.

    Optionally also revokes the refresh token if provided via the
    ``X-Refresh-Token`` header.  Clients that don't send it still get
    a successful 204 (graceful degradation).
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ")

    try:
        payload = decode_access_token(token)
        jti = payload[
            "jti"
        ]  # always present since R1-002; missing jti is rejected by get_current_user anyway
        exp = payload.get("exp", 900)
        ttl = max(exp - int(time.time()), 60)
        await blacklist_token(redis_client, jti, ttl)
    except Exception:
        logger.warning("Best-effort token blacklisting failed on logout")

    # F4: Also revoke the refresh token if provided.
    refresh_token = request.headers.get("X-Refresh-Token")
    if refresh_token:
        try:
            refresh_payload = decode_refresh_token(refresh_token)
            if refresh_payload.get("typ") == "refresh":
                refresh_jti = refresh_payload["jti"]
                # Refresh tokens live 24h; use remaining TTL or 86400s.
                try:
                    refresh_exp = int(refresh_payload.get("exp", 0))
                    refresh_ttl = max(refresh_exp - int(time.time()), 60)
                except (TypeError, ValueError):
                    refresh_ttl = 86400
                await blacklist_token(redis_client, refresh_jti, refresh_ttl)
        except Exception:
            logger.warning("Best-effort refresh token blacklisting failed on logout")
