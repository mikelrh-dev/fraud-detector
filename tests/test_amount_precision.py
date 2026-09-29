"""D2-1: the scored amount and the stored amount must be the same number.

`Transaction.amount` is a `Numeric(12, 2)` column, but `TransactionCreate`
accepted an unbounded `float`. The endpoint scored the raw float and then
handed the same float to the ORM, so the database rounded it on the way in:

    amount=1000.005
      scored on  1000.005  -> tier "low"      -> threshold 70
      stored as Decimal('1000.01')  -> tier "medium" -> threshold 50

The persisted row therefore records a threshold its own stored amount
contradicts, and the `threshold` column says 70 while the amount says the tier
is 50. An ensemble score of 52 is `fraud` against 50 and `legitimate` against
70, and the classification that gets written is the one computed from the
pre-rounding float.

This module asserts the invariant rather than a single value: for any amount,
the threshold the scorer derives must be the threshold the stored value
derives. A test that pins one magic number passes the moment someone changes
the tier table; an invariant does not.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal

import pytest

from src.schemas.transaction import TransactionCreate
from src.services.ensemble import EnsembleScorer

#: What the database does to a `Numeric(12, 2)` on insert. PostgreSQL rounds
#: ties away from zero; modelled explicitly here so the test does not depend
#: on a live round trip, which D7-1-style work is not allowed to need.
CENTS = Decimal("0.01")


def stored_amount(value: float) -> Decimal:
    """The value a `Numeric(12, 2)` column would actually hold."""
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


def make_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "amount": 10.0,
        "currency": "USD",
        "merchant_name": "Test Merchant",
        "merchant_category": "retail",
        "card_last4": "4242",
    }
    base.update(overrides)
    return base


#: 3-decimal values sitting on the tier boundaries found in the audit
#: (1000 / 10000 / 50000), plus interior and extreme values. 19 of the
#: divergent values the audit found were of this shape.
DIVERGENT_AMOUNTS = [
    1000.005,
    1000.015,
    9999.995,
    10000.005,
    10000.015,
    49999.995,
    50000.005,
    50000.015,
    99999.999,
    0.005,
    0.015,
    12345.675,
    7.775,
    3.335,
    0.125,
    1.115,
    99.995,
    1234.567,
    98765.431,
]


class TestAmountPrecisionInvariant:
    def test_three_decimal_amounts_never_diverge_between_scored_and_stored(self):
        """The defect: a 3-decimal amount crosses a tier only after rounding.

        Before the fix the scored tier and the stored tier differ for every
        value in this list whose fractional part rounds it across a boundary,
        which is the whole point of the list.
        """
        scorer = EnsembleScorer()
        divergent: list[str] = []

        for raw in DIVERGENT_AMOUNTS:
            payload = TransactionCreate(**make_payload(amount=raw))  # type: ignore[arg-type]
            scored_threshold = scorer.get_threshold(payload.amount)
            persisted_threshold = scorer.get_threshold(float(stored_amount(payload.amount)))
            if scored_threshold != persisted_threshold:
                divergent.append(
                    f"{raw!r}: scored {payload.amount!r} -> {scored_threshold}, "
                    f"stored {stored_amount(payload.amount)!r} -> {persisted_threshold}"
                )

        assert divergent == [], (
            "scored amount and stored amount select different threshold tiers:\n"
            + "\n".join(divergent)
        )

    def test_boundary_value_scores_on_the_tier_it_is_stored_in(self):
        """The audit's worked example, asserted as a concrete value.

        1000.005 stores as 1000.01, which is the medium tier (>= 1000.01,
        threshold 50). Scoring it on the raw float picked the low tier
        (threshold 70).
        """
        payload = TransactionCreate(**make_payload(amount=1000.005))  # type: ignore[arg-type]
        assert stored_amount(payload.amount) == Decimal("1000.01")
        assert EnsembleScorer().get_threshold(payload.amount) == 50.0

    def test_ensemble_of_52_is_not_legitimate_under_its_own_stored_amount(self):
        """The end-to-end consequence the audit described.

        Score 52 with a stored amount of 1000.01: fraud against the medium
        tier's threshold of 50, legitimate against the low tier's 70.
        """
        payload = TransactionCreate(**make_payload(amount=1000.005))  # type: ignore[arg-type]
        scorer = EnsembleScorer()
        threshold = scorer.get_threshold(payload.amount)
        assert scorer.classify(52.0, threshold) == "fraud"


class TestAmountQuantization:
    def test_three_decimals_are_quantized_at_the_schema_boundary(self):
        """Quantize, so the scored value IS the stored value."""
        payload = TransactionCreate(**make_payload(amount=1000.005))  # type: ignore[arg-type]
        assert payload.amount == pytest.approx(1000.01)

    def test_ties_round_away_from_zero_like_the_column(self):
        """Not banker's rounding.

        Python's built-in `round()` is round-half-to-even, so `round(0.125, 2)`
        is 0.12 while PostgreSQL stores 0.13 for a Numeric(12,2). Using
        `round()` here would have reproduced the same class of divergence one
        rounding mode over.
        """
        assert TransactionCreate(**make_payload(amount=0.125)).amount == pytest.approx(0.13)  # type: ignore[arg-type]
        assert stored_amount(0.125) == Decimal("0.13")

    def test_two_decimal_amounts_are_untouched(self):
        payload = TransactionCreate(**make_payload(amount=1234.56))  # type: ignore[arg-type]
        assert payload.amount == pytest.approx(1234.56)

    def test_integer_amounts_are_untouched(self):
        payload = TransactionCreate(**make_payload(amount=1000))  # type: ignore[arg-type]
        assert payload.amount == pytest.approx(1000.0)

    def test_amount_is_idempotent(self):
        """Quantizing an already-quantized value must not move it again.

        `Decimal.quantize` on a float is exact enough at these magnitudes, but
        idempotence is the property that makes the fix safe to apply twice if
        a future consumer also normalizes.
        """
        once = TransactionCreate(**make_payload(amount=9999.999)).amount  # type: ignore[arg-type]
        twice = TransactionCreate(**make_payload(amount=once)).amount  # type: ignore[arg-type]
        assert twice == pytest.approx(once)

    def test_amount_rounding_to_zero_is_rejected(self):
        """0.001 cannot be represented in a Numeric(12,2).

        Accepting it and quantizing to 0.00 would defeat the column's
        NOT NULL positive-amount intent and let a request persist a
        zero-value transaction. There is no value to round to, so the
        request is refused instead.
        """
        with pytest.raises(ValueError):
            TransactionCreate(**make_payload(amount=0.001))  # type: ignore[arg-type]

    def test_user_id_is_still_accepted(self):
        """The quantization must not disturb the other fields."""
        payload = TransactionCreate(  # type: ignore[arg-type]
            **make_payload(amount=10.005, user_id=uuid.uuid4())
        )
        assert isinstance(payload.user_id, uuid.UUID)
        assert payload.amount == pytest.approx(10.01)
