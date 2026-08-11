"""
Genera transacciones sintéticas para entrenar el modelo ML.
Las transacciones "normales" siguen patrones típicos de consumo.
Las "anómalas" introducen desvíos (montos altos, horarios raros, merchants de riesgo, etc.)
"""
import csv
import random
from datetime import datetime, timedelta

random.seed(42)

MERCHANTS_NORMALES = [
    "Supermercado Centro", "Farmacia Lopez", "McDonalds",
    "Starbucks", "Netflix", "Spotify", "Disney+",
    "Coto Digital", "Mercado Libre", "Pedidos Ya",
    "YPF", "Shell", "Carrefour", "Easy",
]

MERCHANTS_RIESGO = [
    "Crypto Exchange Pro", "Online Gambling", "Money Transfer Now",
    "Casino Royal", "Dark Web Market",
]

CATEGORIAS = {
    "Supermercado Centro": "groceries", "Farmacia Lopez": "health",
    "McDonalds": "food", "Starbucks": "food",
    "Netflix": "entertainment", "Spotify": "entertainment",
    "Disney+": "entertainment", "Coto Digital": "groceries",
    "Mercado Libre": "shopping", "Pedidos Ya": "food",
    "YPF": "transport", "Shell": "transport",
    "Carrefour": "groceries", "Easy": "home",
    "Crypto Exchange Pro": "cryptocurrency",
    "Online Gambling": "gambling",
    "Money Transfer Now": "money_transfer",
    "Casino Royal": "gambling",
    "Dark Web Market": "other",
}


def generar_usuario(seed_base: int) -> dict:
    rng = random.Random(seed_base)
    return {
        "user_id": f"user_{seed_base:04d}",
        "avg_amount": rng.uniform(20, 200),
        "std_amount": rng.uniform(10, 80),
        "typical_hour_start": rng.randint(8, 14),
        "typical_hour_end": rng.randint(16, 22),
        "typical_merchants": rng.sample(MERCHANTS_NORMALES, 5),
        "is_weekend_shopper": rng.random() < 0.3,
    }


def generar_transaccion_normal(usuario: dict, rng: random.Random) -> dict:
    merchant = rng.choice(usuario["typical_merchants"])
    amount = round(abs(rng.gauss(usuario["avg_amount"], usuario["std_amount"])), 2)
    amount = max(1.0, amount)

    hour = rng.randint(usuario["typical_hour_start"], usuario["typical_hour_end"])
    day = rng.randint(0, 4)  # L-V
    if usuario["is_weekend_shopper"] and rng.random() < 0.3:
        day = rng.randint(5, 6)

    timestamp = datetime(2025, 1, 1) + timedelta(
        days=day, hours=hour, minutes=rng.randint(0, 59)
    )

    return {
        "user_id": usuario["user_id"],
        "amount": amount,
        "currency": "ARS",
        "merchant_name": merchant,
        "merchant_category": CATEGORIAS[merchant],
        "card_last4": f"{rng.randint(1000, 9999)}",
        "timestamp": timestamp.isoformat(),
    }


def generar_transaccion_anomala(usuario: dict, rng: random.Random) -> dict:
    anomaly_type = rng.choice([
        "high_amount", "unusual_hour", "risk_merchant", "round_amount"
    ])

    merchant = rng.choice(usuario["typical_merchants"])
    category = CATEGORIAS[merchant]
    amount = round(abs(rng.gauss(usuario["avg_amount"], usuario["std_amount"])), 2)
    hour = rng.randint(usuario["typical_hour_start"], usuario["typical_hour_end"])
    day = rng.randint(0, 6)

    if anomaly_type == "high_amount":
        amount = round(usuario["avg_amount"] * rng.uniform(5, 20), 2)
    elif anomaly_type == "unusual_hour":
        hour = rng.choice([1, 2, 3, 4, 22, 23])
    elif anomaly_type == "risk_merchant":
        merchant = rng.choice(MERCHANTS_RIESGO)
        category = CATEGORIAS[merchant]
    elif anomaly_type == "round_amount":
        amount = rng.choice([5000, 10000, 50000, 99999, 999999])

    timestamp = datetime(2025, 1, 1) + timedelta(
        days=day, hours=hour, minutes=rng.randint(0, 59)
    )

    return {
        "user_id": usuario["user_id"],
        "amount": amount,
        "currency": "ARS",
        "merchant_name": merchant,
        "merchant_category": category,
        "card_last4": f"{rng.randint(1000, 9999)}",
        "timestamp": timestamp.isoformat(),
    }


def main():
    usuarios = [generar_usuario(i) for i in range(50)]
    transacciones = []
    rng = random.Random(42)

    for i in range(5000):
        user = rng.choice(usuarios)
        if rng.random() < 0.85:
            tx = generar_transaccion_normal(user, rng)
        else:
            tx = generar_transaccion_anomala(user, rng)
        transacciones.append(tx)

    with open("transacciones_sinteticas.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "user_id", "amount", "currency", "merchant_name",
            "merchant_category", "card_last4", "timestamp",
        ])
        writer.writeheader()
        writer.writerows(transacciones)

    print(f"[OK] Generadas {len(transacciones)} transacciones sinteticas")
    print("[FILE] Guardadas en transacciones_sinteticas.csv")


if __name__ == "__main__":
    main()
