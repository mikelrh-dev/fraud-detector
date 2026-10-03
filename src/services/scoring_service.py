"""Fraud scoring pipeline service (CV-001: scores are computed in services).

Owns the deterministic scoring pipeline: rule engine -> feature engineering
-> ML model -> ensemble combination. The API endpoint gathers inputs (I/O)
and delegates computation here; CPU-bound steps run via ``asyncio.to_thread``
at the call site so the event loop is never blocked (CV-002).
"""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.core.config import settings
from src.core.counters import degraded_ml_layer
from src.services.ensemble import EnsembleScorer
from src.services.feature_engine import FeatureEngine
from src.services.ml_model import MLModelService
from src.services.rule_engine import RuleEngine

logger = logging.getLogger(__name__)


def _critical_floor() -> float:
    """The amount at or above which rule evidence alone is enough to block.

    Read from the last threshold tier rather than written down here: the floor
    IS the critical tier's lower boundary, so the two cannot drift apart when
    an operator reconfigures the tiers. Note the boundary is **50000.01**, not
    50000 — the tiers are half-open `[min, max)` and the high tier runs up to
    50000.01 inclusive, so 50000.00 is a high-tier amount and 50000.01 is the
    first critical one.

    Read at call time rather than at import so an env override of the tier
    table takes effect the way it does in ``EnsembleScorer.get_threshold``.
    """
    return float(settings.threshold_tiers[-1]["min_amount"])


def _meets_critical_floor(amount: object) -> bool:
    """Whether `amount` reaches the critical floor. Total: never raises.

    The routed policy compares the raw amount against the floor, and a raw amount
    is the one value here that arrives from outside the type system: `amount >=
    FLOOR` raises `TypeError` on a string, and on NaN it evaluates False while
    `inf` evaluates True — so a broken amount would silently become either a
    block or nothing, depending on which flavour of broken it was.

    An amount that cannot be compared must make the gate False. Not True: "the
    amount is critical" is a claim about a number, and an unreadable amount is
    missing evidence for that claim rather than evidence for it. Closing the
    gate leaves the route the rules already earned — `rule > threshold` on its
    own is a `review` — which matches `EnsembleScorer.get_threshold`, already
    failing closed on a non-finite amount.

    `None` and unparseable strings land on 0.0 through `_to_float`, and 0.0 is
    below every floor; a numeric string like `"60000"` is genuinely a critical
    amount and is allowed through, because refusing it would be inventing a
    different verdict for a value that does parse.
    """
    value = _to_float(amount)
    return math.isfinite(value) and value >= _critical_floor()


def _to_float(value: object) -> float:
    """Total numeric conversion; never raises."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _to_finite_float(value: object) -> float:
    """Like ``_to_float`` but also maps NaN/±inf to 0.0.

    ``_to_float`` happily returns NaN because ``float("nan")`` succeeds, and a
    NaN then poisons every downstream comparison. Use this for values that
    reach arithmetic (velocity counts, history stats) rather than for values
    that are only compared.
    """
    result = _to_float(value)
    return result if math.isfinite(result) else 0.0


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
    # A15: which layers actually contributed to this score. Recorded so a score
    # computed with a missing layer is distinguishable from a full one after the
    # fact, instead of being a number that is quietly 25 points low.
    layers_used: tuple[str, ...] = ("rule", "ml", "context")


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

    def _classify_routed(
        self,
        rule_score: float,
        ml_score: float | None,
        context_score: float,
        threshold: float,
        amount: float,
    ) -> str:
        """Route on the layers, not on their weighted average.

        R2. This replaces ``EnsembleScorer.classify(ensemble_score, threshold)``,
        which made one number decide for three signals. The problem was that the
        weights, not the evidence, ended up arbitrating:

        - The model holds 0.25 of the ensemble, so ``ml_score`` 85 against a
          quiet rule layer produced an ensemble of 21.25 against a threshold of
          70 — ``legitimate``. The model's veto was multiplied down by the very
          weight it holds before being compared. Here the layer is compared to
          the threshold directly, so an ML-only signal can block.
        - Symmetrically, rules scoring 100 on a 400k transfer were diluted to
          64.49 and then had to clear a threshold calibrated for one number.
          Here the rule layer clears the threshold on its own evidence, so long
          as the amount is one where blocking is proportionate.

        The bands:

            fraud      ml > threshold, OR (rule > threshold AND amount >= FLOOR)
            review     not fraud, and (rule > threshold OR ml > threshold * 0.75)
            legitimate otherwise

        The FLOOR is what keeps the rule branch proportionate: a rule-strong
        purchase BELOW the critical amount is a `review` for an analyst, never a
        block. That is the intended downgrade, and it is why the rule branch
        cannot be a plain veto the way the ML branch is — the rules speak in
        patterns and a pattern firing on a small purchase is not evidence that
        the purchase itself is worth blocking.

        DEGRADED: the bands above only apply when the model is up. ``ml_score``
        is ``None`` when the artifact failed to load, and then there is no ML
        layer to route against — the bands would be deciding with one layer
        missing, which is a second scoring policy that only runs when the system
        is already broken. So an absent layer falls back to exactly the shipped
        path: the A15 ensemble (weights redistributed across the layers that did
        produce a value) and the same threshold. Degraded verdicts are therefore
        unchanged, which is the only defensible reading of "unchanged": the
        routed policy is for when both layers are present, not a new behaviour
        to discover during an outage.
        """
        if ml_score is None:
            return self.ensemble_scorer.classify(
                self.ensemble_scorer.combine(
                    rule_score=rule_score,
                    ml_score=None,
                    context_score=context_score,
                ),
                threshold,
            )

        # A non-finite ml_score cannot be compared to anything. `NaN > x` is
        # False, so leaving it unguarded would silently *drop* the veto —
        # failing open on a layer that produced garbage. `EnsembleScorer.classify`
        # already fails closed on a non-finite score; this keeps that stance.
        ml_speaks = math.isfinite(ml_score)

        rule_clears = rule_score > threshold
        ml_clears = ml_speaks and ml_score > threshold

        if ml_clears or (rule_clears and _meets_critical_floor(amount)):
            return "fraud"
        if rule_clears or (ml_speaks and ml_score > threshold * 0.75):
            return "review"
        return "legitimate"

    async def compute_scores(
        self,
        tx_data: dict[str, Any],
        context: dict[str, Any],
        user_history: dict[str, float],
    ) -> ScoringResult:
        """Run the full deterministic pipeline.

        CPU-bound steps (feature engineering, ML predict) are offloaded to
        a thread so the event loop is never blocked (CV-002).

        There is no database session and no monitoring collaborator here, by
        decision rather than by omission. Both the ``monitoring_service``
        parameter and the ``db`` parameter it needed were removed on
        2026-10-01: see ``docs/plans/2026-10-01-monitoring-desenmascarar.md``
        (W2) and ``src/services/__init__.py``. Recording a model run would
        have meant one ``ml_model_runs`` row per scored transaction — a table
        documented as a record of a model *training run* — with ``status``,
        ``drift_detected`` and ``model_version`` all constant, so the hook
        could only ever write decoration. If you are adding a per-transaction
        audit row, that is a new table and a new reason; do not resurrect this
        one.
        """
        # CPU-bound: rule engine + feature engine + ML predict
        def _compute() -> tuple[float, list[str], np.ndarray, float | None]:
            rule_score, fired_rules = self.rule_engine.evaluate(tx_data, context)
            features = self.feature_engine.transform(tx_data, user_history=user_history)

            # A15: a layer with no signal must be reported as None, not 0.0.
            # When the model is not loaded, `predict` returns 0.0, which is
            # indistinguishable from "the model ran and this looks legitimate".
            # Passing 0.0 through consumed the ML layer's 0.25 weight anyway, so
            # every score lost 25 points with the model down — silently, and
            # worst exactly when the system was already degraded. None tells
            # the ensemble to redistribute that weight to the layers that did
            # produce a value.
            if not self.ml_service.is_available:
                logger.warning(
                    "ML model not loaded — reporting the ML layer as absent so "
                    "its weight is redistributed instead of lost"
                )
                return rule_score, fired_rules, features, None

            try:
                ml_score = _to_float(self.ml_service.predict(features))
            except ValueError as exc:
                # A shape mismatch is a real failure of a layer that *is*
                # present, so it is not "no signal": keep the weight and report
                # the zero, and let the operator see the warning.
                logger.warning("Feature shape mismatch in ML predict — returning 0.0: %s", exc)
                ml_score = 0.0
            return rule_score, fired_rules, features, ml_score

        rule_score, fired_rules, features, ml_score = await asyncio.to_thread(_compute)

        # Compute context score from velocity signal (ML3).
        # recent_transactions feeds arithmetic, so it must be finite: a NaN here
        # propagated into the ensemble and classified the transaction as
        # legitimate, because every `NaN > threshold` comparison is False.
        recent_txns = _to_finite_float(
            context.get("recent_transactions", 0) if context else 0
        )
        context_score = min(recent_txns / 10.0 * 100, 100.0)

        amount = tx_data.get("amount", 0)
        threshold = self.ensemble_scorer.get_threshold(amount)
        ensemble_score = self.ensemble_scorer.combine(
            rule_score=rule_score,
            ml_score=ml_score,
            context_score=context_score,
        )
        classification = self._classify_routed(
            rule_score=rule_score,
            ml_score=ml_score,
            context_score=context_score,
            threshold=threshold,
            amount=amount,
        )

        # A15: the ML layer is absent from the arithmetic but its stored value
        # stays a float, because FraudScore.ml_score is a non-nullable column
        # and turning this into None would mean a migration. The gap between the
        # two is recorded in `layers_used` instead of being invisible.
        persisted_ml_score = ml_score if ml_score is not None else 0.0
        layers_used = tuple(
            name
            for name, value in (
                ("rule", rule_score),
                ("ml", ml_score),
                ("context", context_score),
            )
            if value is not None
        )
        if ml_score is None:
            degraded_ml_layer.inc()

        return ScoringResult(
            rule_score=rule_score,
            fired_rules=list(fired_rules),
            features=features,
            ml_score=persisted_ml_score,
            threshold=threshold,
            ensemble_score=ensemble_score,
            classification=classification,
            layers_used=layers_used,
        )
