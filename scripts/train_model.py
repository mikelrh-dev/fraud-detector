"""Train an IsolationForest model on synthetic transaction data.

This script:
1. Loads the synthetic dataset from CSV
2. Extracts features using FeatureEngine
3. Trains an IsolationForest model
4. Saves the model to models/isolation_forest_v1.joblib
5. Reports metrics

Usage:
    python scripts/train_model.py
"""

import csv
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (auc, precision_recall_curve, precision_score,
                             recall_score, roc_auc_score, roc_curve)

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.feature_engine import FeatureEngine  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

MODEL_PATH = "models/isolation_forest_v1.joblib"
FEATURE_PIPELINE_PATH = "models/feature_pipeline_v1.joblib"
DATA_PATH = "data/synthetic_transactions.csv"


def load_data(path: str) -> tuple[list[dict], np.ndarray]:
    """Load the synthetic dataset from CSV.

    Returns:
        Tuple of (transactions_list, labels_array).
    """
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

    logger.info("Loaded %d transactions from %s", len(transactions), path)
    return transactions, np.array(labels)


def extract_features(
    transactions: list[dict],
    user_history_map: dict[str, dict] | None = None,
) -> np.ndarray:
    """Extract feature vectors from transactions using FeatureEngine.

    Args:
        transactions: List of transaction dicts.
        user_history_map: Optional dict mapping user_id to history dict.

    Returns:
        NumPy array of shape (n_transactions, 10).
    """
    engine = FeatureEngine()
    features = []

    for tx in transactions:
        user_id = tx.get("user_id", "")
        history = (user_history_map or {}).get(user_id)
        vec = engine.transform(tx, user_history=history)
        features.append(vec)

    return np.array(features)


def build_user_history(
    transactions: list[dict],
    labels: np.ndarray,
) -> dict[str, dict]:
    """Build user history statistics from legitimate transactions only.

    Computes per-user avg_amount, std_amount based on non-fraudulent
    transactions to avoid data leakage.
    """
    user_amounts: dict[str, list[float]] = {}

    for tx, label in zip(transactions, labels):
        if label == 0:  # Only legitimate transactions
            user_id = tx.get("user_id", "unknown")
            if user_id not in user_amounts:
                user_amounts[user_id] = []
            user_amounts[user_id].append(float(tx["amount"]))

    history: dict[str, dict] = {}
    for user_id, amounts in user_amounts.items():
        if len(amounts) > 0:
            history[user_id] = {
                "avg_amount": float(np.mean(amounts)),
                "std_amount": float(np.std(amounts)) if len(amounts) > 1 else 0.0,
                "tx_count_last_5min": 0,
                "tx_count_last_1h": 0,
            }

    logger.info("Built history for %d users", len(history))
    return history


def evaluate_model(
    model: IsolationForest,
    X: np.ndarray,
    y_true: np.ndarray,
) -> dict:
    """Evaluate the model and return metrics.

    Args:
        model: Trained IsolationForest.
        X: Feature matrix.
        y_true: Ground truth labels (0=legitimate, 1=fraud).

    Returns:
        Dict of evaluation metrics.
    """
    # Predictions (IsolationForest: -1=anomaly, 1=normal)
    y_pred = model.predict(X)
    y_pred_binary = np.where(y_pred == -1, 1, 0)

    # Anomaly scores
    y_scores = -model.decision_function(X)

    precision = precision_score(y_true, y_pred_binary, zero_division=0)
    recall = recall_score(y_true, y_pred_binary, zero_division=0)

    # Precision-Recall curve
    precision_vals, recall_vals, _ = precision_recall_curve(y_true, y_scores)
    pr_auc = auc(recall_vals, precision_vals)

    # ROC-AUC
    try:
        roc_auc = roc_auc_score(y_true, y_scores)
    except ValueError:
        roc_auc = 0.0

    return {
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "pr_auc": round(float(pr_auc), 4),
        "roc_auc": round(float(roc_auc), 4),
        "n_samples": len(X),
        "n_anomalies": int(np.sum(y_pred == -1)),
    }


def main() -> None:
    """Run the training pipeline."""
    # 1. Load data
    transactions, labels = load_data(DATA_PATH)

    # 2. Build user history
    user_history = build_user_history(transactions, labels)

    # 3. Extract features
    logger.info("Extracting features...")
    X = extract_features(transactions, user_history)
    logger.info("Feature matrix shape: %s", X.shape)

    # 4. Train IsolationForest
    logger.info("Training IsolationForest...")
    contamination = float(np.sum(labels)) / len(labels)
    model = IsolationForest(
        n_estimators=100,
        max_samples="auto",
        contamination=contamination,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X)

    # 5. Evaluate
    metrics = evaluate_model(model, X, labels)
    logger.info("Training metrics:")
    for key, value in metrics.items():
        logger.info("  %s: %s", key, value)

    # 6. Save model
    model_path = Path(MODEL_PATH)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    logger.info("Model saved to %s", model_path)

    # 7. Save feature engine (fitted)
    engine = FeatureEngine()
    engine.fit(X)
    engine_path = Path(FEATURE_PIPELINE_PATH)
    joblib.dump(engine, engine_path)
    logger.info("Feature pipeline saved to %s", engine_path)

    logger.info("Training complete!")


if __name__ == "__main__":
    main()
