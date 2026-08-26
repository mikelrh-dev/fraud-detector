"""ML constants — single source of truth for merchant risk categories.

Unifies the three disjoint vocabularies that previously lived in:
- FeatureEngine.HIGH_RISK_CATEGORIES (feature_engine.py)
- RuleEngine.RISKY_CATEGORIES (rule_engine.py)
- Training script category lists (train_xgboost_aligned.py, generate_synthetic_data.py)

Downstream consumers:
- FeatureEngine.transform(): uses MERCHANT_RISK_CATEGORIES for merchant_risk_level
  and is_crypto features; applies CATEGORY_ALIASES for input normalization.
- RuleEngine.evaluate(): uses MERCHANT_RISK_CATEGORIES for unusual_merchant and
  velocity_burst rules.
- Training scripts: use MERCHANT_RISK_CATEGORIES to generate realistic training data.
"""

# Canonical high-risk merchant categories.
# Includes both canonical names and recognized aliases so consumers
# can match against a single set without pre-normalization.
MERCHANT_RISK_CATEGORIES: frozenset[str] = frozenset({
    "cryptocurrency",  # canonical
    "crypto",          # alias for cryptocurrency
    "btc",             # alias for cryptocurrency
    "gambling",
    "casino",
    "money_transfer",
    "adult",
    "pharmacy",
})

# Alias mapping: incoming category strings → canonical form.
# Applied in FeatureEngine.transform() input preprocessing so that
# downstream features (merchant_risk_level, is_crypto) are consistent.
CATEGORY_ALIASES: dict[str, str] = {
    "crypto": "cryptocurrency",
    "btc": "cryptocurrency",
}
