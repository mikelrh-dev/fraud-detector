"""Ensemble scorer — combines rule, ML, and context scores into a final risk score.

Applies configurable weights and dynamic thresholds based on transaction
amount tiers.
"""


from src.core.config import settings


class EnsembleScorer:
    """Combines scoring layers into a single ensemble score with classification.

    Uses a weighted average of rule_score, ml_score, and context_score,
    then classifies against a dynamic threshold based on amount.
    """

    def combine(
        self,
        rule_score: float,
        ml_score: float,
        context_score: float = 0.0,
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
        total = (
            rule_score * w.get("rule", 0)
            + ml_score * w.get("ml", 0)
            + context_score * w.get("context", 0)
        )
        return min(max(total, 0.0), 100.0)

    def get_threshold(self, amount: float) -> float:
        """Look up the fraud threshold for a given transaction amount.

        Uses the configured threshold tiers:
            - Low: $0-1000 → 70
            - Medium: $1001-10000 → 60
            - High: $10001-50000 → 50
            - Critical: > $50000 → 40
        """
        for tier in settings.threshold_tiers:
            if tier["min_amount"] <= amount <= tier["max_amount"]:
                return float(tier["threshold"])
        return 70.0  # default low tier

    def classify(self, score: float, threshold: float) -> str:
        """Classify a transaction based on its score vs threshold.

        Returns one of: 'legitimate', 'review', 'fraud'.
        """
        if score > threshold:
            return "fraud"
        if score == threshold:
            return "review"
        return "legitimate"
