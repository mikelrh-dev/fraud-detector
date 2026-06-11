"""Rule engine tests — single rule fires, multiple rules, no rules, determinism, score cap.

These tests verify the deterministic rule engine used as the first layer of
the fraud scoring pipeline.
"""

from datetime import datetime, timezone

import pytest

from src.services.rule_engine import RuleEngine


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
        now = datetime.now(tz=timezone.utc)
        tx = {"amount": 100, "user_id": "user-1", "timestamp": now.isoformat()}
        context = {
            "recent_transactions": 5,  # > 3 in last 5 min
        }
        score, fired = engine.evaluate(tx, context=context)
        assert "high_velocity" in fired
        assert score == 25

    def test_unusual_merchant_rule_fires(self):
        """Merchant in blacklist should fire unusual_merchant (weight 20)."""
        engine = RuleEngine()
        tx = {"amount": 100, "merchant_name": "Suspicious Shop", "card_last4": "1234"}
        context = {"merchant_blacklist": ["Suspicious Shop", "Dark Market"]}
        score, fired = engine.evaluate(tx, context=context)
        assert "unusual_merchant" in fired
        assert score == 20

    def test_card_mismatch_rule_fires(self):
        """Card_last4 not in known cards should fire card_mismatch (weight 20)."""
        engine = RuleEngine()
        tx = {"amount": 100, "card_last4": "9999"}
        context = {"known_cards": ["1234", "5678"]}
        score, fired = engine.evaluate(tx, context=context)
        assert "card_mismatch" in fired
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

    def test_country_mismatch_rule_fires(self):
        """Transaction country different from home should fire country_mismatch (weight 15)."""
        engine = RuleEngine()
        tx = {"amount": 100, "merchant_name": "Store", "country": "RU"}
        context = {"home_country": "US"}
        score, fired = engine.evaluate(tx, context=context)
        assert "country_mismatch" in fired
        assert score == 15


class TestRuleEngineMultipleRules:
    """Multiple rules can fire cumulatively."""

    def test_high_amount_and_velocity(self):
        """High amount + high velocity should fire both."""
        engine = RuleEngine()
        now = datetime.now(tz=timezone.utc)
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
        assert score == 55  # 30 + 25

    def test_three_rules_fire(self):
        """Three rules should sum their weights."""
        engine = RuleEngine()
        tx = {
            "amount": 10000,
            "merchant_name": "Bad Shop",
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
        assert "card_mismatch" in fired
        assert "unusual_hours" in fired
        assert score == 80  # 30 + 20 + 20 + 10

    def test_all_six_rules_fire_capped(self):
        """All rules firing should be capped at 100."""
        engine = RuleEngine()
        now = datetime.now(tz=timezone.utc)
        tx = {
            "amount": 100000,
            "merchant_name": "Bad Shop",
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
        # Total possible: 30 + 25 + 20 + 20 + 10 + 15 = 120
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

    def test_amount_exactly_5000(self):
        """Amount exactly 5000 should not trigger high_amount (not > 5000)."""
        engine = RuleEngine()
        tx = {"amount": 5000, "merchant_name": "Store", "card_last4": "1234"}
        score, fired = engine.evaluate(tx)
        assert "high_amount" not in fired

    def test_amount_5000_point_01(self):
        """Amount 5000.01 should trigger high_amount."""
        engine = RuleEngine()
        tx = {"amount": 5000.01, "merchant_name": "Store", "card_last4": "1234"}
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
