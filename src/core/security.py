"""JWT token management and password hashing utilities."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt  # type: ignore[import-untyped]
from passlib.context import CryptContext  # type: ignore[import-untyped]
from redis.asyncio import Redis

from src.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    user_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token with user_id, role, and typ claims."""
    delta = expires_delta or timedelta(minutes=settings.jwt_exp_minutes)
    return _encode_token(user_id=user_id, role=role, typ="access", delta=delta)


def create_refresh_token(
    user_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token (typ='refresh') with a longer lifetime.

    A refresh token is only valid at /auth/refresh; it is rejected as an
    access token everywhere else (R1-004).
    """
    delta = expires_delta or timedelta(minutes=settings.jwt_refresh_exp_minutes)
    return _encode_token(user_id=user_id, role=role, typ="refresh", delta=delta)


def _encode_token(user_id: str, role: str, typ: str, delta: timedelta) -> str:
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "typ": typ,
        # Unique token ID: enables real revocation (R1-002) and makes
        # refresh rotation meaningful even within the same second.
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + delta,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def _decode_token(token: str, expected_typ: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": True},
        )
    except JWTError:
        raise
    if payload.get("typ") != expected_typ:
        raise JWTError(f"Invalid token type: expected {expected_typ}")
    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token.

    Raises JWTError if the token is invalid, expired, or not an access token.
    """
    return _decode_token(token, expected_typ="access")


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a refresh token.

    Raises JWTError if the token is invalid, expired, or not a refresh token.
    """
    return _decode_token(token, expected_typ="refresh")


async def is_token_blacklisted(redis_client: Redis, jti: str) -> bool:
    """Check if a token has been blacklisted in Redis."""
    return await redis_client.exists(f"token_blacklist:{jti}") > 0


async def blacklist_token(redis_client: Redis, jti: str, ttl: int = 900) -> None:
    """Add a token to the Redis blacklist with a TTL matching token expiry."""
    await redis_client.setex(f"token_blacklist:{jti}", ttl, "1")
