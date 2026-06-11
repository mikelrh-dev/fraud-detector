"""JWT token management and password hashing utilities."""

from datetime import datetime, timedelta, timezone
from typing import Any

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
    """Create a JWT access token with user_id and role claims."""
    delta = expires_delta or timedelta(minutes=settings.jwt_exp_minutes)
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Raises JWTError if the token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": True},
        )
        return payload
    except JWTError:
        raise


async def is_token_blacklisted(redis_client: Redis, jti: str) -> bool:
    """Check if a token has been blacklisted in Redis."""
    return await redis_client.exists(f"token_blacklist:{jti}") > 0


async def blacklist_token(redis_client: Redis, jti: str, ttl: int = 900) -> None:
    """Add a token to the Redis blacklist with a TTL matching token expiry."""
    await redis_client.setex(f"token_blacklist:{jti}", ttl, "1")
