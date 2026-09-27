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

# A14: the rule engine used MERCHANT_RISK_CATEGORIES as a single tier, so a
# pharmacy purchase or a remittance carried the same flat 20 rule points as a
# gambling site, with no corroborating evidence at all. Combined with
# velocity_burst (30) and the night-time rules, a single `category` field could
# reach 85/100 on its own — and 20 points of pure class bias on every such
# transaction is 20 points of systematic false positives across a whole class of
# legitimate merchants.
#
# These tiers are for the rule engine only. MERCHANT_RISK_CATEGORIES is left
# untouched because it is also the feature-engine's contract
# (merchant_risk_level, is_crypto) and the training scripts generate from it;
# changing it would silently shift the model's input distribution, which is a
# different and much more dangerous change.
#
#   - Adversarial: the category itself is evidence of risk.
#   - Regulated: the category is normal for the business; it is only a
#     *corroborating* signal, and must be paired with something else.
MERCHANT_ADVERSARIAL_CATEGORIES: frozenset[str] = frozenset({
    "cryptocurrency",  # canonical
    "crypto",          # alias for cryptocurrency
    "btc",             # alias for cryptocurrency
    "gambling",
    "casino",
    "adult",
})

#: Legitimate, heavily-regulated businesses. Flagging a transaction purely
#: because it happened at a pharmacy or a remittance provider is a false
#: positive by construction, so these only count alongside another signal.
MERCHANT_REGULATED_CATEGORIES: frozenset[str] = frozenset({
    "money_transfer",
    "pharmacy",
})

# Alias mapping: incoming category strings → canonical form.
# Applied in FeatureEngine.transform() input preprocessing so that
# downstream features (merchant_risk_level, is_crypto) are consistent.
CATEGORY_ALIASES: dict[str, str] = {
    "crypto": "cryptocurrency",
    "btc": "cryptocurrency",
}
