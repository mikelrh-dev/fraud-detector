"""Database initialization script — creates all tables."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine

from src.core.config import settings

# noqa comment below is deliberate: these imports look unused to ruff and to a
# reader, but they are what registers every table on Base.metadata for
# create_all(). Dropping them would not raise — Base.metadata would simply be
# missing tables and this script would print success having created almost
# nothing. They are kept explicit so schema creation does not depend on
# src/models/__init__.py happening to re-export every model.
from src.models import (  # noqa: F401
    AuditEntry,
    FraudAlert,
    FraudScore,
    LLMReport,
    MLModelRun,
    RuleMetadata,
    ShapAttribution,
    Transaction,
    User,
)
from src.models.base import Base


def init_db():
    """Create all database tables."""
    # Use synchronous connection for initialization
    db_url = settings.database_url.replace("+asyncpg", "+psycopg2")
    engine = create_engine(db_url)
    
    print("Creating database tables...")
    Base.metadata.create_all(engine)
    print("✓ All tables created successfully")
    
    engine.dispose()


if __name__ == "__main__":
    init_db()
