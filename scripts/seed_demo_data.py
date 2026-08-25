#!/usr/bin/env python
"""Seed demo data for fraud-detector.

Creates the well-known demo accounts (used by the frontend's demo login
button) plus a handful of realistic transactions so a fresh clone has a
populated dashboard.

Usage:
    python scripts/seed_demo_data.py

Requires a running PostgreSQL with the schema applied
(`alembic upgrade head`). Idempotent: existing users/transactions are
skipped.
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.core.database import async_session_maker
from src.core.security import hash_password
from src.models.transaction import Transaction, TransactionStatus
from src.models.user import User, UserRole

DEMO_ADMIN_EMAIL = "admin@frauddetector.dev"
DEMO_ADMIN_PASSWORD = "admin123"
DEMO_ANALYST_EMAIL = "analyst@frauddetector.dev"
DEMO_ANALYST_PASSWORD = "analyst123"

# (merchant, category, amount, card_last4, hours_ago)
ANALYST_TRANSACTIONS = [
    ("Amazon", "ecommerce", "84.99", "4242", 2),
    ("Walmart Supercenter", "grocery", "152.30", "4242", 26),
    ("Shell Gas Station", "fuel", "45.00", "4242", 50),
    ("NETFLIX.COM", "subscription", "15.99", "4242", 74),
    ("Starbucks", "restaurant", "6.75", "4242", 96),
    ("MERCAD0 LIBRE SHOP", "ecommerce", "1899.00", "4242", 5),
    ("Amazon", "ecommerce", "62.40", "4242", 120),
    ("McDonald's", "restaurant", "12.50", "4242", 144),
    ("CRYPT0 EXCHANGE PRO", "crypto", "2500.00", "4242", 8),
    ("Local Bookstore", "retail", "32.90", "4242", 168),
]

ADMIN_TRANSACTIONS = [
    ("Stripe Payout", "finance", "5000.00", "9999", 3),
    ("Google Ads", "advertising", "320.00", "9999", 30),
]


async def _get_or_create_user(
    db, email: str, username: str, password: str, role: UserRole
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        print(f"  = user {email} already exists, skipping")
        return user

    user = User(
        id=uuid4(),
        username=username,
        email=email,
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    print(f"  + created user {email} ({role.value})")
    return user


async def _seed_transactions(db, user: User, specs) -> int:
    result = await db.execute(
        select(Transaction.id).where(Transaction.user_id == user.id).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        print(f"  = transactions for {user.email} already seeded, skipping")
        return 0

    now = datetime.now(tz=timezone.utc)
    for merchant, category, amount, last4, hours_ago in specs:
        db.add(
            Transaction(
                id=uuid4(),
                user_id=user.id,
                amount=Decimal(amount),
                currency="USD",
                merchant_name=merchant,
                merchant_category=category,
                card_last4=last4,
                status=TransactionStatus.APPROVED,
                created_at=now - timedelta(hours=hours_ago),
                updated_at=now - timedelta(hours=hours_ago),
            )
        )
    print(f"  + {len(specs)} transactions for {user.email}")
    return len(specs)


async def main() -> None:
    print("Seeding demo data...")
    async with async_session_maker() as db:
        admin = await _get_or_create_user(
            db, DEMO_ADMIN_EMAIL, "admin", DEMO_ADMIN_PASSWORD, UserRole.ADMIN
        )
        analyst = await _get_or_create_user(
            db, DEMO_ANALYST_EMAIL, "analyst", DEMO_ANALYST_PASSWORD, UserRole.ANALYST
        )

        total = 0
        total += await _seed_transactions(db, admin, ADMIN_TRANSACTIONS)
        total += await _seed_transactions(db, analyst, ANALYST_TRANSACTIONS)

        await db.commit()
        print(f"Done. {total} transactions inserted.")
        print()
        print("Demo credentials:")
        print(f"  Admin   : {DEMO_ADMIN_EMAIL} / {DEMO_ADMIN_PASSWORD}")
        print(f"  Analyst : {DEMO_ANALYST_EMAIL} / {DEMO_ANALYST_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
