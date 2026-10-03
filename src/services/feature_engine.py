"""Feature engine — converts raw transaction data into a fixed-dimension feature vector.

Uses a scikit-learn Pipeline for feature extraction. The pipeline wraps
custom transformers that extract domain-specific features from transaction
dictionaries. The output is always a 10-dimensional feature vector.
"""

import logging
from datetime import datetime, timezone

import numpy as np

from src.core.counters import unknown_merchant_category
from src.core.ml_constants import (
    KNOWN_MERCHANT_CATEGORIES,
    MERCHANT_RISK_CATEGORIES,
    merchant_category_from_name,
    normalize_category,
)

logger = logging.getLogger(__name__)

#: Categories already reported to the log this process. D7-3 wants the miss
#: visible without turning a consistently misspelled merchant into one
#: WARNING per scored transaction; the counter still counts every occurrence.
#: Process-local and unbounded — a category string is caller-supplied free text,
#: so this is a slow leak in the pathological case, bounded in practice by the
#: number of distinct categories a business actually uses.
_WARNED_CATEGORIES: set[str] = set()

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

        # 6. Hour of day + 7. Is weekend (parse once, derive both)
        ts_str = transaction.get("timestamp")
        hour = 0
        is_weekend = 0.0
        if ts_str:
            try:
                # Python 3.10 fromisoformat doesn't accept 'Z' suffix
                dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                # Normalise to UTC before reading hour AND weekday. Both are
                # local values on an offset-aware datetime, so a `-05:00` feed
                # produced a different `hour_of_day` and a different
                # `is_weekend` than a `+00:00` feed for the same instant — the
                # score depended on the producer's locale rather than on the
                # transaction.
                #
                # A NAIVE datetime is used as-is, never passed to astimezone:
                # that would make Python assume the process's local zone, so the
                # same corpus would score differently on a laptop in Madrid and
                # in a UTC container. See tests/test_timestamp_timezone_normalization.py.
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc)
                hour = dt.hour
                is_weekend = 1.0 if dt.weekday() >= 5 else 0.0
            except (ValueError, TypeError):
                # On parse failure, use neutral defaults (not midnight)
                hour = 12
                is_weekend = 0.0
        f_hour = float(hour)

        # 8. Merchant risk level (normalize aliases first)
        #
        # D7-3: this was `(value or "").lower()` plus a two-entry alias dict, so
        # `bitcoin`, `cripto` and `crypto-exchange` fell through as themselves,
        # matched nothing, and zeroed the crypto and merchant-risk features with
        # no error, no log and no counter — a score indistinguishable from one
        # where the merchant genuinely is not risky. An unmatched value is now
        # counted and logged (once per distinct value, not per transaction, so
        # a merchant that always sends the same misspelling cannot flood the
        # log). This is the single place the observation happens: the rule
        # engine runs on the same transaction in the same pipeline and shares
        # the vocabulary without double-counting.
        category = normalize_category(transaction.get("merchant_category"))
        if category and category not in KNOWN_MERCHANT_CATEGORIES:
            unknown_merchant_category.inc()
            if category not in _WARNED_CATEGORIES:
                _WARNED_CATEGORIES.add(category)
                logger.warning(
                    "unknown_merchant_category %r — no alias in "
                    "CATEGORY_ALIASES, so merchant_risk_level and is_crypto were "
                    "scored 0.0. Add it to CATEGORY_ALIASES or to "
                    "KNOWN_MERCHANT_CATEGORIES.",
                    category,
                )

        # D1: the merchant NAME decides these two features too.
        #
        # `merchant_name` was never consulted, so a real 400,000 USD transaction
        # at `binance` carrying the category `retail` scored `is_crypto = 0.0` and
        # `merchant_risk_level = 0.0` — two of the ten features, and the only
        # ones that know what kind of merchant this is, decided by a field the
        # caller filled in. A quarter of bitcoin at an exchange scored as a
        # retail purchase.
        #
        # NAME FIRST, AND WHY. A name identifies a business; a category labels
        # one. When the two disagree, the name is the more specific evidence, and
        # it is the harder of the two to set casually — nobody picks "binance" to
        # make a transaction look calm. The reverse precedence would let a
        # benign category overrule a recognised venue.
        #
        # A name hit can only RAISE the tier, never lower it: it contributes a
        # canonical category that the same MERCHANT_RISK_CATEGORIES set then
        # reads, and a merchant this vocabulary has never heard of contributes
        # nothing at all rather than something safe.
        #
        # The unknown-category counter above still fires on an unrecognised
        # CATEGORY even when the name was recognised. They are separate facts:
        # the counter measures how often the category field is outside the
        # vocabulary, which is what D1's instrumentation needs to stay
        # trustworthy, and D3 validates the field at the edge for HTTP callers
        # without removing this path for the batch consumers that never reach it.
        name_category = merchant_category_from_name(transaction.get("merchant_name"))
        effective_category = name_category or category
        f_merchant_risk = 1.0 if effective_category in MERCHANT_RISK_CATEGORIES else 0.0

        # 9. Is crypto
        f_is_crypto = 1.0 if effective_category == "cryptocurrency" else 0.0

        # 10. Amount is round number (multiple of 100)
        f_round = 1.0 if amount > 0 and amount % 100 == 0 else 0.0

        vector = np.array([
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

        # The `> 0` guards above protect against negative/zero divisors, not
        # against non-finite inputs: a NaN std or an inf amount slipped through
        # and every downstream comparison against it is False. Sanitize at the
        # boundary so the model contract is "always 10 finite floats".
        if not np.isfinite(vector).all():
            logger.error(
                "Non-finite feature values for transaction %s — sanitizing: %s",
                transaction.get("id", "<unknown>"),
                dict(zip(FEATURE_NAMES, np.where(np.isfinite(vector), vector, np.nan))),
            )
            vector = np.nan_to_num(
                vector, nan=0.0, posinf=0.0, neginf=0.0
            )
        return vector

    def get_feature_names(self) -> list[str]:
        """Return the list of feature names in order.

        The names correspond to positions in the feature vector returned
        by transform().
        """
        return FEATURE_NAMES.copy()
