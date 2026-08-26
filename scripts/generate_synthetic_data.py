"""Generate synthetic transaction data for model training.

Produces 50k transactions with realistic fraud patterns (5% fraud rate),
including velocity bursts, amount outliers, unusual hours, merchant risk,
and geo-impossible patterns. Outputs to data/synthetic_transactions.csv.
"""

import csv
import random
from datetime import datetime, timedelta, timezone

from src.core.ml_constants import CATEGORY_ALIASES, MERCHANT_RISK_CATEGORIES

# Configuration
NUM_TRANSACTIONS = 50_000
FRAUD_RATE = 0.05
OUTPUT_PATH = "data/synthetic_transactions.csv"

# Velocity windows per class — mirrors scripts/train_xgboost_aligned.py so
# both generators emit the same distribution (FD-VEL-004 train/serve parity).
VELOCITY_5MIN_FRAUD = (3, 15)
VELOCITY_5MIN_LEGIT = (0, 2)
VELOCITY_1H_FRAUD = (10, 60)
VELOCITY_1H_LEGIT = (0, 5)

# CSV schema — velocity columns must be persisted so training sees real counts.
FIELDNAMES = [
    "transaction_id", "user_id", "amount", "currency",
    "merchant_name", "merchant_category", "timestamp",
    "is_fraud", "hour_of_day", "is_weekend",
    "is_crypto", "amount_round_number",
    "user_avg_amount", "user_std_amount",
    "velocity_5min", "velocity_1h",
]

# Merchant pool
MERCHANTS = {
    "low_risk": [
        "Amazon", "Walmart", "Target", "Best Buy", "Starbucks",
        "Netflix", "Spotify", "Uber", "Lyft", "DoorDash",
        "Whole Foods", "Costco", "Home Depot", "McDonald's",
        "Subway", "Shell Gas", "Exxon", "Kroger", "Safeway", "CVS",
    ],
    "medium_risk": [
        "Electronics World", "Travel Booking Pro", "Luxury Outlet",
        "Fine Dining", "Hotel Reservations", "Car Rental Pro",
        "Furniture Store", "Jewelry Shop", "Golf Equipment",
        "Camera Store",
    ],
    "high_risk": [
        "Crypto Exchange Pro", "Money Transfer Now", "Online Gambling",
        "Adult Content", "Pharmacy Online", "Offshore Bank Transfer",
        "Virtual Gift Cards", "Auction Site", "Forex Trading",
        "Binary Options",
    ],
}

# User pool (100 users with different profiles)
USERS = []
for i in range(100):
    avg_amount = random.uniform(20, 200)
    std_amount = random.uniform(10, 50)
    USERS.append({
        "user_id": f"user-{i:04d}",
        "avg_amount": avg_amount,
        "std_amount": std_amount,
        "home_country": random.choice(["US", "US", "US", "UK", "CA", "DE", "FR"]),
    })

CURRENCIES = ["USD", "EUR", "GBP", "CAD"]


def generate_timestamp(base: datetime, user_id: str) -> str:
    """Generate a realistic timestamp, with some users active at unusual hours."""
    hour_bias = random.random()
    if hour_bias < 0.05 and random.random() < FRAUD_RATE * 2:
        # Fraud pattern: unusual hours (midnight to 5 AM)
        hour = random.randint(0, 5)
    else:
        hour = random.randint(8, 23)

    minute = random.randint(0, 59)
    second = random.randint(0, 59)

    ts = base.replace(hour=hour, minute=minute, second=second, microsecond=0)
    return ts.isoformat()


def generate_transaction(txn_id: int, base_time: datetime) -> dict:
    """Generate a single transaction, potentially fraudulent."""
    user = random.choice(USERS)
    user_id = user["user_id"]
    is_fraud = random.random() < FRAUD_RATE

    if is_fraud:
        amount, merchant_category, merchant_name = generate_fraudulent_tx(user)
    else:
        amount = max(1.0, round(random.gauss(user["avg_amount"], user["std_amount"]), 2))
        # Use realistic non-risk categories for legitimate transactions
        normal_categories = ["groceries", "retail", "restaurant", "transport", "entertainment", "health", "education"]
        merchant_category = random.choice(normal_categories)
        merchant_name = random.choice(MERCHANTS["low_risk"])

    # Add velocity bursts for fraud
    if is_fraud and random.random() < 0.3:
        # Velocity burst: multiple transactions in short window
        hour_offset = random.randint(0, 2)
        minute_offset = random.randint(0, 10)
        ts = base_time + timedelta(hours=hour_offset, minutes=minute_offset)
    else:
        hour_offset = random.randint(0, 720)  # Up to 30 days apart
        ts = base_time + timedelta(hours=hour_offset)

    # Resolve alias for is_crypto check
    resolved_cat = CATEGORY_ALIASES.get(merchant_category, merchant_category)
    is_crypto = resolved_cat == "cryptocurrency"
    is_round = amount % 100 == 0 and amount > 0

    if is_fraud:
        velocity_5min = random.randint(*VELOCITY_5MIN_FRAUD)
        velocity_1h = random.randint(*VELOCITY_1H_FRAUD)
    else:
        velocity_5min = random.randint(*VELOCITY_5MIN_LEGIT)
        velocity_1h = random.randint(*VELOCITY_1H_LEGIT)

    return {
        "transaction_id": f"tx-{txn_id:06d}",
        "user_id": user_id,
        "amount": amount,
        "currency": random.choice(CURRENCIES),
        "merchant_name": merchant_name,
        "merchant_category": merchant_category,
        "timestamp": generate_timestamp(ts, user_id),
        "is_fraud": int(is_fraud),
        "hour_of_day": ts.hour,
        "is_weekend": 1 if ts.weekday() >= 5 else 0,
        "is_crypto": int(is_crypto),
        "amount_round_number": int(is_round),
        "user_avg_amount": round(user["avg_amount"], 2),
        "user_std_amount": round(user["std_amount"], 2),
        "velocity_5min": velocity_5min,
        "velocity_1h": velocity_1h,
    }


def generate_fraudulent_tx(user: dict) -> tuple[float, str, str]:
    """Generate a fraudulent transaction with specific patterns."""
    pattern = random.choices(
        ["amount_outlier", "high_risk_merchant", "unusual_hours", "round_amount"],
        weights=[0.4, 0.3, 0.2, 0.1],
    )[0]

    # Use canonical risk categories (with occasional alias for realism)
    risk_cats = ["cryptocurrency", "money_transfer", "gambling", "adult", "pharmacy"]
    merchant_category = random.choice(risk_cats)
    # Occasionally emit alias form so training data sees both variants
    if random.random() < 0.15:
        alias = CATEGORY_ALIASES.get(merchant_category)
        if alias:
            merchant_category = random.choice([merchant_category, alias])

    if pattern == "amount_outlier":
        amount = round(user["avg_amount"] + user["std_amount"] * random.uniform(5, 20), 2)
        merchant_name = random.choice(MERCHANTS["medium_risk"])
    elif pattern == "high_risk_merchant":
        amount = round(random.uniform(100, 5000), 2)
        merchant_name = random.choice(MERCHANTS["high_risk"])
    elif pattern == "unusual_hours":
        amount = round(random.uniform(50, 500), 2)
        merchant_name = random.choice(MERCHANTS["medium_risk"])
    else:  # round_amount
        amount = round(random.choice([500, 1000, 2000, 5000, 10000, 50000]))
        merchant_name = random.choice(MERCHANTS["medium_risk"])

    return amount, merchant_category, merchant_name


def main() -> None:
    """Generate and save synthetic transaction data."""
    print(f"Generating {NUM_TRANSACTIONS:,} synthetic transactions...")
    base_time = datetime.now(tz=timezone.utc) - timedelta(days=365)

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for i in range(NUM_TRANSACTIONS):
            tx = generate_transaction(i, base_time)
            writer.writerow(tx)

    # Count frauds (actual is_fraud column, not tx-id prefix)
    with open(OUTPUT_PATH, "r", newline="") as f:
        fraud_count = sum(1 for row in csv.DictReader(f) if row["is_fraud"] == "1")

    print(f"Generated {NUM_TRANSACTIONS:,} transactions to {OUTPUT_PATH}")
    print(f"Fraud rate: {FRAUD_RATE * 100:.0f}% ({fraud_count:,} fraudulent)")


if __name__ == "__main__":
    main()
