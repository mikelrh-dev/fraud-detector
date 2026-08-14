#!/usr/bin/env python
"""Generate synthetic transactions for testing."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import random
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import text, create_engine

from src.core.config import settings

async def generate_transactions():
    """Generate 100 synthetic transactions."""
    db_url = settings.database_url.replace("+asyncpg", "+psycopg2")
    engine = create_engine(db_url)
    
    merchants = [
        "Amazon", "Spotify", "Netflix", "Uber", "Airbnb",
        "CryptoBuy", "BitExchange", "Binance", "Coinbase",
        "Starbucks", "McDonald's", "Shell", "ExxonMobil",
        "Walmart", "Target", "Best Buy", "Apple Store"
    ]
    
    categories = [
        "ecommerce", "streaming", "transport", "accommodation",
        "crypto", "gas", "food", "retail", "tech"
    ]
    
    # Get the admin user ID
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id FROM users LIMIT 1"))
        user_id = result.scalar()
    
    if not user_id:
        print("❌ No users found. Please create a user first.")
        engine.dispose()
        return
    
    print(f"Generating 100 synthetic transactions for user {user_id}...")
    
    with engine.connect() as conn:
        for i in range(100):
            tx_id = str(uuid4())
            amount = round(random.uniform(10, 5000), 2)
            merchant = random.choice(merchants)
            category = random.choice(categories)
            card_last4 = str(random.randint(1000, 9999))
            status = "completed"
            
            created_at = datetime.utcnow() - timedelta(days=random.randint(0, 30))
            
            sql = text("""
                INSERT INTO transactions (
                    id, amount, currency, merchant_name, merchant_category, card_last4,
                    status, user_id, created_at, updated_at
                ) VALUES (
                    :id, :amount, 'USD', :merchant, :category, :card_last4,
                    :status, :user_id, :created_at, :updated_at
                )
            """)
            
            conn.execute(sql, {
                "id": tx_id,
                "amount": amount,
                "merchant": merchant,
                "category": category,
                "card_last4": card_last4,
                "status": status,
                "user_id": user_id,
                "created_at": created_at,
                "updated_at": created_at,
            })
            
            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/100 transactions inserted...")
        
        conn.commit()
    
    print("✓ 100 synthetic transactions generated successfully")
    engine.dispose()

if __name__ == "__main__":
    asyncio.run(generate_transactions())
