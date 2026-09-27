"""Async database engine and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.core.config import settings

# A24: Redis is bounded (see core/redis.py: max_connections, socket timeouts)
# and Postgres was not, which is the wrong way round: Postgres is the one every
# request depends on. Without these, one pathological query holds its pooled
# connection forever, and SQLAlchemy's defaults (pool_size=5, max_overflow=10)
# mean 15 stuck requests exhaust the pool and the whole API stops serving.
#
# command_timeout is the load-bearing one: it is the asyncpg-level bound that
# turns "hangs forever" into "fails after 5s". statement_cache_size=0 avoids
# the prepared-statement invalidation class of bug behind PgBouncer/pgpool.
engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_size=10,
    max_overflow=20,
    # Seconds a caller waits for a free connection before erroring. Sheds load
    # loudly instead of queueing without bound.
    pool_timeout=10,
    # Recycle well under any typical idle_session_timeout / firewall idle cut.
    pool_recycle=1800,
    # Validate a pooled connection before handing it out. Without this, a
    # connection that died while idle (Postgres restart) surfaces as a 500 on
    # an unrelated query.
    pool_pre_ping=True,
    connect_args={
        "command_timeout": 5,
        "statement_cache_size": 0,
    },
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    )


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session for dependency injection."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
