"""Database initialization script — creates all tables."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from sqlalchemy import create_engine
from src.models.base import Base
from src.models import (
    User, Transaction, FraudScore, FraudAlert,
    RuleMetadata, LLMReport, MLModelRun, AuditEntry
)
from src.core.config import settings


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
