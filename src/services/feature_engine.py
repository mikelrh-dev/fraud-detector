"""Feature engine — converts raw transaction data into a fixed-dimension feature vector.

Uses a scikit-learn Pipeline for feature extraction. The pipeline wraps
custom transformers that extract domain-specific features from transaction
dictionaries. The output is always a 10-dimensional feature vector.
"""

from datetime import datetime

import numpy as np

# List of known high-risk merchant categories
HIGH_RISK_CATEGORIES: set[str] = {
    "cryptocurrency",
    "money_transfer",
    "gambling",
    "adult",
    "pharmacy",
}

# Feature names in order — used by get_feature_names() and for model interpretation
FEATURE_NAMES: list[str] = [
    "amount",
    "amount_vs_user_avg",
    "amount_vs_user_std",
    "tx_count_last_5min",
    "tx_count_last_1h",
    "hour_of_day",
    "is_weekend",
    "merchant_risk_level",
    "is_crypto",
    "amount_round_number",
]


class FeatureEngine:
    """Extracts a fixed-dimension feature vector from a transaction dict.

    The engine supports an optional user_history dict for features that
    require historical context (e.g., amount vs user average). When no
    history is available, safe defaults (zeros) are used for those features.

    This class can be fitted on a dataset (for training) or used standalone
    (for inference with pre-computed statistics).

    Usage::

        engine = FeatureEngine()
        features = engine.transform(transaction, user_history=history)
    """

    def fit(
        self,
        transactions: list[dict] | None = None,
        y: list | None = None,
    ) -> "FeatureEngine":
        """Fit the feature engine on a dataset.

        Args:
            transactions: List of transaction dicts to learn statistics from.
            y: Ignored. Present for sklearn Pipeline compatibility.

        Returns:
            Self for chaining.
        """
        # In v1, no per-feature scaling is applied.
        # Future versions can fit StandardScaler or compute user stats here.
        return self

    def transform(
        self,
        transaction: dict,
        user_history: dict | None = None,
    ) -> np.ndarray:
        """Transform a single transaction dict into a feature vector.

        Args:
            transaction: Dict with keys like amount, merchant_name,
                merchant_category, timestamp, etc.
            user_history: Optional dict with user-level statistics
                (avg_amount, std_amount, tx_count_5min, tx_count_1h).

        Returns:
            NumPy array of shape (10,) containing the feature vector.
        """
        history = user_history or {}

        amount = float(transaction.get("amount", 0) or 0)

        # 1. Raw amount
        f_amount = amount

        # 2. Amount vs user average (ratio)
        user_avg = float(history.get("avg_amount", 0) or 0)
        if user_avg > 0:
            f_amount_vs_avg = amount / user_avg - 1.0
        else:
            f_amount_vs_avg = 0.0

        # 3. Amount vs user std
        user_std = float(history.get("std_amount", 0) or 0)
        if user_std > 0:
            f_amount_vs_std = (amount - user_avg) / user_std
        else:
            f_amount_vs_std = 0.0

        # 4. Transaction count last 5 minutes
        f_tx_5min = float(history.get("tx_count_last_5min", 0) or 0)

        # 5. Transaction count last 1 hour
        f_tx_1h = float(history.get("tx_count_last_1h", 0) or 0)

        # 6. Hour of day
        ts_str = transaction.get("timestamp")
        hour = 0
        if ts_str:
            try:
                dt = datetime.fromisoformat(str(ts_str))
                hour = dt.hour
            except (ValueError, TypeError):
                hour = 0
        f_hour = float(hour)

        # 7. Is weekend
        is_weekend = 0.0
        if ts_str:
            try:
                dt = datetime.fromisoformat(str(ts_str))
                is_weekend = 1.0 if dt.weekday() >= 5 else 0.0
            except (ValueError, TypeError):
                is_weekend = 0.0

        # 8. Merchant risk level
        category = (transaction.get("merchant_category") or "").lower()
        f_merchant_risk = 1.0 if category in HIGH_RISK_CATEGORIES else 0.0

        # 9. Is crypto
        f_is_crypto = 1.0 if category == "cryptocurrency" else 0.0

        # 10. Amount is round number (multiple of 100)
        f_round = 1.0 if amount > 0 and amount % 100 == 0 else 0.0

        return np.array([
            f_amount,
            f_amount_vs_avg,
            f_amount_vs_std,
            f_tx_5min,
            f_tx_1h,
            f_hour,
            is_weekend,
            f_merchant_risk,
            f_is_crypto,
            f_round,
        ])

    def get_feature_names(self) -> list[str]:
        """Return the list of feature names in order.

        The names correspond to positions in the feature vector returned
        by transform().
        """
        return FEATURE_NAMES.copy()
