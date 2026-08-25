"""Shared pytest fixtures for all test modules."""

from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.main import app
from src.core.dependencies import get_db, get_redis, get_velocity_store
from src.core.security import create_access_token, hash_password
from src.models.user import User, UserRole
from src.services.velocity_store import VelocityStore


@pytest.fixture
def mock_db() -> AsyncMock:
    """Provide a mock async database session.

    Usage in tests::
        mock_db.execute = AsyncMock(return_value=MagicMock())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
    """
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Provide a mock Redis client with velocity ZSET methods.

    ``pipeline()`` returns a mock pipeline whose ``execute`` defaults to
    ``[0, 0, 0]`` (trim ok, zero 5min counts, zero 1h counts) so the
    velocity path is inert unless a test seeds it.

    ``incr()`` behaves like real Redis: increments and returns the new
    count per key, so the rate limiter tests work correctly.
    """
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=0)
    redis.setex = AsyncMock()

    # Simulate real Redis INCR: per-key counter that increments on each call.
    _incr_counters: dict[str, int] = defaultdict(int)

    async def _fake_incr(key: str) -> int:
        _incr_counters[key] += 1
        return _incr_counters[key]

    redis.incr = AsyncMock(side_effect=_fake_incr)
    redis.zadd = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.zremrangebyscore = AsyncMock(return_value=0)
    redis.zcount = AsyncMock(return_value=0)

    pipe = MagicMock()
    pipe.zadd = MagicMock(return_value=1)
    pipe.expire = MagicMock(return_value=True)
    pipe.zremrangebyscore = MagicMock(return_value=0)
    pipe.zcount = MagicMock(return_value=0)
    pipe.execute = AsyncMock(return_value=[0, 0, 0])
    redis.pipeline = MagicMock(return_value=pipe)

    return redis


@pytest.fixture
def test_user_factory() -> MagicMock:
    """Create a mock User with default analyst role."""

    def _create_user(role: str = "analyst", is_active: bool = True) -> MagicMock:
        user = MagicMock(spec=User)
        user.id = "00000000-0000-0000-0000-000000000001"
        user.username = "test_analyst"
        user.email = "analyst@example.com"
        user.hashed_password = hash_password("test_password_123")
        user.role = UserRole(role)
        user.is_active = is_active
        return user

    return _create_user


@pytest.fixture
def auth_headers(test_user_factory) -> dict[str, str]:
    """Generate Authorization headers with a valid JWT."""
    user = test_user_factory()
    token = create_access_token(user_id=str(user.id), role=user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """Generate Authorization headers with admin JWT."""
    token = create_access_token(
        user_id="admin-uuid",
        role="admin",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_client(mock_db, mock_redis) -> AsyncClient:
    """Provide an async test client with mocked dependencies."""

    async def _override_get_db():
        yield mock_db

    async def _override_get_redis():
        yield mock_redis

    def _override_get_velocity_store():
        return VelocityStore(redis=mock_redis)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis
    app.dependency_overrides[get_velocity_store] = _override_get_velocity_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
