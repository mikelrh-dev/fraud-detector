"""Pydantic schemas for fraud scoring responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ScoreResponse(BaseModel):
    """Full scoring breakdown returned after transaction scoring."""

    transaction_id: uuid.UUID
    rule_score: float
    ml_score: float
    ensemble_score: float
    threshold: float
    classification: str
    fired_rules: list[str]

    #: Which ensemble layers contributed to THIS score, in evaluation order
    #: (a subset of ``rule``, ``ml``, ``context``).
    #:
    #: WHY THIS IS A FIELD AND NOT A NULL. A missing layer is recorded here
    #: rather than by nulling its score, because ``ml_score`` cannot be
    #: nulled: ``FraudScore.ml_score`` is a non-nullable column and changing
    #: that is a migration. A15 (services/scoring_service.py) resolved it the
    #: other way — when the model is not loaded the ensemble redistributes its
    #: 0.25 weight to the layers that did produce a value, and the stored score
    #: stays ``0.0``. A degraded score is therefore an ordinary-looking number,
    #: and this field is the only thing that distinguishes it from a complete
    #: one: ``"ml" in layers_used`` is TRUE when the model ran and genuinely
    #: scored zero, and FALSE when it never ran at all.
    #:
    #: Computed and carried by ``ScoringResult`` since A15, where it stopped at
    #: the dataclass and never reached the wire. Exposed here rather than
    #: persisted: storing it needs a column, and a migration cannot be tested
    #: without a live database (see ``docs/plans/2026-09-28-fix-loop.md``,
    #: D7-1). Until that lands, ``GET /transactions/{id}`` cannot report it —
    #: it reads a stored row and there is no column to read.
    layers_used: list[str]

    created_at: datetime

    # Dynamic friction based on score and classification
    friction_level: str  # ALLOW | CHALLENGE | BLOCK
    action: str | None = None  # request_3d_secure | request_sms | request_biometric | block_transaction

    model_config = {"from_attributes": True}
