"""FastAPI dependency injection for database, Redis, and auth."""

from collections.abc import AsyncGenerator, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_maker
from src.core.redis import get_redis as _get_redis
from src.core.security import decode_access_token

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


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security_scheme),
) -> dict:
    """Extract and validate the current user from the JWT in the Authorization header.

    Returns a dict with user_id and role on success.
    Raises HTTPException 401 if the token is missing, invalid, or expired.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
        return {"user_id": payload["sub"], "role": payload["role"]}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
