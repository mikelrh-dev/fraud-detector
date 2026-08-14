from sqlalchemy import text, create_engine
from src.core.config import settings
from src.core.security import hash_password

db_url = settings.database_url.replace("+asyncpg", "+psycopg2")
engine = create_engine(db_url)

hashed = hash_password("admin123")
print(f"Hash: {hashed}")

with engine.connect() as conn:
    conn.execute(text("DELETE FROM users WHERE username = 'admin';"))
    conn.execute(text("""
        INSERT INTO users (id, username, email, hashed_password, role, is_active, created_at, updated_at)
        VALUES ('12345678-1234-1234-1234-123456789012', 'admin', 'admin@frauddetector.dev', :hash, 'admin', true, NOW(), NOW());
    """), {"hash": hashed})
    conn.commit()
    print("✓ User created successfully")
