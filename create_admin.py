"""Seed the demo admin account (admin@frauddetector.dev / admin123) for local development.

Matches the Demo Login button credentials on the LoginPage.
Idempotent: skips when the account already exists.
"""

import asyncio

from sqlalchemy import func, select

from src.core.database import async_session_maker
from src.core.security import hash_password
from src.models.user import User, UserRole

DEMO_EMAIL = "admin@frauddetector.dev"


async def create_admin() -> None:
    """Create the demo admin user if it does not already exist."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(func.lower(User.email) == DEMO_EMAIL)
        )
        if result.scalar_one_or_none() is not None:
            print("Demo admin already exists — skipping.")
            return

        admin = User(
            username="admin",
            email=DEMO_EMAIL,
            hashed_password=hash_password("admin123"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        print(f"Demo admin created: {admin.id} ({DEMO_EMAIL})")


if __name__ == "__main__":
    asyncio.run(create_admin())
