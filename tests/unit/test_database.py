"""Tests for async database engine and session."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.database import Base, async_session_maker, engine


def test_base_has_metadata():
    """Base should be a declarative base with metadata."""
    assert hasattr(Base, "metadata")
    assert Base.metadata is not None


def test_engine_is_async_engine():
    """Engine should be an AsyncEngine instance."""
    assert isinstance(engine, AsyncEngine)


def test_async_session_maker_is_async_sessionmaker():
    """Session maker should be an async_sessionmaker yielding AsyncSession."""
    assert isinstance(async_session_maker, async_sessionmaker)
    assert async_session_maker.class_ is AsyncSession


def test_database_url_uses_asyncpg():
    """Engine URL should use asyncpg driver."""
    assert engine.url.drivername == "postgresql+asyncpg"
