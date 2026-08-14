"""Deterministic rule engine for fraud detection.

Evaluates transactions against a set of code-based rules and produces
a cumulative risk score (0-100) with the list of fired rules.
"""

from datetime import datetime
from typing import Any


class RuleEngine:
    """Evaluates transactions against deterministic fraud rules.

    Each rule has a fixed weight. The total score is the sum of fired
    rule weights, capped at 100.
    """

    WEIGHTS: dict[str, float] = {
        "high_amount": 35,  # Increased from 25 to catch mid-range fraud better
        "high_velocity": 25,
        "velocity_burst": 30,
        "unusual_merchant": 20,
        "card_mismatch": 20,
        "unusual_hours": 10,
        "off_hours_crypto": 25,
        "country_mismatch": 15,
        "near_fraud": 15,  # Graph: user ≤2 hops from known fraudster
    }

    # Merchant categories considered inherently risky regardless of the name
    RISKY_CATEGORIES: frozenset[str] = frozenset(
        {"btc", "crypto", "gambling", "casino", "money_transfer"}
    )

    # Amount threshold above which the high_amount rule fires
    HIGH_AMOUNT_THRESHOLD: float = 1000.0

    def evaluate(
        self,
        transaction: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> tuple[float, list[str]]:
        """Evaluate a transaction against all rules.

        Args:
            transaction: Dict with keys like amount, merchant_name, card_last4,
                user_id, timestamp, country.
            context: Optional dict with recent_transactions, merchant_blacklist,
                known_cards, home_country.

        Returns:
            Tuple of (total_score, list_of_fired_rule_names).
        """
        ctx = context or {}
        fired: list[str] = []

        # 1. High amount: amount > 1000 (catches mid-range fraud, not just whale txns)
        amount = transaction.get("amount", 0) or 0
        if amount > self.HIGH_AMOUNT_THRESHOLD:
            fired.append("high_amount")

        # 2. High velocity: > 3 transactions in 5 minutes (same user)
        recent_txns = ctx.get("recent_transactions", 0) or 0
        if recent_txns > 3:
            fired.append("high_velocity")

        # 2b. Velocity burst: > 1 tx in 5 min on a risky category
        #     Even 2 crypto/gambling txns in 5 min is anomalous (card testing pattern)
        category = (transaction.get("merchant_category") or "").lower()
        if recent_txns > 1 and category in self.RISKY_CATEGORIES:
            fired.append("velocity_burst")

        # 3. Unusual merchant: in blacklist or inherently risky category
        merchant = (transaction.get("merchant_name") or "").lower()
        blacklist = [m.lower() for m in (ctx.get("merchant_blacklist") or [])]
        if merchant in blacklist or category in self.RISKY_CATEGORIES:
            fired.append("unusual_merchant")

        # 4. Card mismatch: card_last4 not in user's known cards
        card_last4 = transaction.get("card_last4", "")
        known_cards = ctx.get("known_cards") or []
        if known_cards and card_last4 and card_last4 not in known_cards:
            fired.append("card_mismatch")

        # 5. Unusual hours: transaction between 00:00 and 06:00
        ts_str = transaction.get("timestamp")
        hour: int | None = None
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str)
                hour = dt.hour
                if 0 <= hour < 6:
                    fired.append("unusual_hours")
            except (ValueError, TypeError):
                pass

        # 5b. Off-hours + crypto: night transaction on a risky category
        #     Revolut-grade: combine temporal + category signals
        if hour is not None and 0 <= hour < 6 and category in self.RISKY_CATEGORIES:
            fired.append("off_hours_crypto")

        # 6. Country mismatch: transaction country != home country
        tx_country = transaction.get("country")
        home_country = ctx.get("home_country")
        if tx_country and home_country and tx_country != home_country:
            fired.append("country_mismatch")

        # 7. Near fraud: user or card is ≤2 hops from known fraudster (graph network)
        graph_features = ctx.get("graph_features") or {}
        if graph_features.get("is_near_fraud"):
            fired.append("near_fraud")

        total = float(sum(self.WEIGHTS[r] for r in fired))
        total = min(total, 100.0)

        return total, fired
