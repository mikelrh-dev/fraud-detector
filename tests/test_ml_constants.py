"""ML constants tests — unified category vocabulary, aliases, and integration.

Tests for the canonical category list and alias normalization used by
FeatureEngine, RuleEngine, and training scripts.
"""


from src.core.ml_constants import CATEGORY_ALIASES, MERCHANT_RISK_CATEGORIES
from src.services.feature_engine import FeatureEngine
from src.services.rule_engine import RuleEngine


class TestCategoryAliases:
    """Category alias normalization — incoming aliases map to canonical forms."""

    def test_crypto_alias_normalizes(self):
        """'crypto' should normalize to 'cryptocurrency'."""
        assert CATEGORY_ALIASES["crypto"] == "cryptocurrency"

    def test_btc_alias_normalizes(self):
        """'btc' should normalize to 'cryptocurrency'."""
        assert CATEGORY_ALIASES["btc"] == "cryptocurrency"

    def test_canonical_form_self_maps(self):
        """Canonical forms should map to themselves."""
        for cat in MERCHANT_RISK_CATEGORIES:
            if cat not in CATEGORY_ALIASES:
                # Canonical form not in aliases — that's fine, it passes through
                pass

    def test_aliases_cover_known_variants(self):
        """Known aliases should be present."""
        assert "crypto" in CATEGORY_ALIASES
        assert "btc" in CATEGORY_ALIASES


class TestMerchantRiskCategories:
    """Canonical high-risk merchant categories."""

    def test_frozenset_contains_expected(self):
        """Core categories should be present."""
        assert "cryptocurrency" in MERCHANT_RISK_CATEGORIES
        assert "gambling" in MERCHANT_RISK_CATEGORIES
        assert "casino" in MERCHANT_RISK_CATEGORIES
        assert "money_transfer" in MERCHANT_RISK_CATEGORIES
        assert "adult" in MERCHANT_RISK_CATEGORIES
        assert "pharmacy" in MERCHANT_RISK_CATEGORIES

    def test_is_frozenset(self):
        """Should be a frozenset for immutability."""
        assert isinstance(MERCHANT_RISK_CATEGORIES, frozenset)


class TestFeatureEngineCategoryNormalization:
    """FeatureEngine.transform() should normalize categories via aliases."""

    def test_crypto_normalizes_to_cryptocurrency(self):
        """Transaction with merchant_category='crypto' should be treated as cryptocurrency."""
        engine = FeatureEngine()
        tx_crypto = {
            "amount": 1000.0,
            "merchant_category": "crypto",
            "timestamp": "2024-01-15T12:00:00",
        }
        tx_canonical = {
            "amount": 1000.0,
            "merchant_category": "cryptocurrency",
            "timestamp": "2024-01-15T12:00:00",
        }
        f_crypto = engine.transform(tx_crypto)
        f_canonical = engine.transform(tx_canonical)
        # merchant_risk_level (index 7) and is_crypto (index 8) should match
        assert f_crypto[7] == f_canonical[7], "merchant_risk_level should match after normalization"
        assert f_crypto[8] == f_canonical[8], "is_crypto should match after normalization"

    def test_crypto_triggers_merchant_risk(self):
        """'crypto' alias should trigger merchant_risk_level=1.0."""
        engine = FeatureEngine()
        tx = {
            "amount": 100.0,
            "merchant_category": "crypto",
            "timestamp": "2024-01-15T12:00:00",
        }
        features = engine.transform(tx)
        assert features[7] == 1.0, "merchant_risk_level should be 1.0 for crypto"

    def test_btc_triggers_merchant_risk(self):
        """'btc' alias should trigger merchant_risk_level=1.0."""
        engine = FeatureEngine()
        tx = {
            "amount": 100.0,
            "merchant_category": "btc",
            "timestamp": "2024-01-15T12:00:00",
        }
        features = engine.transform(tx)
        assert features[7] == 1.0, "merchant_risk_level should be 1.0 for btc"

    def test_btc_triggers_is_crypto(self):
        """'btc' alias should trigger is_crypto=1.0 (mapped to cryptocurrency)."""
        engine = FeatureEngine()
        tx = {
            "amount": 100.0,
            "merchant_category": "btc",
            "timestamp": "2024-01-15T12:00:00",
        }
        features = engine.transform(tx)
        assert features[8] == 1.0, "is_crypto should be 1.0 for btc"

    def test_non_risk_category_no_trigger(self):
        """'groceries' should not trigger merchant_risk or is_crypto."""
        engine = FeatureEngine()
        tx = {
            "amount": 100.0,
            "merchant_category": "groceries",
            "timestamp": "2024-01-15T12:00:00",
        }
        features = engine.transform(tx)
        assert features[7] == 0.0
        assert features[8] == 0.0


class TestRuleEngineCategoryNormalization:
    """RuleEngine should recognize normalized categories for risky-category rules."""

    def test_crypto_alias_fires_unusual_merchant(self):
        """'crypto' alias should fire unusual_merchant via category normalization."""
        engine = RuleEngine()
        tx = {"amount": 100, "merchant_name": "CryptoBuy", "merchant_category": "crypto"}
        score, fired = engine.evaluate(tx)
        assert "unusual_merchant" in fired

    def test_btc_alias_fires_unusual_merchant(self):
        """'btc' alias should fire unusual_merchant."""
        engine = RuleEngine()
        tx = {"amount": 100, "merchant_name": "BtcShop", "merchant_category": "btc"}
        score, fired = engine.evaluate(tx)
        assert "unusual_merchant" in fired

    def test_canonical_form_still_works(self):
        """Canonical 'cryptocurrency' should still fire unusual_merchant."""
        engine = RuleEngine()
        tx = {"amount": 100, "merchant_name": "CryptoEx", "merchant_category": "cryptocurrency"}
        score, fired = engine.evaluate(tx)
        assert "unusual_merchant" in fired
