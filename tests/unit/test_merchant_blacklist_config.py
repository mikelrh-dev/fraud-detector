"""The risky-merchant list is configuration, not a literal in the request path.

ML-01, audit 2026-09-29: `api/v1/transactions.py` inlined three merchant
strings into the `context` dict it hands the rule engine. The list could not
be extended without a code change and a deploy -- there was no configuration
path at all, not in `.env` and not in `src/core/config.py`.

Moving a value out of a literal and into a setting is only worth doing if two
things hold, and this file asserts both rather than assuming them:

1. The default is byte-identical to what the literal was, so no transaction
   scores differently than it did before the move.
2. The request path actually reads the setting. A config field that nothing
   consumes is the same defect wearing a different hat -- which is precisely
   what TST-01 and TST-02 found in this repo two days running.

The rule itself and the +20 weight are untouched; that is the point of
`test_default_preserves_the_previous_rule_outcome`.
"""

from __future__ import annotations

import pytest

from src.core.config import Settings, settings
from src.services.rule_engine import RuleEngine

#: The exact literals that were inlined at api/v1/transactions.py:263 before
#: this change. Order is part of the contract here: this is the value the
#: request path used, verbatim.
PREVIOUS_LITERALS = [
    "crypto exchange pro",
    "online gambling",
    "money transfer now",
]

#: WEIGHTS["unusual_merchant"] in services/rule_engine.py. Asserted rather
#: than hard-coded into the expectation so a weight change that breaks this
#: contract has to be made deliberately, in two places.
UNUSUAL_MERCHANT_WEIGHT = RuleEngine.WEIGHTS["unusual_merchant"]


class TestBlacklistDefault:
    """The default must be the value that was inlined, unchanged."""

    def test_default_is_the_previous_three_literals(self):
        assert settings.merchant_blacklist == PREVIOUS_LITERALS

    def test_each_settings_instance_owns_its_own_list(self):
        """The endpoint hands `settings.merchant_blacklist` -- a list owned by
        a module-level singleton -- into the context dict of every request. A
        shared default would mean one request's mutation is visible to the
        next, across the whole process. Pydantic deep-copies non-hashable
        defaults per instance, so it is safe today; this pins that, because
        the safety is a library behaviour this code depends on rather than
        something it enforces."""
        other = Settings()
        assert other.merchant_blacklist is not settings.merchant_blacklist
        assert other.merchant_blacklist == PREVIOUS_LITERALS

    def test_env_override_parses_a_json_array(self):
        """The point of the change: an operator can extend the list without a
        deploy. Complex types parse as JSON, matching `threshold_tiers`."""
        override = Settings(merchant_blacklist=["a", "b", "c"])
        assert override.merchant_blacklist == ["a", "b", "c"]

    def test_env_override_replaces_rather_than_extends(self):
        """Replaces, not merges. An operator who sets the variable gets
        exactly the list they asked for, and is not silently unioned with
        the defaults -- a merged list would be impossible to reason about."""
        override = Settings(merchant_blacklist=["only this one"])
        assert override.merchant_blacklist == ["only this one"]


class TestRuleOutcomePreserved:
    """The default must produce the same rule outcome the literal did."""

    @pytest.mark.parametrize("merchant", PREVIOUS_LITERALS)
    def test_each_defaulted_merchant_still_fires_unusual_merchant(self, merchant):
        engine = RuleEngine()
        context = {"merchant_blacklist": settings.merchant_blacklist}

        score, fired = engine.evaluate(
            {
                "amount": 100.0,
                "merchant_name": merchant,
                "merchant_category": "retail",
                "timestamp": "2024-01-15T12:00:00+00:00",
            },
            context,
        )

        assert "unusual_merchant" in fired
        # Nothing else fires: 100.0 is under HIGH_AMOUNT_THRESHOLD, one
        # transaction is not velocity, and midday is not a night hour. So the
        # whole score IS the blacklist contribution.
        assert fired == ["unusual_merchant"]
        assert score == float(UNUSUAL_MERCHANT_WEIGHT) == 20.0

    def test_match_is_case_insensitive_as_before(self):
        """rule_engine lowercases both sides. The setting must not change
        that, or an operator adding "Some Shop" would silently never match."""
        engine = RuleEngine()
        _, fired = engine.evaluate(
            {
                "amount": 100.0,
                "merchant_name": "ONLINE GAMBLING",
                "merchant_category": "retail",
                "timestamp": "2024-01-15T12:00:00+00:00",
            },
            {"merchant_blacklist": settings.merchant_blacklist},
        )
        assert "unusual_merchant" in fired

    def test_an_unlisted_merchant_is_unaffected(self):
        """The setting must not fire the rule for everything."""
        engine = RuleEngine()
        _, fired = engine.evaluate(
            {
                "amount": 100.0,
                "merchant_name": "Grocery Store",
                "merchant_category": "groceries",
                "timestamp": "2024-01-15T12:00:00+00:00",
            },
            {"merchant_blacklist": settings.merchant_blacklist},
        )
        assert "unusual_merchant" not in fired

    def test_evaluation_does_not_mutate_the_list_it_was_handed(self):
        """The endpoint passes the singleton's list into every request's
        context. rule_engine lowercases into a new list, so nothing writes
        back into it. If that ever changes, the mutation would be global."""
        blacklist = settings.merchant_blacklist
        snapshot = list(blacklist)
        RuleEngine().evaluate(
            {
                "amount": 100.0,
                "merchant_name": "ONLINE GAMBLING",
                "merchant_category": "retail",
                "timestamp": "2024-01-15T12:00:00+00:00",
            },
            {"merchant_blacklist": blacklist},
        )
        assert blacklist == snapshot
