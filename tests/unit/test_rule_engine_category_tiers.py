"""A14: a regulated merchant category is not evidence on its own.

``unusual_merchant`` fired on ``category in MERCHANT_RISK_CATEGORIES`` with no
other condition, so every pharmacy purchase and every remittance carried a flat
20 rule points. The category is not a risk claim for those businesses — it is
what they are — and 20 points of class bias on a whole class of legitimate
merchants is 20 points of systematic false positives.

Worse in combination: ``velocity_burst`` (30) and the night-time rules stack on
the same field, so a single ``pharmacy`` at 03:00 with 2 transactions in 5
minutes reached 85/100 from category and clock alone.

The adversarial tier (crypto, gambling, casino, adult) still stands on its own,
because there the category *is* the claim.
"""

import pytest

from src.core.ml_constants import (
    MERCHANT_ADVERSARIAL_CATEGORIES,
    MERCHANT_REGULATED_CATEGORIES,
    MERCHANT_RISK_CATEGORIES,
)
from src.services.rule_engine import RuleEngine

NIGHT = "2026-09-27T03:00:00+00:00"
DAY = "2026-09-27T14:00:00+00:00"


@pytest.fixture
def engine() -> RuleEngine:
    return RuleEngine()


def tx(category: str, **overrides: object) -> dict:
    payload: dict = {
        "amount": 500.0,
        "merchant_name": "Comercio",
        "merchant_category": category,
        "timestamp": DAY,
    }
    payload.update(overrides)
    return payload


class TestTiers:
    def test_the_two_tights_partition_the_original_set(self) -> None:
        assert (
            MERCHANT_ADVERSARIAL_CATEGORIES | MERCHANT_REGULATED_CATEGORIES
        ) == MERCHANT_RISK_CATEGORIES, (
            "the tiers must cover exactly what the single set covered, or a "
            "category silently stops being considered anywhere"
        )

    def test_the_feature_engine_contract_is_unchanged(self) -> None:
        """A14 must not shift the model's input distribution.

        MERCHANT_RISK_CATEGORIES is also the feature-engine's contract
        (merchant_risk_level, is_crypto) and the training scripts generate from
        it. Changing that set would have retrained the model by accident.
        """
        assert "pharmacy" in MERCHANT_RISK_CATEGORIES
        assert "money_transfer" in MERCHANT_RISK_CATEGORIES

    @pytest.mark.parametrize("category", sorted(MERCHANT_REGULATED_CATEGORIES))
    def test_regulated_alone_does_not_fire(
        self, engine: RuleEngine, category: str
    ) -> None:
        score, fired = engine.evaluate(tx(category))
        assert "unusual_merchant" not in fired
        assert score == 0.0

    @pytest.mark.parametrize("category", sorted(MERCHANT_ADVERSARIAL_CATEGORIES))
    def test_adversarial_alone_does_fire(
        self, engine: RuleEngine, category: str
    ) -> None:
        _, fired = engine.evaluate(tx(category))
        assert "unusual_merchant" in fired


class TestRegulatedNeedsCorroboration:
    @pytest.mark.parametrize("category", sorted(MERCHANT_REGULATED_CATEGORIES))
    def test_velocity_corroborates(self, engine: RuleEngine, category: str) -> None:
        _, fired = engine.evaluate(tx(category), {"recent_transactions": 5})
        assert "unusual_merchant" in fired

    @pytest.mark.parametrize("category", sorted(MERCHANT_REGULATED_CATEGORIES))
    def test_night_hour_corroborates(self, engine: RuleEngine, category: str) -> None:
        _, fired = engine.evaluate(tx(category, timestamp=NIGHT))
        assert "unusual_merchant" in fired

    @pytest.mark.parametrize("category", sorted(MERCHANT_REGULATED_CATEGORIES))
    def test_single_prior_transaction_is_not_corroboration(
        self, engine: RuleEngine, category: str
    ) -> None:
        """One prior transaction is normal; the threshold is the same as
        velocity_burst's, so the two rules cannot both claim the same evidence
        as if it were two independent signals."""
        _, fired = engine.evaluate(tx(category), {"recent_transactions": 1})
        assert "unusual_merchant" not in fired


class TestBlacklistIsUnaffected:
    def test_blacklisted_merchant_still_fires(self, engine: RuleEngine) -> None:
        _, fired = engine.evaluate(
            tx("grocery", merchant_name="Bad Shop"),
            {"merchant_blacklist": ["Bad Shop"]},
        )
        assert "unusual_merchant" in fired

    def test_blacklisted_pharmacy_still_fires(self, engine: RuleEngine) -> None:
        _, fired = engine.evaluate(
            tx("pharmacy", merchant_name="Bad Pharmacy"),
            {"merchant_blacklist": ["Bad Pharmacy"]},
        )
        assert "unusual_merchant" in fired


class TestStackedBiasIsGone:
    def test_a_quiet_daytime_pharmacy_scores_zero(self, engine: RuleEngine) -> None:
        score, fired = engine.evaluate(tx("pharmacy"))
        assert score == 0.0
        assert fired == []

    def test_pharmacy_at_night_with_velocity_still_scores_high(
        self, engine: RuleEngine
    ) -> None:
        """Custody must not mean ignoring: the signals still add up."""
        score, fired = engine.evaluate(
            tx("pharmacy", timestamp=NIGHT), {"recent_transactions": 5}
        )
        assert score >= 55.0
        assert {"unusual_merchant", "high_velocity"} <= set(fired)

    def test_no_single_regulated_category_reaches_the_fraud_threshold(self) -> None:
        """The original defect, scoped to the tier that caused it.

        A single category plus a low amount plus a night hour must not, on its
        own, carry a pharmacy or a remittance to the fraud threshold.
        """
        engine = RuleEngine()
        worst = 0.0
        for category in MERCHANT_REGULATED_CATEGORIES:
            score, _ = engine.evaluate(
                tx(category, amount=50.0, timestamp=NIGHT),
                {"recent_transactions": 2},
            )
            worst = max(worst, score)
        assert worst < 70.0, (
            f"a regulated category alone reached {worst}, the fraud threshold; "
            "it must not be able to carry a score by itself"
        )

    def test_the_adversarial_tier_still_stacks_by_design(self) -> None:
        """Crypto at 03:00 with rapid transactions is card testing.

        This is the behaviour the adversarial tier exists for, and the fix must
        not weaken it. Recorded explicitly so a future change that flattens this
        is a deliberate decision rather than an accident.
        """
        engine = RuleEngine()
        score, fired = engine.evaluate(
            tx("cryptocurrency", amount=50.0, timestamp=NIGHT),
            {"recent_transactions": 2},
        )
        assert score >= 70.0
        assert {
            "unusual_merchant",
            "velocity_burst",
            "unusual_hours",
            "off_hours_crypto",
        } <= set(fired)
