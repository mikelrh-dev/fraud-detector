"""Fraud scoring pipeline service (CV-001: scores are computed in services).

Owns the deterministic scoring pipeline: rule engine -> feature engineering
-> ML model -> ensemble combination. The API endpoint gathers inputs (I/O)
and delegates computation here; CPU-bound steps run via ``asyncio.to_thread``
at the call site so the event loop is never blocked (CV-002).
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.services.ensemble import EnsembleScorer
from src.services.feature_engine import FeatureEngine
from src.services.ml_model import MLModelService
from src.services.rule_engine import RuleEngine


def _to_float(value: object) -> float:
    """Total numeric conversion; never raises."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


@dataclass
class ScoringResult:
    """Outcome of one full scoring pass."""

    rule_score: float
    fired_rules: list[str] = field(default_factory=list)
    features: np.ndarray = field(default_factory=lambda: np.empty(0))
    ml_score: float = 0.0
    threshold: float = 0.0
    ensemble_score: float = 0.0
    classification: str = "legitimate"


class ScoringService:
    """Coordinates rule engine, feature engine, ML model and ensemble."""

    def __init__(
        self,
        rule_engine: RuleEngine | None = None,
        feature_engine: FeatureEngine | None = None,
        ml_service: MLModelService | None = None,
        ensemble_scorer: EnsembleScorer | None = None,
    ) -> None:
        self.rule_engine = rule_engine or RuleEngine()
        self.feature_engine = feature_engine or FeatureEngine()
        self.ml_service = ml_service or MLModelService()
        self.ensemble_scorer = ensemble_scorer or EnsembleScorer()

    @staticmethod
    def compute_user_history_stats(amounts: list[Any]) -> dict[str, float]:
        """avg/std over past amounts; tolerates Decimal and empty input."""
        values = [_to_float(a) for a in amounts]
        return {
            "avg_amount": _to_float(np.mean(values)) if values else 0.0,
            "std_amount": _to_float(np.std(values)) if len(values) > 1 else 0.0,
        }

    def compute_scores(
        self,
        tx_data: dict[str, Any],
        context: dict[str, Any],
        user_history: dict[str, Any],
    ) -> ScoringResult:
        """Run the full deterministic pipeline (CPU-bound; call via to_thread)."""
        rule_score, fired_rules = self.rule_engine.evaluate(tx_data, context)

        features = self.feature_engine.transform(tx_data, user_history=user_history)
        ml_score = _to_float(self.ml_service.predict(features))

        amount = tx_data.get("amount", 0)
        threshold = self.ensemble_scorer.get_threshold(amount)
        ensemble_score = self.ensemble_scorer.combine(
            rule_score=rule_score,
            ml_score=ml_score,
        )
        classification = self.ensemble_scorer.classify(ensemble_score, threshold)

        return ScoringResult(
            rule_score=rule_score,
            fired_rules=list(fired_rules),
            features=features,
            ml_score=ml_score,
            threshold=threshold,
            ensemble_score=ensemble_score,
            classification=classification,
        )
