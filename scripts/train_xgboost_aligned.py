"""Train XGBoost model aligned with production FeatureEngine (10 features).

This script:
1. Loads synthetic_transactions.csv + PaySim (if available)
2. Uses FeatureEngine.transform() to generate EXACT 10 features used in production
3. Applies SMOTE only on train set (no leakage)
4. Trains XGBoost with scale_pos_weight from real class imbalance
5. Saves model to models/xgboost_paysim_v1.joblib (overwrites production model)
6. Reports metrics on test set (PR-AUC, Recall, Precision, F1)

Usage:
    python scripts/train_xgboost_aligned.py
"""

import csv
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
from imblearn.over_sampling import SMOTE
from sklearn.metrics import (auc, classification_report, confusion_matrix,
                             precision_recall_curve, precision_score, recall_score,
                             roc_auc_score)
from sklearn.model_selection import train_test_split
import xgboost as xgb

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.feature_engine import FeatureEngine  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

MODEL_PATH = "models/xgboost_paysim_v1.joblib"
DATA_SYNTHETIC = "data/synthetic_transactions.csv"
DATA_PAYSIM = "../transaccion/PS_20174392719_1491204439457_log.csv"


def generate_synthetic_data(n_samples: int = 50000, fraud_rate: float = 0.01) -> tuple[list[dict], np.ndarray]:
    """Generate synthetic transaction data compatible with FeatureEngine."""
    import random
    from datetime import datetime, timedelta

    rng = np.random.RandomState(42)
    transactions = []
    labels = []

    # Categories - some high-risk, some normal
    normal_categories = ["groceries", "retail", "restaurant", "transport", "entertainment", "health", "education"]
    risk_categories = ["cryptocurrency", "money_transfer", "gambling", "adult", "pharmacy"]

    merchants_normal = [f"Store_{i}" for i in range(50)]
    merchants_risk = [f"CryptoEx_{i}" for i in range(10)] + [f"Casino_{i}" for i in range(5)]

    base_date = datetime(2024, 1, 1)

    for i in range(n_samples):
        is_fraud = rng.random() < fraud_rate

        if is_fraud:
            # Fraudulent transactions: higher amounts, risky categories, unusual hours, high velocity
            amount = float(rng.lognormal(mean=10.5, sigma=0.8))  # ~35k median
            category = rng.choice(risk_categories, p=[0.4, 0.3, 0.15, 0.1, 0.05])
            merchant = rng.choice(merchants_risk)
            hour = rng.choice(list(range(0, 6)) + list(range(22, 24)))  # Night hours
            velocity_5min = rng.randint(3, 15)
            velocity_1h = rng.randint(10, 60)
        else:
            # Legitimate transactions: normal amounts, normal categories, normal hours
            amount = float(rng.lognormal(mean=4.5, sigma=1.2))  # ~90 median
            category = rng.choice(normal_categories)
            merchant = rng.choice(merchants_normal)
            hour = rng.randint(7, 22)
            velocity_5min = rng.randint(0, 2)
            velocity_1h = rng.randint(0, 5)

        # Timestamp
        day_offset = rng.randint(0, 365)
        minute = rng.randint(0, 59)
        timestamp = (datetime(2024, 1, 1) + timedelta(days=int(day_offset))).replace(
            hour=hour, minute=minute, second=0
        ).isoformat()

        tx = {
            "amount": round(amount, 2),
            "merchant_name": merchant,
            "merchant_category": category,
            "timestamp": timestamp,
        }
        transactions.append(tx)
        labels.append(1 if is_fraud else 0)

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
            })
            labels.append(int(row["is_fraud"]))
    logger.info("Loaded %d synthetic transactions from %s", len(transactions), path)
    return transactions, np.array(labels)


def _save_synthetic_csv(transactions: list[dict], labels: np.ndarray, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["amount", "merchant_name", "merchant_category", "timestamp", "is_fraud"])
        writer.writeheader()
        for tx, label in zip(transactions, labels):
            writer.writerow({
                "amount": tx["amount"],
                "merchant_name": tx["merchant_name"],
                "merchant_category": tx["merchant_category"],
                "timestamp": tx["timestamp"],
                "is_fraud": int(label),
            })
    logger.info("Generated and saved %d synthetic transactions to %s", len(transactions), path)


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


def main() -> None:
    logger.info("=== XGBoost Aligned Training Pipeline ===")

    # 1. Load synthetic data
    synth_tx, synth_y = load_synthetic_data(DATA_SYNTHETIC)

    # 2. Load and map PaySim data
    paysim_items, paysim_y = load_paysim_data(DATA_PAYSIM)

    # 3. Combine datasets
    all_transactions = synth_tx + [item["tx"] if isinstance(item, dict) and "tx" in item else item
                                   for item in paysim_items]
    all_histories = [{"avg_amount": 0.0, "std_amount": 0.0}] * len(synth_tx)  # synthetic has no history in CSV
    all_histories += [item["history"] if isinstance(item, dict) and "history" in item else {}
                      for item in paysim_items]
    all_labels = np.concatenate([synth_y, paysim_y]) if len(paysim_y) > 0 else synth_y

    logger.info("Total training samples: %d (fraud: %d, legit: %d)",
                len(all_labels), int(np.sum(all_labels)), int(np.sum(all_labels == 0)))

    # 4. Extract features using production FeatureEngine
    logger.info("Extracting features with production FeatureEngine...")
    X = build_feature_vectors(
        [{"tx": tx, "history": hist} for tx, hist in zip(all_transactions, all_histories)]
    )
    logger.info("Feature matrix shape: %s", X.shape)

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
        n_estimators=500,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos,
        eval_metric="auc",
        use_label_encoder=False,
        random_state=42,
        n_jobs=-1,
    )

    model.fit(
        X_train_res, y_train_res,
        eval_set=[(X_test, y_test)],
        verbose=True,
    )

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

    # 9. Save model
    Path(MODEL_PATH).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    logger.info("Model saved to %s", MODEL_PATH)

    # 10. Quick sanity check with production FeatureEngine
    logger.info("=== Sanity Check with Production FeatureEngine ===")
    from src.services.ml_model import MLModelService
    service = MLModelService(model_path=MODEL_PATH)
    service.load_model()

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