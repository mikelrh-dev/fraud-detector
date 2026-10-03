"""Deterministic rule engine for fraud detection.

Evaluates transactions against a set of code-based rules and produces
a cumulative risk score (0-100) with the list of fired rules.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Any

from src.core.ml_constants import (
    AMOUNT_MAGNITUDE_CAP,
    AMOUNT_MAGNITUDE_POINTS,
    HIGH_AMOUNT_THRESHOLD,
    MERCHANT_ADVERSARIAL_CATEGORIES,
    MERCHANT_REGULATED_CATEGORIES,
    MERCHANT_RISK_CATEGORIES,
    merchant_category_from_name,
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


def _magnitude_points(amount: float) -> float:
    """Extra rule points for how far `amount` sits above the high-amount line.

    D2. `high_amount` was a switch, so 1,001.00 EUR and 400,000.00 USD scored an
    identical 35 — a coffee and a quarter of bitcoin were the same evidence. The
    term is `log10(amount / threshold)` times a per-decade weight, capped, which
    gives the three properties the response needs:

    - **zero AT the threshold**, so crossing the line changes nothing and the
      base weight keeps its meaning (log10(1) == 0);
    - **strictly increasing**, so a larger amount is never cheaper than a
      smaller one — the property `tests/test_model_amount_monotonicity.py`
      asserts for the ML model and that this rule engine had no counterpart for;
    - **capped**, so the rule cannot buy a `fraud` classification on its own at
      any amount. See AMOUNT_MAGNITUDE_CAP for the arithmetic.

    A non-finite `amount` reaches here as `inf` (the A12 untrusted-input
    branch), where `log10(inf)` is `inf` and the cap is what makes the result a
    number. `inf` is therefore scored at the ceiling, which is the honest
    reading of "an amount we could not read": as much as this rule ever claims.
    """
    if not amount > HIGH_AMOUNT_THRESHOLD:
        return 0.0
    decades = math.log10(amount / HIGH_AMOUNT_THRESHOLD)
    return min(decades * AMOUNT_MAGNITUDE_POINTS, AMOUNT_MAGNITUDE_CAP)


class RuleEngine:
    """Evaluates transactions against deterministic fraud rules.

    Each rule has a fixed weight, and the total score is the sum of the fired
    rule weights, capped at 100. ONE EXCEPTION, and it is deliberate rather than
    a forgotten detail: `high_amount` has a fixed BASE weight plus an
    amount-derived term (`_magnitude_points`), because D2 established that a
    switch cannot tell a 1,001 EUR coffee from a 400,000 USD wire. The base
    weight below is still the whole of the claim for a transaction just over the
    threshold, so the table stays readable as the rulebook it is.
    """

    WEIGHTS: dict[str, float] = {
        # Base weight, increased from 25 to catch mid-range fraud better. D2
        # added a magnitude term ON TOP of this, not in place of it, so the
        # number that means "over the line" is still the number below.
        "high_amount": 35,
        "high_velocity": 25,
        "velocity_burst": 30,
        "unusual_merchant": 20,
        "unusual_hours": 10,
        "off_hours_crypto": 25,
        "near_fraud": 15,  # Graph: user ≤2 hops from known fraudster
    }

    def evaluate(
        self,
        transaction: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> tuple[float, list[str]]:
        """Evaluate a transaction against all rules.

        Args:
            transaction: Dict with keys like amount, merchant_name,
                merchant_category, timestamp.
            context: Optional dict with recent_transactions, merchant_blacklist,
                graph_features.

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
        if amount > HIGH_AMOUNT_THRESHOLD:
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
        #
        # D1: the same vocabulary now includes the merchant NAME, so `binance`
        # with the category `retail` reaches this rule exactly as it reaches the
        # feature engine's `is_crypto`. One vocabulary, two readers — a crypto
        # merchant that the features scored as crypto and the rules scored as
        # retail would be the same disagreement D7-3 fixed for aliases, one
        # field over.
        category = normalize_category(transaction.get("merchant_category"))
        name_category = merchant_category_from_name(transaction.get("merchant_name"))
        effective_category = name_category or category
        if recent_txns > 1 and effective_category in MERCHANT_RISK_CATEGORIES:
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
                # Normalise to UTC before reading the hour. `dt.hour` on an
                # offset-aware value is the LOCAL hour, so 23:00-05:00 read as
                # 23 and this rule did not fire on a 04:00 UTC transaction.
                #
                # A NAIVE datetime is used as-is, never passed to astimezone:
                # that would make Python assume the process's local zone, so the
                # same corpus would score differently on a laptop in Madrid and
                # in a UTC container. See tests/test_timestamp_timezone_normalization.py
                # for the full statement — and for why this is unreachable from
                # the HTTP API today and reachable from every other consumer.
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc)
                hour = dt.hour
                if 0 <= hour < 6:
                    fired.append("unusual_hours")
            except (ValueError, TypeError):
                pass

        is_adversarial = effective_category in MERCHANT_ADVERSARIAL_CATEGORIES
        is_regulated = effective_category in MERCHANT_REGULATED_CATEGORIES
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
        if night_hour and effective_category in MERCHANT_ADVERSARIAL_CATEGORIES:
            fired.append("off_hours_crypto")

        # 6. Near fraud: user or card is ≤2 hops from known fraudster (graph network)
        graph_features = ctx.get("graph_features") or {}
        if graph_features.get("is_near_fraud"):
            fired.append("near_fraud")

        # D2: `high_amount` is a magnitude, not a switch. The base weight stays in
        # WEIGHTS because that is the base rule and the other rules share the
        # table; the amount-derived part is added here so `fired` stays the same
        # list of rule NAMES it has always been — a consumer reading
        # `fired_rules` gets "high_amount fired", and the size of the claim lives
        # in the score where every other rule's weight lives.
        weights = dict(self.WEIGHTS)
        weights["high_amount"] += _magnitude_points(amount)
        total = float(sum(weights[r] for r in fired))
        total = min(total, 100.0)

        return total, fired
