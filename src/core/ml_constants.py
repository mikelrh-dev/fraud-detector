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

#: The canonical merchant-category vocabulary. `merchant_category` is free
#: text on the wire (see D7-3), so this set is what "a category we understand"
#: means. It is deliberately wider than the risky sets: a grocery purchase is a
#: category the system knows and that carries no risk, and conflating the two
#: would make the unknown-category counter useless for the miss it exists to
#: catch.
KNOWN_MERCHANT_CATEGORIES: frozenset[str] = frozenset({
    # canonical, from the risky sets above
    "cryptocurrency",
    "gambling",
    "casino",
    "money_transfer",
    "adult",
    "pharmacy",
    # canonical, non-risky
    "retail",
    "grocery",
    "restaurant",
    "travel",
    "utilities",
    "healthcare",
    "education",
    "entertainment",
    "fuel",
    "telecom",
    "subscription",
    "charity",
    "atm",
    "insurance",
})

# Alias mapping: incoming category strings → canonical form.
# Applied in FeatureEngine.transform() input preprocessing so that
# downstream features (merchant_risk_level, is_crypto) are consistent.
#
# D7-3: this mapped `crypto` and `btc` and nothing else, so `bitcoin`,
# `cripto` and `crypto-exchange` fell through as themselves, matched no set
# membership test, and produced `is_crypto = 0.0` — indistinguishable, in the
# persisted score, from a transaction that is genuinely not crypto. The audit
# measured 47.29 -> 0.63 on that feature.
#
# Keys are already-normalized forms (see `normalize_category`): lowercased,
# trimmed, with `-` and `_` folded to a single space and runs collapsed. Write
# new keys in normalized form or they will silently never match.
CATEGORY_ALIASES: dict[str, str] = {
    # --- cryptocurrency ---
    "crypto": "cryptocurrency",
    "btc": "cryptocurrency",
    "xbt": "cryptocurrency",
    "bitcoin": "cryptocurrency",
    "bitcoins": "cryptocurrency",
    "cripto": "cryptocurrency",
    "criptocurrency": "cryptocurrency",
    "criptomoneda": "cryptocurrency",
    "cripto coin": "cryptocurrency",
    "crypto coin": "cryptocurrency",
    "crypto currency": "cryptocurrency",
    "crypto exchange": "cryptocurrency",
    "crypto trading": "cryptocurrency",
    "cripto exchange": "cryptocurrency",
    "blockchain": "cryptocurrency",
    "ethereum": "cryptocurrency",
    "eth": "cryptocurrency",
    "monero": "cryptocurrency",
    "litecoin": "cryptocurrency",
    # --- gambling ---
    "apuestas": "gambling",
    "apuesta": "gambling",
    "betting": "gambling",
    "apuestas deportivas": "gambling",
    "juego": "gambling",
    "juego de azar": "gambling",
    "juegos de azar": "gambling",
    "sportsbook": "gambling",
    "lottery": "gambling",
    "loteria": "gambling",
    # --- casino ---
    "casinos": "casino",
    "apuestas casino": "casino",
    # --- money transfer ---
    "money transfer": "money_transfer",
    "money transfers": "money_transfer",
    "transferencia": "money_transfer",
    "transferencia de dinero": "money_transfer",
    "remittance": "money_transfer",
    "remesas": "money_transfer",
    "wire transfer": "money_transfer",
    "envio de dinero": "money_transfer",
    "p2p": "money_transfer",
    "p2p transfer": "money_transfer",
    # --- pharmacy ---
    "pharmacy": "pharmacy",
    "farmacia": "pharmacy",
    "drugstore": "pharmacy",
    # --- adult ---
    "adult": "adult",
    "contenido adulto": "adult",
}


def _normalize_form(value: object) -> str:
    """Lowercase, trim, and fold separators so spelling variants collapse.

    `-`, `_` and runs of whitespace all become a single space. `crypto-exchange`,
    `crypto_exchange` and `crypto exchange` are one word to a human and were
    three separate misses.
    """
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    for separator in ("-", "_", "\t", "\n", "\r"):
        text = text.replace(separator, " ")
    return " ".join(text.split())


def normalize_category(value: object) -> str:
    """Map a free-text `merchant_category` onto the canonical vocabulary.

    Returns the canonical name, or the normalized input itself when nothing
    matches — never a guess and never an exception. The miss is what
    `FeatureEngine` counts and logs; this function stays pure so the rule
    engine and the feature engine can share one vocabulary without the rule
    engine double-counting the same event.

    WHY NOT A HARD ENUM ON THE SCHEMA. `merchant_category` is nullable free
    text and existing rows already hold values outside any list we could write
    today. A `Literal[...]` would reject those writes outright, and building a
    list complete enough to be safe is a product decision about which
    categories the business accepts, not a code change. Making the miss loud is
    reversible and can be done without a migration; narrowing the accepted
    input is neither. If the business later decides on a closed set, the enum
    is the right end state and this function becomes the one place that has to
    learn it.
    """
    normalized = _normalize_form(value)
    if not normalized:
        return ""
    return CATEGORY_ALIASES.get(normalized, normalized)


def _build_alias_spellings() -> dict[str, tuple[str, ...]]:
    """Invert :data:`CATEGORY_ALIASES` into canonical → the spellings for it.

    Written as an inversion rather than a hand-kept second table so the two
    cannot drift: adding an entry to `CATEGORY_ALIASES` is enough, and a
    hand-written table would go stale the moment somebody added an alias and
    forgot the second file.

    Identity entries are dropped. `"adult": "adult"` and `"pharmacy":
    "pharmacy"` are not spelling variants, they are the canonical name keyed to
    itself, and including them would let an "alias" emit the canonical string —
    which is precisely how the dead branch in the corpus generator managed to
    look like it was doing something.

    Every value here round-trips by construction: keys of `CATEGORY_ALIASES` are
    documented as already being in normalized form, so `normalize_category`
    normalizes them to themselves and then looks them up to the canonical name.
    """
    collected: dict[str, list[str]] = {}
    for spelling, canonical in CATEGORY_ALIASES.items():
        if spelling == canonical:
            continue
        collected.setdefault(canonical, []).append(spelling)
    return {canonical: tuple(sorted(v)) for canonical, v in collected.items()}


#: Canonical category → the alias spellings that normalize onto it. Emitting one
#: of these is how a producer (the training corpus, the demo generator) makes sure
#: its output passes through the same normalization a live request does, instead
#: of quietly only ever exercising the canonical names.
CATEGORY_ALIAS_SPELLINGS: dict[str, tuple[str, ...]] = _build_alias_spellings()

#: Categories deliberately carried no alias spelling, declared rather than
#: inferred.
#:
#: Every category a generator draws should have spellings, because a producer
#: that can only ever emit the canonical name never exercises the normalization
#: that every live request depends on — that was the dead branch in
#: `train_xgboost_aligned._draw_category` (see 15a8eec) and in
#: `scripts/generate_synthetic_data.py` (7e81876). The guard that keeps that
#: from coming back derives the generator vocabularies from the generators
#: themselves, so a new risk category with no aliases goes red on its own.
#:
#: This set is the escape hatch for the case that is legitimately
#: alias-free, and it is EMPTY right now: all five categories the generators
#: draw have spellings.
#:
#:     cryptocurrency  19    money_transfer  10    gambling  10
#:     pharmacy         2    adult            1
#:
#: It exists so that "this category genuinely has no other spelling anyone
#: uses" is a sentence somebody wrote down and a reviewer can disagree with,
#: rather than a silent gap. Adding a name here is a DECLARATION, and it is
#: checked both ways by `tests/test_category_vocabulary.py`: a name here that
#: does have spellings is an error, and so is a name here that no generator
#: draws.
CATEGORIES_WITHOUT_ALIAS_SPELLINGS: frozenset[str] = frozenset()
