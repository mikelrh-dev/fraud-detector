"""FastAPI dependency injection for database, Redis, and auth."""

from collections.abc import AsyncGenerator, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_maker
from src.core.redis import get_redis as _get_redis
from src.core.security import decode_access_token, is_token_blacklisted
from src.services.velocity_store import VelocityStore

_security_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_redis() -> AsyncGenerator[Redis, None]:
    """Provide a Redis client from the shared pool."""
    yield _get_redis()


def get_velocity_store() -> VelocityStore:
    """Provide a VelocityStore bound to the shared Redis connection pool."""
    return VelocityStore()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security_scheme),
    redis_client: Redis = Depends(get_redis),
) -> dict:
    """Extract and validate the current user from the JWT in the Authorization header.

    Also enforces token revocation: a JTI present in the Redis blacklist
    (written on logout) is rejected (R1-002).

    Returns a dict with user_id and role on success.
    Raises HTTPException 401 if the token is missing, invalid, expired,
    or revoked.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    jti = payload.get("jti")
    if jti is None:
        # Tokens without a JTI cannot be revoked; refuse them outright.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if await is_token_blacklisted(redis_client, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"user_id": payload["sub"], "role": payload["role"]}


def require_role(required_role: str) -> Callable[[dict], dict]:
    """Return a dependency that checks the user has the required role."""

    def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required",
            )
        return current_user

    return role_checker


def require_any_role(*allowed_roles: str) -> Callable[[dict], dict]:
    """Return a dependency that accepts any one of ``allowed_roles``.

    ``require_role`` is exact equality, so an admin was rejected by endpoints
    that only meant "not a guest" (e.g. ``require_role("analyst")``). Use this
    when the intent is a set of acceptable roles.
    """
    if not allowed_roles:
        raise ValueError("require_any_role() needs at least one role")

    def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role " + " or ".join(f"'{r}'" for r in allowed_roles) + " required",
            )
        return current_user

    return role_checker
