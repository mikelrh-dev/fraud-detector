"""Pydantic schemas for transaction CRUD operations."""

import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field, field_validator

from src.core.ml_constants import KNOWN_MERCHANT_CATEGORIES, normalize_category

#: The storage resolution of `Transaction.amount` (a Numeric(12, 2) column).
#: Anything finer than this cannot survive a round trip through the database.
AMOUNT_QUANTUM = Decimal("0.01")


class TransactionCreate(BaseModel):
    """Payload for creating a new transaction."""

    # Upper bound mirrors the Numeric(12,2) column. Without it, `inf` was
    # accepted, matched no threshold tier (the test is `amount < max_amount`
    # and the last tier's max is math.inf), and scored as legitimate.
    amount: float = Field(
        ...,
        gt=0,
        le=9_999_999_999.99,
        allow_inf_nan=False,
        description="Transaction amount",
    )

    @field_validator("amount")
    @classmethod
    def _quantize_to_column_resolution(cls, value: float) -> float:
        """Round the amount to what the column can actually hold.

        D2-1. The endpoint scored the raw float and then handed the same float
        to a Numeric(12, 2) column, so the number that was scored and the
        number that was persisted were different numbers at every tier
        boundary:

            amount=1000.005  ->  scored 1000.005   (low tier,    threshold 70)
                               stored 1000.01    (medium tier, threshold 50)

        The row therefore recorded a threshold its own amount contradicted,
        and an ensemble of 52 was classified `legitimate` against the 70 while
        the stored amount implied 50, where the same 52 is `fraud`.

        QUANTIZE, DO NOT REJECT. The choice is deliberate and the alternative
        was weighed:

        - Rejecting a 3-decimal amount with a 422 would break a client that
          sends one today. That request is not currently an error: the column
          silently rounds it on insert, the request succeeds, and the stored
          row is exactly what the client asked for modulo half a cent. Making
          it a hard error removes a working write path to buy nothing.
        - Rounding here is not the same as rounding late. Late, the value
          changed *after* the decision that depended on it was already made.
          Here, the value is settled before anything reads it, so the scored
          number and the stored number are the same number. The client sees
          the amount it will get back on the created transaction, and the
          half-cent difference it was always going to lose is now visible in
          the request it sent rather than hidden in the response.

        Rounding is half-away-from-zero because that is what PostgreSQL's
        numeric does. Python's built-in `round()` is half-to-even, so
        `round(0.125, 2) == 0.12` while the column stores 0.13 — using it here
        would have rebuilt the same class of divergence one rounding mode
        over.

        The one case that cannot be quantized into something meaningful is a
        value that rounds to zero: Numeric(12, 2) cannot hold 0.001, and
        persisting 0.00 would defeat the positive-amount constraint the column
        encodes. That is refused, because there is no value to round to.
        """
        quantized = Decimal(str(value)).quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)
        if quantized <= 0:
            raise ValueError(
                f"amount {value!r} rounds to 0.00 at the stored resolution "
                f"({AMOUNT_QUANTUM}); the smallest representable amount is {AMOUNT_QUANTUM}"
            )
        return float(quantized)

    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")
    merchant_name: str = Field(..., min_length=1, max_length=255)

    merchant_category: str | None = Field(None, max_length=100)

    @field_validator("merchant_category")
    @classmethod
    def _reject_a_category_outside_the_vocabulary(cls, value: str | None) -> str | None:
        """D3: the field that decides the features is not free text.

        `merchant_category` drives `is_crypto` and `merchant_risk_level` (D1,
        D7-3), so whoever posts the payload chose which features fired. That is a
        design flaw rather than a logic bug: `cryptocurrency` and `retail` are
        both legitimate values and the same merchant can be honestly described
        either way, so the score depended on a string rather than on the
        transaction. An unknown value was worse than wrong — it matched no set,
        scored both features 0.0, and produced a score indistinguishable from a
        genuinely safe merchant. So the edge refuses it with a 422 and names the
        vocabulary.

        VALIDATED ON THE NORMALIZED FORM, NOT THE RAW STRING. `cripto`,
        `crypto-exchange` and `BTC` all resolve to `cryptocurrency`, and
        rejecting them would throw away the alias work D7-3 exists for — the
        frontend and the corpus both emit spellings, and the accepted input must
        match what a legitimate producer sends.

        RETURNED UNCHANGED, NOT CANONICALIZED. What the client sent is what gets
        stored and scored, and both engines already run `normalize_category`
        themselves. Rewriting it here would make the stored row disagree with
        the request that created it — the exact scored-vs-persisted divergence
        the `amount` quantizer above exists to prevent, in the other direction.

        EMPTY IS NOT AN ERROR. The column is nullable and the field is optional;
        a blank value is an incomplete record, not an attack, and it normalizes
        to `""` which is how every consumer already spells "no category".

        THIS IS NOT THE ONLY LINE OF DEFENCE. The feature engine keeps its
        unknown-category counter and warning, because the engine is also driven
        by batch and replay consumers that never pass through this endpoint —
        validating the edge does not authorise deleting the instrumentation that
        explains D1.
        """
        if value is None:
            return None
        canonical = normalize_category(value)
        if canonical == "":
            return value
        if canonical not in KNOWN_MERCHANT_CATEGORIES:
            raise ValueError(
                f"merchant_category {value!r} is not a known category "
                f"(it normalizes to {canonical!r}). Accepted values are "
                f"KNOWN_MERCHANT_CATEGORIES in src/core/ml_constants.py, plus "
                f"any spelling CATEGORY_ALIASES normalizes onto one of them; "
                f"the frontend selector is generated from the same set."
            )
        return value

    card_last4: str = Field(..., min_length=4, max_length=4, description="Last 4 digits of card")
    # DEPRECATED: user_id is ignored server-side (F2). The authenticated
    # user's identity is always used. Kept for backward compatibility with
    # existing clients; will be removed in a future version.
    user_id: uuid.UUID | None = Field(None, deprecated="Ignored — server uses authenticated user identity")


class ShapContribution(BaseModel):
    """A single feature contribution computed by SHAP (FRD-SHP-001).

    Ordered by rank in the detail response; signed contribution —
    positive pushes toward fraud, negative toward legitimate.
    """

    feature: str
    contribution: float


class ScoreBreakdown(BaseModel):
    """Scoring breakdown nested in transaction responses.

    Mirrors ScoreResponse minus transaction_id/created_at/fired_rules
    (fired_rules is not persisted in fraud_scores).
    """

    rule_score: float
    ml_score: float
    ensemble_score: float
    threshold: float
    classification: str

    shap_contributions: list[ShapContribution] | None = None

    model_config = {"from_attributes": True}  # enables model_validate(FraudScore)


class TransactionResponse(BaseModel):
    """Transaction details returned to clients."""

    id: uuid.UUID
    amount: float
    currency: str
    merchant_name: str
    merchant_category: str | None
    card_last4: str
    status: str
    risk_score: float | None = None
    classification: str | None = None
    scoring: ScoreBreakdown | None = None
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    """Paginated list of transactions."""

    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int
