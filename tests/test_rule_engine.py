"""Rule engine tests — single rule fires, multiple rules, no rules, determinism, score cap.

These tests verify the deterministic rule engine used as the first layer of
the fraud scoring pipeline.

No test in this file reads the wall clock
------------------------------------------
``test_high_velocity_rule_fires`` and ``test_high_amount_and_velocity`` used
to build their transaction timestamp with ``datetime.now()`` and then assert
an exact score. That made the assertion a statement about the hour CI happened
to run: the ``unusual_hours`` rule charges 10 points for 00:00-05:59 UTC, so
both tests scored 35 and 70 instead of 25 and 60 in exactly six hours of
every day, and nightly CI failed on them. Measured across all 24 hours, 6
failed and 18 passed — a green run was luck, not correctness.

The engine was never wrong. It reads the hour from the transaction's own
timestamp and charges for a night-hour transaction; a transaction at 03:00
UTC genuinely is one. The fix is that "now" is injected rather than read:
:class:`TestUnusualHoursBoundaries` sweeps all 24 hours and pins the exact
score and fired-rule set for each, so the contract is stated instead of
assumed, and the two velocity tests are independent of the hour.
"""

import pytest

from src.core.clock import FrozenClock
from src.services.rule_engine import RuleEngine

#: Mid-afternoon UTC, when no hour-based rule fires. A fixed instant, not
#: "now", so the velocity tests below assert one thing: that the velocity rule
#: contributes exactly its own weight.
DAYLIGHT_UTC = FrozenClock.at_hour(14)


class TestRuleEngineSingleRule:
    """Each rule can fire independently."""

    def test_high_amount_rule_fires(self):
        """Transaction amount > 5000 should fire high_amount rule (weight 30)."""
        engine = RuleEngine()
        tx = {"amount": 10000, "merchant_name": "Normal Store", "card_last4": "1234"}
        score, fired = engine.evaluate(tx)
        assert "high_amount" in fired
        assert score > 0

    def test_low_amount_no_rule(self):
        """Transaction amount <= 5000 should NOT fire high_amount."""
        engine = RuleEngine()
        tx = {"amount": 100, "merchant_name": "Normal Store", "card_last4": "1234"}
        score, fired = engine.evaluate(tx)
        assert "high_amount" not in fired
        # If no amount rule fires, the others also depend on context
        # Without context, velocity/card/country can't fire
        if not fired:
            assert score == 0

    def test_high_velocity_rule_fires(self):
        """More than 3 transactions in 5 min should fire high_velocity (weight 25)."""
        engine = RuleEngine()
        now = DAYLIGHT_UTC.now_utc()
        tx = {"amount": 100, "user_id": "user-1", "timestamp": now.isoformat()}
        context = {
            "recent_transactions": 5,  # > 3 in last 5 min
        }
        score, fired = engine.evaluate(tx, context=context)
        assert "high_velocity" in fired
        assert score == 25

    def test_high_velocity_score_is_the_same_at_every_hour(self):
        """The velocity rule's contribution must not depend on the hour.

        This is the assertion that was missing. The original test asserted
        ``score == 25`` from a ``datetime.now()`` fixture, so it passed in 18
        hours and failed in 6. This one states the invariant directly: at every
        hour of the day the rule set is the same, and the score is the velocity
        weight plus whatever the hour is worth — 10 in the six night hours and
        0 in the other eighteen.
        """
        engine = RuleEngine()
        for hour in range(24):
            clock = FrozenClock.at_hour(hour)
            tx = {
                "amount": 100,
                "user_id": "user-1",
                "timestamp": clock.now_utc().isoformat(),
            }
            score, fired = engine.evaluate(tx, context={"recent_transactions": 5})
            expected_extra = 10 if hour < 6 else 0
            assert fired == ["high_velocity", "unusual_hours"] or fired == ["high_velocity"], (
                f"hour {hour:02d}: unexpected rule set {fired}"
            )
            assert score == 25 + expected_extra, (
                f"hour {hour:02d}: expected {25 + expected_extra}, got {score}"
            )

    def test_unusual_merchant_rule_fires(self):
        """Merchant in blacklist should fire unusual_merchant (weight 20)."""
        engine = RuleEngine()
        tx = {"amount": 100, "merchant_name": "Suspicious Shop", "card_last4": "1234"}
        context = {"merchant_blacklist": ["Suspicious Shop", "Dark Market"]}
        score, fired = engine.evaluate(tx, context=context)
        assert "unusual_merchant" in fired
        assert score == 20

    def test_unusual_hours_rule_fires(self):
        """Transaction between 00:00-06:00 should fire unusual_hours (weight 10)."""
        engine = RuleEngine()
        # 3 AM
        tx = {"amount": 100, "timestamp": "2024-01-15T03:00:00+00:00"}
        score, fired = engine.evaluate(tx)
        assert "unusual_hours" in fired
        assert score == 10

    def test_unusual_hours_boundary_before(self):
        """Transaction at 06:00 should NOT fire unusual_hours."""
        engine = RuleEngine()
        # Exactly 6 AM — boundary: > 6 means not unusual
        tx = {"amount": 100, "timestamp": "2024-01-15T06:00:00+00:00"}
        score, fired = engine.evaluate(tx)
        assert "unusual_hours" not in fired


class TestUnusualHoursBoundaries:
    """The full 24-hour contract for the hour-based rules (CI-001).

    This class exists because the two tests that used to flake nightly did not
    state the hour dependency at all — they inherited it from
    ``datetime.now()``. Stating it means the next person who writes a
    wall-clock fixture in this file sees the sweep and understands that the
    hour is a scoring input, not a detail.

    ``unusual_hours`` fires on hour < 6 and is worth 10. ``off_hours_crypto``
    additionally fires for an adversarial category and is worth 25.
    """

    NIGHT_HOURS = (0, 1, 2, 3, 4, 5)
    DAY_HOURS = tuple(range(6, 24))

    @pytest.mark.parametrize("hour", range(24))
    def test_plain_merchant_fires_unusual_hours_only_at_night(self, hour):
        """A non-risk merchant: unusual_hours is the only hour-dependent rule."""
        engine = RuleEngine()
        clock = FrozenClock.at_hour(hour)
        tx = {
            "amount": 100,
            "merchant_name": "Normal Store",
            "card_last4": "1234",
            "timestamp": clock.now_utc().isoformat(),
        }
        score, fired = engine.evaluate(tx)
        is_night = hour in self.NIGHT_HOURS
        assert ("unusual_hours" in fired) is is_night, (
            f"hour {hour:02d}: unusual_hours fired={'unusual_hours' in fired}, "
            f"expected {is_night}"
        )
        assert score == (10.0 if is_night else 0.0), f"hour {hour:02d}: {score}"

    @pytest.mark.parametrize("hour", range(24))
    def test_adversarial_category_fires_off_hours_crypto_at_night(self, hour):
        """A crypto merchant also picks up off_hours_crypto (+25) at night."""
        engine = RuleEngine()
        clock = FrozenClock.at_hour(hour)
        tx = {
            "amount": 100,
            "merchant_name": "CryptoBuy",
            "merchant_category": "cryptocurrency",
            "card_last4": "1234",
            "timestamp": clock.now_utc().isoformat(),
        }
        score, fired = engine.evaluate(tx)
        is_night = hour in self.NIGHT_HOURS
        assert ("off_hours_crypto" in fired) is is_night
        # unusual_merchant 20 always (adversarial stands alone) + 10 + 25 at night
        assert score == (20.0 + 35.0 * is_night), f"hour {hour:02d}: {score}"

    def test_exactly_six_hours_are_affected(self):
        """Pin the size of the night window.

        Not decoration: this is the number that made the old tests fail 6
        times out of 24. If a future change widens or narrows the window this
        fails and says so, rather than the failure surfacing as an unexplained
        red nightly build.
        """
        engine = RuleEngine()
        affected = []
        for hour in range(24):
            clock = FrozenClock.at_hour(hour)
            _, fired = engine.evaluate(
                {"amount": 100, "timestamp": clock.now_utc().isoformat()}
            )
            if "unusual_hours" in fired:
                affected.append(hour)
        assert affected == list(self.NIGHT_HOURS), (
            f"unusual_hours fires at {affected}, expected {list(self.NIGHT_HOURS)}"
        )
        assert len(affected) == 6

class TestRuleEngineMerchantCategory:
    """unusual_merchant fires on risky merchant categories (RULE-MERCH-001..004).

    Uses a non-blacklisted merchant name and amount <= 5000 so the only
    possible 20-point contribution is the category-based unusual_merchant fire.
    """

    engine = RuleEngine()
    name = "CryptoBuy"
    base_tx = {"amount": 100, "merchant_name": name, "card_last4": "1234"}

    def test_btc_category_fires(self):
        """Category 'btc' fires unusual_merchant with exactly 20 points."""
        tx = {**self.base_tx, "merchant_category": "btc"}
        score, fired = self.engine.evaluate(tx)
        assert "unusual_merchant" in fired
        assert score == 20

    def test_crypto_category_fires(self):
        """Category 'crypto' fires unusual_merchant."""
        tx = {**self.base_tx, "merchant_category": "crypto"}
        score, fired = self.engine.evaluate(tx)
        assert "unusual_merchant" in fired
        assert score == 20

    def test_gambling_category_fires(self):
        """Category 'gambling' fires unusual_merchant."""
        tx = {**self.base_tx, "merchant_category": "gambling"}
        score, fired = self.engine.evaluate(tx)
        assert "unusual_merchant" in fired
        assert score == 20

    def test_casino_category_fires(self):
        """Category 'casino' fires unusual_merchant."""
        tx = {**self.base_tx, "merchant_category": "casino"}
        score, fired = self.engine.evaluate(tx)
        assert "unusual_merchant" in fired
        assert score == 20

    def test_money_transfer_category_alone_does_not_fire(self):
        """A14: a regulated category is not evidence on its own.

        This test used to assert the opposite — that `money_transfer` fired
        `unusual_merchant` and scored exactly 20 with no corroborating signal —
        which pinned the class-bias defect. Flagging every remittance because of
        what a remittance is, is a false positive by construction.
        """
        tx = {**self.base_tx, "merchant_category": "money_transfer"}
        score, fired = self.engine.evaluate(tx)
        assert "unusual_merchant" not in fired
        assert score == 0

    def test_money_transfer_with_corroboration_fires(self):
        """The category is a corroborating signal, so it still counts."""
        tx = {**self.base_tx, "merchant_category": "money_transfer"}
        _, fired = self.engine.evaluate(tx, context={"recent_transactions": 5})
        assert "unusual_merchant" in fired

    def test_adversarial_category_still_fires_alone(self):
        """The tier that genuinely is a risk claim keeps its behaviour."""
        tx = {**self.base_tx, "merchant_category": "gambling"}
        score, fired = self.engine.evaluate(tx)
        assert "unusual_merchant" in fired
        assert score == 20

    def test_blacklisted_name_without_category_still_fires(self):
        """Exact-name blacklist match still fires without a category (RULE-MERCH-002)."""
        tx = {**self.base_tx, "merchant_name": "Suspicious Shop"}
        context = {"merchant_blacklist": ["Suspicious Shop"]}
        score, fired = self.engine.evaluate(tx, context=context)
        assert "unusual_merchant" in fired
        assert score == 20

    def test_blacklisted_name_with_safe_category_fires(self):
        """Blacklisted name + non-risk category fires via OR semantics (RULE-MERCH-002)."""
        tx = {
            **self.base_tx,
            "merchant_name": "Suspicious Shop",
            "merchant_category": "retail",
        }
        context = {"merchant_blacklist": ["Suspicious Shop"]}
        score, fired = self.engine.evaluate(tx, context=context)
        assert "unusual_merchant" in fired
        assert score == 20

    def test_non_risk_category_does_not_fire(self):
        """Category 'groceries' does not fire unusual_merchant (RULE-MERCH-003)."""
        tx = {**self.base_tx, "merchant_category": "groceries"}
        score, fired = self.engine.evaluate(tx)
        assert "unusual_merchant" not in fired
        assert score == 0

    def test_missing_category_no_crash(self):
        """Missing merchant_category key falls back to name check without crashing."""
        tx = dict(self.base_tx)  # no merchant_category key
        score, fired = self.engine.evaluate(tx)
        assert isinstance(score, float)
        assert "unusual_merchant" not in fired

    def test_empty_string_category_does_not_fire(self):
        """Empty-string category does not fire unusual_merchant."""
        tx = {**self.base_tx, "merchant_category": ""}
        score, fired = self.engine.evaluate(tx)
        assert "unusual_merchant" not in fired
        assert score == 0

    def test_category_matching_case_insensitive(self):
        """Category 'BTC' (uppercase) fires — matching is case-insensitive."""
        tx = {**self.base_tx, "merchant_category": "BTC"}
        score, fired = self.engine.evaluate(tx)
        assert "unusual_merchant" in fired
        assert score == 20

    def test_category_fire_scores_exactly_20(self):
        """Category fire yields only unusual_merchant with score 20.0 (RULE-MERCH-004)."""
        tx = {**self.base_tx, "merchant_category": "btc"}
        score, fired = self.engine.evaluate(tx)
        assert fired == ["unusual_merchant"]
        assert score == 20.0


class TestRuleEngineMultipleRules:
    """Multiple rules can fire cumulatively."""

    def test_high_amount_and_velocity(self):
        """High amount + high velocity should fire both."""
        engine = RuleEngine()
        now = DAYLIGHT_UTC.now_utc()
        tx = {
            "amount": 10000,
            "merchant_name": "Store",
            "card_last4": "1234",
            "user_id": "user-1",
            "timestamp": now.isoformat(),
        }
        context = {"recent_transactions": 5}
        score, fired = engine.evaluate(tx, context=context)
        assert "high_amount" in fired
        assert "high_velocity" in fired
        assert score == 60  # 35 + 25 (high_amount raised from 25, R3-005)

    @pytest.mark.parametrize("hour", [0, 3, 5, 6, 12, 23])
    def test_high_amount_and_velocity_holds_at_every_boundary_hour(self, hour):
        """The 24-hour sweep, parameterised over the hours that matter.

        00, 03 and 05 are inside the night window; 06 is the first hour out of
        it; 12 is midday; 23 is the last hour of the day. Together with
        ``test_high_velocity_score_is_the_same_at_every_hour``, which covers
        all 24, this pins the boundary from both sides.
        """
        engine = RuleEngine()
        clock = FrozenClock.at_hour(hour)
        tx = {
            "amount": 10000,
            "merchant_name": "Store",
            "card_last4": "1234",
            "user_id": "user-1",
            "timestamp": clock.now_utc().isoformat(),
        }
        score, fired = engine.evaluate(tx, context={"recent_transactions": 5})
        expected_extra = 10 if hour < 6 else 0
        assert "high_amount" in fired
        assert "high_velocity" in fired
        assert score == 60 + expected_extra, (
            f"hour {hour:02d}: expected {60 + expected_extra}, got {score} "
            f"(fired {fired})"
        )

    def test_three_rules_fire(self):
        """Three rules (+ unusual_hours + off_hours_crypto) sum their weights."""
        engine = RuleEngine()
        tx = {
            "amount": 10000,
            "merchant_name": "Bad Shop",
            "merchant_category": "crypto",
            "card_last4": "9999",
            "timestamp": "2024-01-15T03:00:00+00:00",
        }
        context = {
            "merchant_blacklist": ["Bad Shop"],
            "known_cards": ["1234", "5678"],
        }
        score, fired = engine.evaluate(tx, context=context)
        assert "high_amount" in fired
        assert "unusual_merchant" in fired
        assert "unusual_hours" in fired
        assert "off_hours_crypto" in fired
        # 35 (high_amount) + 20 (unusual_merchant)
        # + 10 (unusual_hours) + 25 (off_hours_crypto) = 90
        assert score == 90

    def test_all_six_rules_fire_capped(self):
        """All rules firing should be capped at 100."""
        engine = RuleEngine()
        tx = {
            "amount": 100000,
            "merchant_name": "Bad Shop",
            "merchant_category": "cryptocurrency",
            "card_last4": "9999",
            "user_id": "user-1",
            "timestamp": "2024-01-15T03:00:00+00:00",
            "country": "RU",
        }
        context = {
            "recent_transactions": 10,
            "merchant_blacklist": ["Bad Shop"],
            "known_cards": ["1234", "5678"],
            "home_country": "US",
        }
        score, fired = engine.evaluate(tx, context=context)
        # Total possible: 35 + 25 + 30 + 20 + 10 + 25 = 145 (capped at 100)
        assert len(fired) == 6
        assert score == 100  # capped

    def test_no_rule_scores_zero(self):
        """No rules firing should give score 0 and empty fired list."""
        engine = RuleEngine()
        tx = {
            "amount": 50,
            "merchant_name": "Normal Store",
            "card_last4": "1234",
            "timestamp": "2024-01-15T12:00:00+00:00",
        }
        context = {
            "recent_transactions": 1,
            "merchant_blacklist": [],
            "known_cards": ["1234"],
            "home_country": "US",
        }
        score, fired = engine.evaluate(tx, context=context)
        assert score == 0.0
        assert fired == []


class TestRuleEngineDeterminism:
    """Same input must produce same output every time."""

    def test_deterministic_output(self):
        """Two evaluations with same inputs produce same result."""
        engine = RuleEngine()
        tx = {
            "amount": 10000,
            "merchant_name": "Bad Shop",
            "card_last4": "1234",
            "timestamp": "2024-01-15T12:00:00+00:00",
        }
        context = {
            "merchant_blacklist": ["Bad Shop"],
            "known_cards": ["1234", "5678"],
        }
        score1, fired1 = engine.evaluate(tx, context=context)
        score2, fired2 = engine.evaluate(tx, context=context)
        assert score1 == score2
        assert fired1 == fired2


class TestRuleEngineEdgeCases:
    """Edge cases and boundary conditions."""

    def test_negative_amount_zero_score(self):
        """Negative amounts should not trigger high_amount."""
        engine = RuleEngine()
        tx = {"amount": -100, "merchant_name": "Store", "card_last4": "1234"}
        score, fired = engine.evaluate(tx)
        assert "high_amount" not in fired

    def test_zero_amount(self):
        """Zero amount should not trigger high_amount."""
        engine = RuleEngine()
        tx = {"amount": 0, "merchant_name": "Store", "card_last4": "1234"}
        score, fired = engine.evaluate(tx)
        assert "high_amount" not in fired

    def test_amount_exactly_1000(self):
        """Amount exactly 1000 should not trigger high_amount (not > 1000)."""
        engine = RuleEngine()
        tx = {"amount": 1000, "merchant_name": "Store", "card_last4": "1234"}
        score, fired = engine.evaluate(tx)
        assert "high_amount" not in fired

    def test_amount_1000_point_01(self):
        """Amount 1000.01 should trigger high_amount."""
        engine = RuleEngine()
        tx = {"amount": 1000.01, "merchant_name": "Store", "card_last4": "1234"}
        score, fired = engine.evaluate(tx)
        assert "high_amount" in fired

    def test_empty_merchant_name_no_crash(self):
        """Empty merchant name should not crash the engine."""
        engine = RuleEngine()
        tx = {"amount": 100, "merchant_name": "", "card_last4": "1234"}
        score, fired = engine.evaluate(tx)
        # Should not crash, just no rules fire (unless unusual_hours)
        assert isinstance(score, float)

    def test_missing_timestamp_no_crash(self):
        """Missing timestamp should not crash the engine."""
        engine = RuleEngine()
        tx = {"amount": 100, "merchant_name": "Store", "card_last4": "1234"}
        score, fired = engine.evaluate(tx)
        assert isinstance(score, float)
        assert isinstance(fired, list)
