"""Train XGBoost model aligned with production FeatureEngine (10 features).

This script:
1. Loads synthetic_transactions.csv + PaySim (if available)
2. Uses FeatureEngine.transform() to generate EXACT 10 features used in production
3. Applies SMOTE only on train set (no leakage)
4. Trains XGBoost with scale_pos_weight from real class imbalance
5. Saves model to models/xgboost_paysim_v1.joblib (overwrites production model)
6. Reports metrics on test set (PR-AUC, Recall, Precision, F1)
7. Cost-sensitive evaluation: FN cost 10x FP, prints economic cost and optimal threshold

Usage:
    python scripts/train_xgboost_aligned.py
"""

import csv
import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
from imblearn.over_sampling import SMOTE
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (auc, confusion_matrix,
                             precision_recall_curve, precision_score, recall_score,
                             roc_auc_score)
from sklearn.model_selection import train_test_split
import xgboost as xgb

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.feature_engine import FeatureEngine  # noqa: E402
from src.core.ml_constants import MERCHANT_RISK_CATEGORIES, CATEGORY_ALIASES  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

MODEL_PATH = "models/xgboost_paysim_v1.joblib"
DATA_SYNTHETIC = "data/synthetic_transactions.csv"
DATA_PAYSIM = "../transaccion/PS_20174392719_1491204439457_log.csv"

#: Amplitude of the post-generation noise pass, shared by main() and the
#: per-feature contract test so the two cannot disagree.
FRAUD_NOISE_INTENSITY = 0.40

# --- Behavioural archetypes -------------------------------------------------
# The generator used to emit one profile per class: fraud was always a
# large amount at a risky merchant at night with a velocity burst, and
# legitimate was always none of those. That is not how fraud works, and it
# is why four of the ten features scored ROC-AUC 1.0000 on their own: each
# one was a sufficient statistic for the label, so the tree model had no
# reason to combine anything.
#
# Real fraud arrives in distinct shapes, and — the part that matters — each
# shape is blind to a different signal:
#
#   card_testing     many tiny transactions at ordinary merchants. High
#                    velocity, *small* amounts, ordinary categories.
#   account_takeover a burst of medium purchases at ordinary merchants. The
#                    merchant field looks completely normal; only the burst
#                    and the timing betray it.
#   high_value_wire  a single large transfer to a high-risk merchant. A
#                    wire is singular, so velocity is *legitimate-looking*;
#                    and the amount is large, but so is a car purchase.
#   low_signal       deliberately ordinary in every dimension. This is the
#                    irreducible false negative: it is why no feature can
#                    separate the classes, and keeping it is the whole
#                    point.
#
# Legitimate traffic gets the same treatment, and crucially it gets a
# `fraud_lookalike` segment: honest customers who buy crypto, shop at 3am,
# and hit a merchant during a sale. Without that segment, merchant risk and
# hour would be near-deterministic and the data would be degenerate in the
# opposite direction.
#
# Every field below is a per-archetype *rate*, never a rule.
#
# The weights are set from how fraud portfolios are actually shaped, not
# from a target metric: card-not-present fraud and account takeover dominate
# transaction *count*, while wires are a minority of events but a large
# share of value. Getting that balance roughly right is what makes raw
# `amount` a weak-but-real signal (real fraud skews a few times larger than
# real legitimate spend) instead of either a perfect separator or noise.
NIGHT_HOURS = (0, 1, 2, 3, 4, 5, 22, 23)
DAY_HOURS = tuple(range(6, 22))

#: name, weight, lognormal(mu, sigma) for amount, P(high-risk category),
#: P(night hour), velocity_5min window, velocity_1h window, P(round amount)
FRAUD_ARCHETYPES: tuple[dict, ...] = (
    {"name": "card_testing", "weight": 0.22, "amount": (3.3, 0.85),
     "p_risk": 0.08, "p_night": 0.45, "v5": (8, 32), "v1": (20, 85), "p_round": 0.02},
    {"name": "account_takeover", "weight": 0.36, "amount": (5.6, 0.9),
     "p_risk": 0.12, "p_night": 0.65, "v5": (10, 45), "v1": (25, 95), "p_round": 0.12},
    {"name": "high_value_wire", "weight": 0.30, "amount": (9.2, 0.9),
     "p_risk": 0.92, "p_night": 0.55, "v5": (0, 3), "v1": (0, 9), "p_round": 0.75},
    {"name": "low_signal", "weight": 0.12, "amount": (4.6, 1.1),
     "p_risk": 0.10, "p_night": 0.20, "v5": (0, 2), "v1": (0, 5), "p_round": 0.10},
)

LEGIT_ARCHETYPES: tuple[dict, ...] = (
    {"name": "everyday", "weight": 0.68, "amount": (4.2, 1.05),
     "p_risk": 0.06, "p_night": 0.12, "v5": (0, 2), "v1": (0, 6), "p_round": 0.10},
    {"name": "big_purchase", "weight": 0.17, "amount": (8.0, 0.9),
     "p_risk": 0.12, "p_night": 0.10, "v5": (0, 3), "v1": (0, 8), "p_round": 0.30},
    {"name": "burst", "weight": 0.12, "amount": (4.6, 1.0),
     "p_risk": 0.08, "p_night": 0.30, "v5": (3, 9), "v1": (8, 28), "p_round": 0.08},
    {"name": "fraud_lookalike", "weight": 0.03, "amount": (10.0, 0.7),
     "p_risk": 0.90, "p_night": 0.85, "v5": (4, 14), "v1": (12, 45), "p_round": 0.20},
)

#: Within the high-risk segment, which merchant category. Crypto dominates
#: fraud because exchanges are where stolen funds land; it is a large but
#: far from overwhelming share of it.
RISK_CATEGORY_WEIGHTS_FRAUD = (0.45, 0.32, 0.13, 0.05, 0.05)  # crypto, transfer, gambling, adult, pharmacy
RISK_CATEGORY_WEIGHTS_LEGIT = (0.60, 0.15, 0.20, 0.025, 0.025)

#: Number of simulated cardholders. Enough transactions each that the
#: per-user history statistics are meaningful.
N_USERS = 4000

#: Below this an amount is never snapped to a round figure — nobody rounds a
#: £4.20 coffee to the nearest hundred.
ROUNDING_FLOOR = 200.0
MAX_AMOUNT = 1_000_000.0


def _pick_archetype(rng: np.random.RandomState, archetypes: tuple[dict, ...]) -> dict:
    weights = np.array([a["weight"] for a in archetypes], dtype=float)
    weights = weights / weights.sum()
    return archetypes[int(rng.choice(len(archetypes), p=weights))]


def _draw_amount(rng: np.random.RandomState, archetype: dict) -> float:
    """Lognormal amount, optionally snapped to a round figure.

    Every archetype draws from its own lognormal, but the supports overlap
    heavily: a fraud wire at £13k and a legitimate car purchase at £13k are
    the same number, and a card-testing fraud at £16 and a legitimate
    takeaway at £16 are the same number. That overlap is deliberate.
    """
    mu, sigma = archetype["amount"]
    amount = float(rng.lognormal(mean=mu, sigma=sigma))
    if amount >= ROUNDING_FLOOR and rng.random() < archetype["p_round"]:
        amount = round(amount / 100.0) * 100.0
    return float(min(max(round(amount, 2), 0.01), MAX_AMOUNT))


def _draw_hour(rng: np.random.RandomState, p_night: float) -> int:
    if rng.random() < p_night:
        return int(NIGHT_HOURS[rng.randint(len(NIGHT_HOURS))])
    return int(DAY_HOURS[rng.randint(len(DAY_HOURS))])


def _draw_category(
    rng: np.random.RandomState,
    archetype: dict,
    normal_categories: list[str],
    risk_categories: list[str],
    is_fraud: bool,
) -> str:
    """Merchant category.

    Emits only canonical names from ``MERCHANT_RISK_CATEGORIES`` plus the
    aliases ``CATEGORY_ALIASES`` normalises. The previous on-disk CSV used a
    ``high_risk``/``low_risk`` vocabulary that ``FeatureEngine`` does not
    recognise, so ``merchant_risk_level`` and ``is_crypto`` were constant
    zero for every single row.
    """
    if rng.random() < archetype["p_risk"]:
        weights = (RISK_CATEGORY_WEIGHTS_FRAUD if is_fraud
                   else RISK_CATEGORY_WEIGHTS_LEGIT)
        # Normalise defensively: rng.choice raises on a vector that does not
        # sum to 1, and a hand-edited weight tuple should not be able to take
        # the whole generator down.
        p = np.array(weights, dtype=float)
        p = p / p.sum()
        category = risk_categories[int(rng.choice(len(risk_categories), p=p))]
        # Real feeds carry alias spellings; FeatureEngine normalises them.
        alias = CATEGORY_ALIASES.get(category)
        if alias and rng.random() < 0.15:
            return alias
        return category
    return str(normal_categories[rng.randint(len(normal_categories))])


def _assign_user_statistics(
    transactions: list[dict],
    user_ids: list[int],
    rng: np.random.RandomState,
) -> None:
    """Populate ``user_avg_amount`` / ``user_std_amount`` per transaction.

    Each user gets a *persona* — their typical spend and spread — and the
    running statistics start from it, so a user's first transaction already
    has a meaningful history rather than a zero that would make
    ``amount_vs_user_avg`` collapse to 0 and take the feature with it.

    The statistics are then advanced in timestamp order over the user's own
    prior transactions, which is what production sees at scoring time. This
    is deliberately causal: a transaction never contributes to the history it
    is scored against, so the ratio features are honest z-scores rather than
    an artefact of the row including itself.
    """
    n_users = int(max(user_ids)) + 1
    persona_mean = rng.lognormal(mean=4.6, sigma=1.0, size=n_users)
    persona_std = np.abs(rng.lognormal(mean=3.2, sigma=0.7, size=n_users))
    persona_std = np.maximum(persona_std, 1.0)

    running_sum = persona_mean.copy()
    running_sq = (persona_mean ** 2 + persona_std ** 2).copy()
    running_n = np.zeros(n_users, dtype=float)

    order = sorted(
        range(len(transactions)),
        key=lambda i: (user_ids[i], transactions[i]["timestamp"]),
    )
    for i in order:
        uid = user_ids[i]
        n = running_n[uid]
        mean = running_sum[uid] / (n + 1.0)
        # Variance over the persona plus the n observed transactions.
        second = running_sq[uid] / (n + 1.0)
        var = max(second - mean ** 2, 0.0)
        std = float(np.sqrt(var)) if var > 0.0 else 0.0

        transactions[i]["user_avg_amount"] = round(mean, 2)
        transactions[i]["user_std_amount"] = round(std, 2)

        amount = float(transactions[i]["amount"])
        running_sum[uid] += amount
        running_sq[uid] += amount ** 2
        running_n[uid] += 1


def generate_synthetic_data(n_samples: int = 50000, fraud_rate: float = 0.01) -> tuple[list[dict], np.ndarray]:
    """Generate synthetic transaction data compatible with FeatureEngine.

    The design constraint is that **no single feature may separate the
    classes on its own**. Every field is a per-archetype rate with real
    overlap between the two populations, and a deliberate slice of fraud is
    indistinguishable from legitimate traffic. An honest ten-feature model
    therefore tops out well below a perfect score — which is the correct
    answer for this problem, not a shortfall.
    """
    rng = np.random.RandomState(42)
    transactions: list[dict] = []
    labels: list[int] = []
    user_ids: list[int] = []

    normal_categories = ["groceries", "retail", "restaurant", "transport",
                         "entertainment", "health", "education"]
    risk_categories = ["cryptocurrency", "money_transfer", "gambling",
                       "adult", "pharmacy"]
    merchants_normal = [f"Store_{i}" for i in range(50)]
    merchants_risk = [f"CryptoEx_{i}" for i in range(10)] + [f"Casino_{i}" for i in range(5)]

    for _ in range(n_samples):
        is_fraud = rng.random() < fraud_rate
        archetype = _pick_archetype(
            rng, FRAUD_ARCHETYPES if is_fraud else LEGIT_ARCHETYPES
        )

        amount = _draw_amount(rng, archetype)
        category = _draw_category(
            rng, archetype, normal_categories, risk_categories, is_fraud
        )
        merchant_pool = merchants_risk if archetype["p_risk"] > 0.5 and is_fraud else merchants_normal
        merchant = str(merchant_pool[rng.randint(len(merchant_pool))])
        hour = _draw_hour(rng, archetype["p_night"])
        velocity_5min = int(rng.randint(*archetype["v5"]))
        velocity_1h = int(rng.randint(*archetype["v1"]))

        day_offset = int(rng.randint(0, 365))
        minute = int(rng.randint(0, 59))
        timestamp = (datetime(2024, 1, 1) + timedelta(days=day_offset)).replace(
            hour=hour, minute=minute, second=0
        ).isoformat()

        transactions.append({
            "amount": amount,
            "merchant_name": merchant,
            "merchant_category": category,
            "timestamp": timestamp,
            "velocity_5min": velocity_5min,
            "velocity_1h": velocity_1h,
        })
        labels.append(1 if is_fraud else 0)
        user_ids.append(int(rng.randint(N_USERS)))

    _assign_user_statistics(transactions, user_ids, rng)

    # user_id is kept out of the row dict the FeatureEngine consumes but is
    # needed by the CSV writer to make the per-user statistics auditable.
    for tx, uid in zip(transactions, user_ids):
        tx["user_id"] = f"user-{uid:05d}"

    return transactions, np.array(labels)


def load_synthetic_data(path: str) -> tuple[list[dict], np.ndarray]:
    """Load synthetic data from CSV, or generate if not exists."""
    if Path(path).exists():
        return _load_synthetic_csv(path)

    # Generate and save
    logger.info("Synthetic data not found at %s, generating...", path)
    transactions, labels = generate_synthetic_data(n_samples=50000, fraud_rate=0.01)
    _save_synthetic_csv(transactions, labels, path)
    return transactions, labels


def _load_synthetic_csv(path: str) -> tuple[list[dict], np.ndarray]:
    transactions = []
    labels = []
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            transactions.append({
                "amount": float(row["amount"]),
                "merchant_name": row["merchant_name"],
                "merchant_category": row["merchant_category"],
                "timestamp": row["timestamp"],
                # Velocity / per-user stat columns, with "0" fallback so
                # legacy column-less CSVs still parse (FD-VEL-004).
                "user_avg_amount": float(row.get("user_avg_amount", "0") or 0),
                "user_std_amount": float(row.get("user_std_amount", "0") or 0),
                "velocity_5min": int(row.get("velocity_5min", "0") or 0),
                "velocity_1h": int(row.get("velocity_1h", "0") or 0),
            })
            labels.append(int(row["is_fraud"]))
    logger.info("Loaded %d synthetic transactions from %s", len(transactions), path)
    return transactions, np.array(labels)


def _save_synthetic_csv(transactions: list[dict], labels: np.ndarray, path: str) -> None:
    """Persist the synthetic corpus.

    ``user_avg_amount`` / ``user_std_amount`` are written here because
    omitting them made ``amount_vs_user_std`` a constant-zero column for
    every row of the training set: the generator computed nothing, the CSV
    carried nothing, ``_load_synthetic_csv`` fell back to ``0``, and the
    ``FeatureEngine`` ``> 0`` guard then emitted 0.0 for the feature. The
    deployed artifact still carried weight on that dead column.
    """
    fieldnames = [
        "user_id", "amount", "merchant_name", "merchant_category",
        "timestamp", "is_fraud", "velocity_5min", "velocity_1h",
        "user_avg_amount", "user_std_amount",
    ]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for tx, label in zip(transactions, labels):
            writer.writerow({
                "user_id": tx.get("user_id", ""),
                "amount": tx["amount"],
                "merchant_name": tx["merchant_name"],
                "merchant_category": tx["merchant_category"],
                "timestamp": tx["timestamp"],
                "is_fraud": int(label),
                "velocity_5min": tx.get("velocity_5min", 0),
                "velocity_1h": tx.get("velocity_1h", 0),
                "user_avg_amount": tx.get("user_avg_amount", 0),
                "user_std_amount": tx.get("user_std_amount", 0),
            })
    logger.info("Generated and saved %d synthetic transactions to %s", len(transactions), path)


def build_synthetic_history(tx: dict) -> dict:
    """Build a FeatureEngine user_history from a synthetic transaction dict.

    Reads the velocity and per-user stat keys emitted by the synthetic
    generators; missing keys fall back to zero so legacy column-less CSVs
    still produce valid (zero) history features.
    """
    return {
        "avg_amount": float(tx.get("user_avg_amount", 0) or 0),
        "std_amount": float(tx.get("user_std_amount", 0) or 0),
        "tx_count_last_5min": int(tx.get("velocity_5min", 0) or 0),
        "tx_count_last_1h": int(tx.get("velocity_1h", 0) or 0),
    }


def load_paysim_data(path: str) -> tuple[list[dict], np.ndarray]:
    """Load PaySim data and MAP to production FeatureEngine features."""
    import pandas as pd

    if not Path(path).exists():
        logger.warning("PaySim file not found at %s, skipping", path)
        return [], np.array([])

    logger.info("Loading PaySim data from %s...", path)
    df = pd.read_csv(path)

    # Filter to only transaction types that have fraud (TRANSFER, CASH_OUT)
    # and sample for speed (PaySim is ~6M rows)
    fraud_types = ["TRANSFER", "CASH_OUT"]
    df = df[df["type"].isin(fraud_types)].copy()

    # Sample if too large (keep all fraud + sample legit)
    fraud_df = df[df["isFraud"] == 1]
    legit_df = df[df["isFraud"] == 0].sample(n=min(200000, len(df[df["isFraud"] == 0])), random_state=42)
    df = pd.concat([fraud_df, legit_df]).sample(frac=1, random_state=42).reset_index(drop=True)

    logger.info("PaySim sample: %d rows (%d fraud, %d legit)",
                len(df), len(fraud_df), len(legit_df))

    transactions = []
    labels = []

    # Build user history for avg/std amounts (per nameOrig, using only legit txns)
    legit_only = df[df["isFraud"] == 0]
    user_stats = {}
    for uid, group in legit_only.groupby("nameOrig"):
        amounts = group["amount"].astype(float).values
        if len(amounts) > 0:
            user_stats[uid] = {
                "avg_amount": float(np.mean(amounts)),
                "std_amount": float(np.std(amounts)) if len(amounts) > 1 else 0.0,
            }

    # Map PaySim types to production merchant_category
    type_to_category = {
        "TRANSFER": "money_transfer",      # in HIGH_RISK_CATEGORIES
        "CASH_OUT": "cash_out",            # not in HIGH_RISK_CATEGORIES by default
        "CASH_IN": "cash_in",
        "PAYMENT": "payment",
        "DEBIT": "debit",
    }

    for _, row in df.iterrows():
        uid = row["nameOrig"]
        history = user_stats.get(uid, {"avg_amount": 0.0, "std_amount": 0.0})

        tx = {
            "amount": float(row["amount"]),
            "merchant_name": row["nameDest"][:50],
            "merchant_category": type_to_category.get(row["type"], "other"),
            "timestamp": f"2024-01-{(int(row['step']) % 28) + 1:02d}T{int(row['step']) % 24:02d}:00:00",
        }
        transactions.append({
            "tx": tx,
            "history": history,
        })
        labels.append(int(row["isFraud"]))

    logger.info("Mapped %d PaySim transactions to production features", len(transactions))
    return transactions, np.array(labels)


def add_realistic_noise(
    transactions: list[dict],
    labels: np.ndarray,
    fraud_noise_intensity: float = 0.15,
) -> tuple[list[dict], np.ndarray]:
    """
    Add realistic noise to synthetic transactions to prevent overfitting.
    
    For FRAUD transactions, add:
    - Amount variance ±5-15% (card testing often uses slightly different amounts)
    - Merchant name typos 3% (fraudsters obfuscate merchant names)
    - Timestamp jitter ±10-30 minutes (avoid exact patterns)
    
    For LEGITIMATE transactions, add minimal noise:
    - Small amount variance ±2-5% (natural rounding)
    - Rare typos 0.5%
    
    Args:
        transactions: List of transaction dicts
        labels: np.array of fraud labels (0/1)
        fraud_noise_intensity: How much noise to add to fraud txs (0.15 = 15%)
        
    Returns:
        (noisy_transactions, labels) tuple
    """
    rng = np.random.RandomState(42)
    noisy_txs = []

    for tx, label in zip(transactions, labels):
        tx_copy = tx.copy()
        # Capture round-ness *before* the jitter: a rent payment or a wire
        # transfer stays a round figure when the amount wobbles by a few
        # percent, and that is what `amount_round_number` encodes.
        was_round = float(tx_copy["amount"]) >= 100.0 and (
            float(tx_copy["amount"]) % 100 == 0
        )

        if label == 1:  # FRAUD
            # Amount variance: ±5-15%
            amount_factor = rng.uniform(1 - fraud_noise_intensity, 1 + fraud_noise_intensity)
            tx_copy["amount"] = max(0.01, tx_copy["amount"] * amount_factor)

            # Merchant name typo: 3% chance
            if rng.random() < 0.03 and len(tx_copy["merchant_name"]) > 2:
                merchant = tx_copy["merchant_name"]
                idx = rng.randint(0, len(merchant))
                # Replace character with random letter/digit
                new_char = rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))
                merchant = merchant[:idx] + new_char + merchant[idx+1:]
                tx_copy["merchant_name"] = merchant

            # Timestamp jitter: ±10-30 minutes
            try:
                ts = datetime.fromisoformat(tx_copy["timestamp"])
                jitter_minutes = rng.randint(-30, 30)
                ts = ts + timedelta(minutes=jitter_minutes)
                tx_copy["timestamp"] = ts.isoformat()
            except (ValueError, KeyError):
                pass  # Skip if timestamp can't be parsed

        else:  # LEGITIMATE
            # Smaller variance: ±2-5%
            amount_factor = rng.uniform(0.98, 1.05)
            tx_copy["amount"] = max(0.01, tx_copy["amount"] * amount_factor)

            # Rare typo: 0.5%
            if rng.random() < 0.005 and len(tx_copy["merchant_name"]) > 2:
                merchant = tx_copy["merchant_name"]
                idx = rng.randint(0, len(merchant))
                # Replace character with random letter/digit
                new_char = rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))
                merchant = merchant[:idx] + new_char + merchant[idx+1:]
                tx_copy["merchant_name"] = merchant

        # Re-snap to the nearest hundred if the amount was round before the
        # jitter. Without this the feature was a constant zero for the whole
        # corpus: the multiplier took every multiple of 100 with it, so the
        # deployed model's weight on it was meaningless.
        if was_round:
            tx_copy["amount"] = float(
                max(round(round(float(tx_copy["amount"])) / 100.0) * 100.0, 100.0)
            )

        noisy_txs.append(tx_copy)
    
    logger.info("Added realistic noise to %d transactions (fraud: %.1f%% noise intensity)",
                len(transactions), fraud_noise_intensity * 100)
    return noisy_txs, labels


def build_feature_vectors(
    transactions: list[dict],
    histories: list[dict] | None = None,
) -> np.ndarray:
    """Extract feature vectors using production FeatureEngine."""
    engine = FeatureEngine()
    features = []

    for i, item in enumerate(transactions):
        if isinstance(item, dict) and "tx" in item:
            # PaySim format: {"tx": {...}, "history": {...}}
            tx = item["tx"]
            history = item["history"]
        else:
            # Synthetic format: direct transaction dict
            tx = item
            history = (histories or [{}])[i] if histories else {}

        vec = engine.transform(tx, user_history=history)
        features.append(vec)

    return np.array(features)


def build_training_matrix() -> tuple[np.ndarray, np.ndarray]:
    """Build the exact feature matrix and labels the model is fit on.

    Single source of truth for the training distribution. ``main()`` and the
    per-feature contract test in ``tests/test_model_feature_contract.py``
    both call this, so the contract can never be measured against a
    re-implementation of the pipeline that has silently drifted from it.
    """
    # 1. Load synthetic data
    synth_tx, synth_y = load_synthetic_data(DATA_SYNTHETIC)

    # 2. Load and map PaySim data
    paysim_items, paysim_y = load_paysim_data(DATA_PAYSIM)

    # 3. Combine datasets
    all_transactions = synth_tx + [item["tx"] if isinstance(item, dict) and "tx" in item else item
                                   for item in paysim_items]
    # Synthetic histories now carry the velocity / user-stat values read from
    # the CSV, so FeatureEngine sees real counts instead of zeros (FD-VEL-004).
    all_histories = [build_synthetic_history(tx) for tx in synth_tx]
    all_histories += [item["history"] if isinstance(item, dict) and "history" in item else {}
                      for item in paysim_items]
    all_labels = np.concatenate([synth_y, paysim_y]) if len(paysim_y) > 0 else synth_y

    logger.info("Total training samples: %d (fraud: %d, legit: %d)",
                len(all_labels), int(np.sum(all_labels)), int(np.sum(all_labels == 0)))

    # 3.5. ADD REALISTIC NOISE to prevent overfitting
    logger.info("Adding realistic noise to synthetic data...")
    all_transactions, all_labels = add_realistic_noise(
        all_transactions, all_labels, fraud_noise_intensity=FRAUD_NOISE_INTENSITY
    )

    # 4. Extract features using production FeatureEngine
    logger.info("Extracting features with production FeatureEngine...")
    X = build_feature_vectors(
        [{"tx": tx, "history": hist} for tx, hist in zip(all_transactions, all_histories)]
    )
    logger.info("Feature matrix shape: %s", X.shape)
    return X, all_labels


def main() -> None:
    logger.info("=== XGBoost Aligned Training Pipeline ===")

    X, all_labels = build_training_matrix()

    # 5. Train/test split (stratified)
    X_train, X_test, y_train, y_test = train_test_split(
        X, all_labels,
        test_size=0.2,
        random_state=42,
        stratify=all_labels,
    )

    logger.info("Train: %d (fraud: %d, legit: %d)",
                len(X_train), int(np.sum(y_train)), int(np.sum(y_train == 0)))
    logger.info("Test:  %d (fraud: %d, legit: %d)",
                len(X_test), int(np.sum(y_test)), int(np.sum(y_test == 0)))
    
    # ADD FEATURE-LEVEL NOISE to prevent overfit
    rng = np.random.RandomState(42)
    X_train = X_train + rng.normal(0, 0.1, X_train.shape)  # Gaussian noise in feature space
    logger.info("Added Gaussian noise (std=0.1) to train features")

    # 6. SMOTE only on TRAIN (no leakage)
    contamination = float(np.sum(y_train)) / len(y_train)
    logger.info("Fraud rate in train: %.4f%%", contamination * 100)

    smote = SMOTE(sampling_strategy=0.5, random_state=42)
    X_train_res, y_train_res = smote.fit_resample(X_train, y_train)
    logger.info("After SMOTE: %d samples (fraud: %d, legit: %d)",
                len(X_train_res), int(np.sum(y_train_res)), int(np.sum(y_train_res == 0)))

    # 7. Train XGBoost
    neg_count = int(np.sum(y_train == 0))
    pos_count = int(np.sum(y_train == 1))
    scale_pos = neg_count / pos_count if pos_count > 0 else 1.0

    logger.info("Training XGBoost (scale_pos_weight=%.1f)...", scale_pos)
    model = xgb.XGBClassifier(
        n_estimators=200,  # Reduced from 500 to prevent overfitting
        max_depth=4,  # Reduced from 6 to prevent overfitting
        learning_rate=0.1,
        subsample=0.7,  # Reduced from 0.8
        colsample_bytree=0.7,  # Reduced from 0.8
        scale_pos_weight=scale_pos,
        eval_metric="aucpr",
        use_label_encoder=False,
        random_state=42,
        n_jobs=-1,
        reg_alpha=1.0,  # L1 regularization to reduce complexity
        reg_lambda=2.0,  # L2 regularization to reduce complexity
    )

    model.fit(
        X_train_res, y_train_res,
        eval_set=[(X_test, y_test)],
        verbose=True,
    )

    # 7.5. CALIBRATE the model to get smooth probabilities (sigmoid method)
    logger.info("Calibrating model with sigmoid method for smooth probabilities...")
    calibrated_model = CalibratedClassifierCV(model, method='sigmoid', cv=5)
    calibrated_model.fit(X_train_res, y_train_res)
    model = calibrated_model  # Use calibrated model for predictions

    # 8. Evaluate on test set
    logger.info("=== Evaluation on Test Set ===")
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # PR-AUC
    precisions, recalls, _ = precision_recall_curve(y_test, y_proba)
    pr_auc = auc(recalls, precisions)

    # ROC-AUC
    try:
        roc_auc = roc_auc_score(y_test, y_proba)
    except ValueError:
        roc_auc = 0.0

    logger.info("Test Metrics:")
    logger.info("  Precision: %.4f", precision)
    logger.info("  Recall:    %.4f", recall)
    logger.info("  F1:        %.4f", f1)
    logger.info("  PR-AUC:    %.4f", pr_auc)
    logger.info("  ROC-AUC:   %.4f", roc_auc)

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = cm.ravel()
    logger.info("Confusion Matrix:")
    logger.info("  TN=%d, FP=%d, FN=%d, TP=%d", tn, fp, fn, tp)

    # Cost-sensitive evaluation: FN (fraud not blocked) costs 10x an FP (review).
    # This aligns the model objective with economic loss instead of raw accuracy.
    cost_fn, cost_fp = 10.0, 1.0
    cost_default = fn * cost_fn + fp * cost_fp
    logger.info("Cost (threshold=0.5): %.2f  (FN=%d*%g + FP=%d*%g)",
                cost_default, fn, cost_fn, fp, cost_fp)

    # Find the threshold that minimizes expected cost on the test set.
    best_thr, best_cost = 0.5, cost_default
    for thr in np.arange(0.05, 0.95, 0.05):
        y_thr = (y_proba >= thr).astype(int)
        tn_t, fp_t, fn_t, tp_t = confusion_matrix(y_test, y_thr).ravel()
        c = fn_t * cost_fn + fp_t * cost_fp
        if c < best_cost:
            best_cost, best_thr = c, thr
    logger.info("Optimal cost threshold: %.2f (expected cost %.2f)", best_thr, best_cost)

    # 9. Save model with feature contract stamp
    Path(MODEL_PATH).parent.mkdir(parents=True, exist_ok=True)
    engine = FeatureEngine()
    feature_names = engine.get_feature_names()
    artifact = {"model": model, "feature_names": feature_names}
    joblib.dump(artifact, MODEL_PATH)
    logger.info("Model saved to %s (with feature_names: %s)", MODEL_PATH, feature_names)

    # 10. Quick sanity check with production FeatureEngine
    logger.info("=== Sanity Check with Production FeatureEngine ===")
    from src.services.ml_model import MLModelService
    service = MLModelService(model_path=MODEL_PATH)
    loaded = service.load_model()
    logger.info("Model loaded: %s, n_features: %s, feature_names: %s",
                loaded, service.n_features, service.feature_names)

    engine = FeatureEngine()

    # High-risk crypto tx
    tx_high = {
        "amount": 50000.0,
        "merchant_category": "cryptocurrency",
        "timestamp": "2024-01-15T03:00:00+00:00",
    }
    hist_high = {"avg_amount": 200.0, "std_amount": 500.0,
                 "tx_count_last_5min": 10, "tx_count_last_1h": 50}
    f_high = engine.transform(tx_high, user_history=hist_high)
    score_high = service.predict(f_high)
    logger.info("High-risk crypto (50k, 3am, high vel): ml_score = %.2f", score_high)

    # Normal grocery
    tx_low = {
        "amount": 50.0,
        "merchant_category": "groceries",
        "timestamp": "2024-01-15T12:00:00",
    }
    hist_low = {"avg_amount": 100.0, "std_amount": 20.0,
                "tx_count_last_5min": 0, "tx_count_last_1h": 2}
    f_low = engine.transform(tx_low, user_history=hist_low)
    score_low = service.predict(f_low)
    logger.info("Normal grocery (50, 12pm, no vel): ml_score = %.2f", score_low)

    logger.info("=== Training Complete ===")


if __name__ == "__main__":
    main()