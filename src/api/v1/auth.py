"""Authentication endpoints — register, login, refresh, logout."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.v1.rate_limit import check_rate_limit
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db, get_redis
from src.core.security import blacklist_token, create_access_token, decode_access_token
from src.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from src.services.auth import login, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_endpoint(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> UserResponse:
    """Register a new user (admin only)."""
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create users",
        )
    try:
        user = await register_user(db, request)
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.post("/login", response_model=TokenResponse)
async def login_endpoint(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(check_rate_limit),
) -> TokenResponse:
    """Authenticate and return JWT tokens."""
    try:
        result = await login(db, request)
        return result
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Refresh an access token using a refresh token.

    The refresh token is passed in the Authorization header.
    A new access token and a rotated refresh token are returned.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    refresh_token = auth_header.removeprefix("Bearer ")
    try:
        payload = decode_access_token(refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload["sub"]
    role = payload["role"]

    # Issue new tokens
    new_access = create_access_token(user_id=user_id, role=role)
    new_refresh = create_access_token(user_id=user_id, role=role)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
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
        jti = payload.get("jti", token)
        exp = payload.get("exp", 900)
        ttl = max(exp - int(__import__("time").time()), 60)
        await blacklist_token(redis_client, jti, ttl)
    except Exception:
        pass  # Best-effort blacklisting
