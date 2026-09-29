"""Deterministic rule engine for fraud detection.

Evaluates transactions against a set of code-based rules and produces
a cumulative risk score (0-100) with the list of fired rules.
"""

import logging
import math
from datetime import datetime
from typing import Any

from src.core.ml_constants import (
    MERCHANT_ADVERSARIAL_CATEGORIES,
    MERCHANT_REGULATED_CATEGORIES,
    MERCHANT_RISK_CATEGORIES,
    normalize_category,
)

logger = logging.getLogger(__name__)


def _as_text(value: Any) -> str:
    """Coerce an untrusted value to text without raising.

    A12: ``(value or "").lower()`` raised AttributeError on an int and would
    have propagated to any non-HTTP consumer. The HTTP path is protected by
    pydantic, so this only ever bites a batch import or a replay tool, which is
    why it went unnoticed.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


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
        "unusual_hours": 10,
        "off_hours_crypto": 25,
        "near_fraud": 15,  # Graph: user ≤2 hops from known fraudster
    }

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

        # A12: amount and merchant_name arrived unvalidated. `amount > 1000`
        # raises TypeError on a string, and `.lower()` raises AttributeError on a
        # non-str, so any consumer other than the HTTP API — a batch import, a
        # replay tool, a future queue worker — inherited a crash. Pydantic keeps
        # the HTTP path clean, which is exactly why nobody noticed.
        #
        # Present-but-malformed and absent are treated differently, on purpose.
        # A value that is there and unusable is evidence the payload is
        # untrustworthy, so it fires high_amount: coercing it to 0 would let
        # anyone who can make the amount unparseable dodge every rule. A field
        # that is simply absent is an incomplete record, not an attack, and
        # firing on it would flood a batch consumer that passes partial dicts
        # with false positives. Absent keeps the previous meaning of zero.
        raw_amount = transaction.get("amount")
        amount: float
        if raw_amount is None:
            amount = 0.0
        elif isinstance(raw_amount, bool) or not isinstance(raw_amount, (int, float)):
            logger.error(
                "Non-numeric amount %r (type %s) — treating as untrusted and "
                "firing high_amount rather than scoring it clean",
                raw_amount,
                type(raw_amount).__name__,
            )
            amount = float("inf")
        elif not math.isfinite(float(raw_amount)):
            logger.error("Non-finite amount %r — treating as untrusted", raw_amount)
            amount = float("inf")
        else:
            amount = float(raw_amount)

        # 1. High amount: amount > 1000 (catches mid-range fraud, not just whale txns)
        if amount > self.HIGH_AMOUNT_THRESHOLD:
            fired.append("high_amount")

        # 2. High velocity: > 3 transactions in 5 minutes (same user)
        recent_txns = ctx.get("recent_transactions", 0) or 0
        if recent_txns > 3:
            fired.append("high_velocity")

        # 2b. Velocity burst: > 1 tx in 5 min on a risky category
        #     Even 2 crypto/gambling txns in 5 min is anomalous (card testing pattern)
        # D7-3: shares one vocabulary with the feature engine instead of its own
        # two-entry alias lookup, so `cripto` and `crypto-exchange` fire here
        # for the same transaction that they zero the crypto feature on. The
        # unknown-value counter and log stay in the feature engine — this runs
        # in the same pipeline on the same transaction, and counting in both
        # would double every event.
        category = normalize_category(transaction.get("merchant_category"))
        if recent_txns > 1 and category in MERCHANT_RISK_CATEGORIES:
            fired.append("velocity_burst")

        # 3. Unusual merchant: blacklisted, or an inherently adversarial category.
        #
        # A14: this fired on category alone for every merchant in
        # MERCHANT_RISK_CATEGORIES, which charged a flat 20 points to every
        # pharmacy purchase and every remittance with no evidence whatsoever.
        # A regulated category is now only a *corroborating* signal: it counts
        # here only when paired with velocity, a night hour, or a blacklisted
        # merchant. An adversarial category still stands on its own, because
        # that is the actual claim being made.
        merchant = _as_text(transaction.get("merchant_name")).lower()
        blacklist = [_as_text(m).lower() for m in (ctx.get("merchant_blacklist") or [])]
        blacklisted = merchant in blacklist

        # Rule 4's hour is needed as corroboration, so it is resolved first.
        # Rule ordering in the *output* list is unchanged; only the evaluation
        # order moved.
        ts_str = transaction.get("timestamp")
        hour: int | None = None
        if ts_str:
            try:
                # Python 3.10 fromisoformat doesn't accept 'Z' suffix
                dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                hour = dt.hour
                if 0 <= hour < 6:
                    fired.append("unusual_hours")
            except (ValueError, TypeError):
                pass

        is_adversarial = category in MERCHANT_ADVERSARIAL_CATEGORIES
        is_regulated = category in MERCHANT_REGULATED_CATEGORIES
        night_hour = hour is not None and 0 <= hour < 6
        has_corroboration = recent_txns > 1 or night_hour or blacklisted

        if blacklisted or is_adversarial or (is_regulated and has_corroboration):
            fired.append("unusual_merchant")

        # 5b. Off-hours + adversarial category.
        #
        # A14: this rule is named for crypto and is scoped accordingly. It used
        # the full risk-category set, so a pharmacy at 3am scored it too — and
        # since `unusual_hours` already charges 10 for the same night hour, the
        # night hour was being counted twice, 10 + 25 = 35 points for one fact.
        # For a regulated merchant the night hour now carries its proportionate
        # weight (unusual_hours, 10) and velocity still stacks on top, which
        # lands a night-time pharmacy with rapid transactions in review rather
        # than in fraud.
        if night_hour and category in MERCHANT_ADVERSARIAL_CATEGORIES:
            fired.append("off_hours_crypto")

        # 6. Near fraud: user or card is ≤2 hops from known fraudster (graph network)
        graph_features = ctx.get("graph_features") or {}
        if graph_features.get("is_near_fraud"):
            fired.append("near_fraud")

        total = float(sum(self.WEIGHTS[r] for r in fired))
        total = min(total, 100.0)

        return total, fired
