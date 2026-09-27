"""Ensemble scorer — combines rule, ML, and context scores into a final risk score.

Applies configurable weights and dynamic thresholds based on transaction
amount tiers.
"""

import logging
import math

from src.core.config import settings

logger = logging.getLogger(__name__)


class EnsembleScorer:
    """Combines scoring layers into a single ensemble score with classification.

    Uses a weighted average of rule_score, ml_score, and context_score,
    then classifies against a dynamic threshold based on amount.

    A layer may be passed as ``None`` to say "this layer had no signal" (for
    example the ML model is not loaded). Its weight is then redistributed across
    the layers that did produce a value, rather than being silently lost. A
    layer that ran and scored ``0.0`` is real evidence and keeps its weight.
    """

    def combine(
        self,
        rule_score: float | None,
        ml_score: float | None,
        context_score: float | None = 0.0,
        weights: dict[str, float] | None = None,
    ) -> float:
        """Compute the weighted ensemble score.

        Args:
            rule_score: Score from the rule engine (0-100).
            ml_score: Score from the ML model (0-100).
            context_score: Optional contextual risk score (0-100, default 0).
            weights: Dict with keys 'rule', 'ml', 'context' (default from config).

        Returns:
            Ensemble score between 0 and 100.
        """
        w = weights or {
            "rule": settings.ensemble_rule_weight,
            "ml": settings.ensemble_ml_weight,
            "context": settings.ensemble_context_weight,
        }

        # A layer contributes only if it produced a signal. ``None`` means "this
        # layer had nothing to say" (the ML model is not loaded, say), which is
        # a different thing from a layer that ran and scored 0 — that is real
        # evidence of low risk and must keep its weight.
        #
        # A15: the previous filter was on *weight* rather than on signal, so an
        # absent model still consumed its 0.25 share. Every score silently lost
        # 25 points with the model down, with no log and no signal, and the
        # effect was worst exactly when the system was already degraded. Weight
        # is now redistributed across the layers that actually produced a
        # value, so a surviving layer carries the full 1.0.
        scores = {
            "rule": rule_score,
            "ml": ml_score,
            "context": context_score,
        }

        active = {k: v for k, v in scores.items() if v is not None}
        active_weights = {k: w.get(k, 0) for k in active if w.get(k, 0) > 0}
        total_weight = sum(active_weights.values())

        if total_weight == 0:
            # Every layer either produced nothing or is weighted at zero. A
            # single live layer at weight zero still means we have no basis to
            # score, so refuse rather than invent a number.
            logger.error(
                "No layer produced a signal (rule=%r ml=%r context=%r, weights=%r) "
                "— returning 0.0",
                rule_score,
                ml_score,
                context_score,
                w,
            )
            return 0.0

        # A non-finite layer is a bug upstream, not a risk signal. It must never
        # be allowed to decide the outcome: min/max propagate NaN unchanged and
        # every `NaN > threshold` comparison is False, which silently classified
        # the transaction as legitimate. Fail closed instead — the highest score
        # is above every threshold, so the transaction is routed to review.
        non_finite = [
            k for k, v in active.items() if not math.isfinite(float(v))  # type: ignore[arg-type]
        ]
        if non_finite:
            logger.error(
                "Non-finite score(s) %s in ensemble input "
                "(rule=%r ml=%r context=%r) — failing closed to 100.0",
                ",".join(sorted(non_finite)),
                rule_score,
                ml_score,
                context_score,
            )
            return 100.0

        # Normalize the *active* weights to sum to 1.0, then weighted average.
        total = sum(
            float(active[k]) * (active_weights[k] / total_weight)  # type: ignore[arg-type]
            for k in active_weights
        )
        return min(max(total, 0.0), 100.0)

    def get_threshold(self, amount: float) -> float:
        """Look up the fraud threshold for a given transaction amount.

        Uses the configured threshold tiers:
            - Low: $0-1000 → 70
            - Medium: $1000.01-10000 → 50
            - High: $10000.01-50000 → 45
            - Critical: > $50000 → 40

        Uses half-open intervals [min, max) to avoid gaps at boundaries.
        """
        # An unknown amount must not pick a tier by accident. The last tier's
        # max is math.inf and the test is `amount < max`, so inf (and every
        # negative) matched nothing and fell through to the low-tier default.
        # Fail closed on the strictest tier instead: the lowest threshold is
        # the one most likely to route the transaction to review.
        if not math.isfinite(amount):
            logger.error("Non-finite amount %r in get_threshold — using strictest tier", amount)
            return min(float(t["threshold"]) for t in settings.threshold_tiers)

        for tier in settings.threshold_tiers:
            if tier["min_amount"] <= amount < tier["max_amount"]:
                return float(tier["threshold"])

        # Negative amounts are rejected at the schema (ge=0); if one still
        # arrives from a non-HTTP caller, use the low tier explicitly.
        logger.error("Amount %r matched no configured tier — using low tier", amount)
        return float(settings.threshold_tiers[0]["threshold"])

    def classify(self, score: float, threshold: float) -> str:
        """Classify a transaction based on its score vs threshold.

        Returns one of: 'legitimate', 'review', 'fraud'.

        Bands:
            fraud  : score > threshold
            review : score >= threshold * 0.75  (grey zone — needs analyst)
            legitimate: score < threshold * 0.75

        A non-finite score is classified as 'fraud'. Every comparison against
        NaN is False, which would otherwise fall through to 'legitimate' and
        whitelist the transaction.
        """
        if not math.isfinite(score) or not math.isfinite(threshold):
            logger.error("Non-finite score/threshold (%r/%r) — classifying as fraud", score, threshold)
            return "fraud"
        if score > threshold:
            return "fraud"
        if score >= threshold * 0.75:
            return "review"
        return "legitimate"
