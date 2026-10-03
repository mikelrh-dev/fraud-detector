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
- Frontend (generated, never hand-typed): scripts/generate_frontend_vocabulary.py
  writes KNOWN_MERCHANT_CATEGORIES into frontend/src/lib/merchant-vocabulary.generated.ts,
  and tests/unit/test_frontend_vocabulary.py fails if the two ever disagree.

It also holds the D2 magnitude constants, because a tuning number that decides
how a transaction scores belongs with the other tuned numbers rather than inline
in the method that applies it.
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


# ---------------------------------------------------------------------------
# D1 — the merchant NAME vocabulary
# ---------------------------------------------------------------------------
#
# WHY THIS TABLE EXISTS. A real transaction: 400,000 USD, merchant `binance`,
# category `retail`. It scored 24.1/100, "legitimate". The reason is not a bad
# threshold or a bad model — it is that `merchant_name` was never consulted by
# anything. `FeatureEngine` derived `is_crypto` and `merchant_risk_level` from
# the CATEGORY alone, and `RuleEngine` derived its adversarial/regulated tiers
# from the category alone. So the two features that know what kind of merchant
# this is were decided by whichever string the payload happened to carry, and
# the field that actually identifies the merchant was decoration.
#
# The category and the name answer DIFFERENT questions, and the fix is to let
# each answer its own:
#
#   merchant_category   "what kind of business is this"  -> the validated
#                       enumeration above. The caller picks from a closed list.
#   merchant_name       "which merchant is this"         -> the table below.
#
# WHAT IS ADMISSIBLE HERE, AND WHY IT IS NARROWER THAN IT LOOKS. A SINGLE-token
# entry must IDENTIFY a merchant. It must not DESCRIBE a category. So `binance`
# is here and a bare `casino`, `apuestas` or `crypto` is not, even though a
# merchant called "Casino Barcelona" is a casino: a descriptor in a free-text
# field is D1's defect relocated rather than fixed — it fires on "Casino
# Barcelona" and "Crypto Consulting", and the caller picks those strings.
# `merchant_category` is where that claim belongs, and it is validated (D3).
#
# A MULTI-token phrase is a different claim and may contain such a word, because
# the phrase is what identifies the merchant: `crypto com` is the brand
# Crypto.com, and it matches "Crypto.com", "Crypto.Com Berlin" and "Crypto Com
# SA" while `crypto` alone would match all three AND "Crypto Consulting".
# `tests/test_merchant_name_vocabulary.py` enforces this distinction rather than
# leaving it to this comment to be believed.
#
# What that costs, stated rather than hidden: a merchant that transacts at
# Binance under an unrelated local name (`"Berlin Sueiro SA"`) is not matched.
# Nothing can match it from the name, and pretending otherwise would mean
# guessing. The corpus's own vocabulary of fictional merchants
# (`CryptoEx_7`, `Casino_3`) is deliberately not matched either — see the note
# in scripts/train_xgboost_aligned.py on why the shipped artifact is unaffected.
#
# Every entry can only RAISE risk, never lower it: the value is a canonical
# category that feeds the same tier sets the category feeds, and a hit wins over
# a benign category rather than replacing the whole field. A name is evidence
# about a merchant; it is not a licence to declare one safe.
#
# KEYS ARE TOKEN SEQUENCES, NOT SUBSTRINGS. See `merchant_category_from_name`
# for the tokenization rule and for why contiguous-run matching is the one
# chosen here. An entry that is not written in lowercase, space-separated
# alphanumeric form will silently never match, so `_phrase_index` is derived
# from this table rather than hand-maintained and a test asserts every key
# survives the round trip.

#: Known merchant identifier -> the canonical category it belongs to.
KNOWN_MERCHANT_PHRASES: dict[str, str] = {
    # --- crypto exchanges -------------------------------------------------
    # Named individually because these are the venues a stolen balance lands
    # on, and the reported transaction is one of them. `binance` is the entry
    # that exists because of a measurement; the rest are the same class of
    # merchant a card-present feed sees, and each is a word that is not a common
    # English noun, so the incidental-match cost is close to zero.
    "binance": "cryptocurrency",   # the reported 400k USD / retail transaction
    "coinbase": "cryptocurrency",  # largest US-regulated venue
    "bitstamp": "cryptocurrency",  # long-standing EU venue (Luxembourg)
    "bitfinex": "cryptocurrency",  # long-standing venue, large USD books
    "bitpanda": "cryptocurrency",  # EU-licensed retail venue
    "upbit": "cryptocurrency",     # large-KRW venue, present in APAC feeds
    # DOCUMENTED JUDGEMENT: `kraken` IS a common English noun, so a seafood
    # merchant trading as "Kraken" matches. Accepted, because in a payments
    # corpus the name is overwhelmingly the exchange and because the failure is
    # a review, never an auto-block: an adversarial category fires
    # `unusual_merchant` (20) and needs a night hour before `off_hours_crypto`
    # joins it. Recorded here so the next reviewer can disagree.
    "kraken": "cryptocurrency",
    # Multi-token entries, because the brand is punctuated or spelled out and
    # tokenization splits on the punctuation. `crypto.com` tokenizes to
    # ("crypto", "com"), which is exactly why this cannot be a bare `crypto`
    # entry — see the admissibility note above.
    "crypto com": "cryptocurrency",
    "blockchain com": "cryptocurrency",
    # A merchant whose registered name literally says what it is. The same
    # claim `merchant_category=cryptocurrency` makes, stated in the name
    # instead — which is a stronger claim, because a name is harder to pick
    # casually than a free-text category.
    "crypto exchange": "cryptocurrency",
    # --- gambling ---------------------------------------------------------
    # Named betting brands rather than the word "casino". Same reasoning as the
    # exchanges: these identify a venue, and "casino" describes a category.
    "bet365": "gambling",
    "betfair": "gambling",
    "pokerstars": "gambling",
    "william hill": "gambling",
    "betway": "gambling",
    "1xbet": "gambling",
    # --- money transfer ---------------------------------------------------
    # Included to show the vocabulary is not crypto-only: the rule engine
    # decides what a hit MEANS through the tier sets, so a money_transfer hit is
    # REGULATED and counts only alongside velocity, a night hour or a
    # blacklist entry — it cannot fire on its own. These are the canonical
    # remittance businesses, so `merchant_name` saying "money transfer" is
    # information the category field did not carry.
    "western union": "money_transfer",
    "moneygram": "money_transfer",
}


def _merchant_tokens(value: object) -> tuple[str, ...]:
    """Reduce a merchant name to its token sequence.

    THE RULE, stated once so a reader does not have to infer it: lowercase, then
    split on every character that is not a letter or a digit, and drop empties.
    Letters-and-digits rather than an enumerated separator list, because the
    punctuation that actually shows up in this field is not enumerable — a
    merchant name arrives as `Binance`, `BINANCE.COM`, `Binance-Exchange`,
    `Binance  Berlin`, `binance_berlin`, `Binance / Berlin` and all of them are
    one name.

        "binance"           -> ("binance",)
        "BINANCE.COM"       -> ("binance", "com")
        "Binance  Berlin"   -> ("binance", "berlin")
        "binance_berlin"    -> ("binance", "berlin")

    `str.isalnum()` keeps non-ASCII letters, so a Spanish or German merchant
    name (`"Farmacia San Juan"`) tokenizes instead of collapsing to nothing.

    Never raises. A non-string `merchant_name` — an int, a list, an object, from
    a batch consumer rather than from pydantic — is coerced through `str()`, and
    a name that no vocabulary entry matches returns no category, which is the
    same "we learned nothing" answer as an absent name.
    """
    if value is None:
        return ()
    lowered = "".join(ch.lower() if ch.isalnum() else " " for ch in str(value))
    return tuple(lowered.split())


def _phrase_index() -> dict[tuple[str, ...], str]:
    """`KNOWN_MERCHANT_PHRASES` keyed by token sequence rather than by string.

    Derived, never hand-kept, for the reason `_build_alias_spellings` gives: a
    second spelling table is a table that goes stale. An entry written in the
    wrong form ("Binance Exchange", "crypto.com") produces a key that matches
    nothing, which is the silent-miss failure this whole change exists to remove,
    so `tests/test_merchant_name_vocabulary.py` asserts every key round-trips.
    """
    return {
        tuple(_merchant_tokens(phrase)): category
        for phrase, category in KNOWN_MERCHANT_PHRASES.items()
    }


_PHRASE_INDEX: dict[tuple[str, ...], str] = _phrase_index()

#: Phrase lengths present, longest first. Iterating lengths from the longest down
#: is what makes a two-token entry beat a one-token entry that overlaps it, so
#: the most specific match wins regardless of where it sits in the name.
_PHRASE_LENGTHS: tuple[int, ...] = tuple(
    sorted({len(phrase) for phrase in _PHRASE_INDEX}, reverse=True)
)


def merchant_category_from_name(value: object) -> str:
    """The canonical category a merchant NAME identifies, or `""` for none.

    THE MATCHING RULE, which the task this file exists for asked to be decided
    deliberately rather than left to whoever typed it first:

    An entry matches when its token sequence appears as a CONTIGUOUS RUN of
    tokens in the name. All three other rules were available and were rejected
    against the three cases that have to work and the three that must not:

      substring  -- `"binance" in name`. Rejected: it fires on `BinanceCard`,
                    `PreBinance` and `BinanceSA`, none of which is an exchange.
      whole name == entry -- exact match. Rejected: misses `Binance Berlin`,
                    which is the shape the reported payload actually took once a
                    feed adds a branch or a city.
      every name token is known -- set containment. Rejected: `Binance SA
                    Argentina` has three tokens and one is known, so it misses;
                    and it makes the rule depend on tokens the vocabulary has
                    never heard of.
      contiguous run -- chosen. It is word-boundary exact on both sides, so the
                    three accidental matches above fail, and it tolerates
                    surrounding context, so the three real ones succeed:

                        "binance"           matches
                        "Binance Exchange"  matches
                        "Binance Berlin"    matches
                        "BINANCE.COM"       matches
                        "BinanceCard"       does NOT
                        "PreBinance"        does NOT
                        "Rebinanzas SA"     does NOT

    Ties, in order: the longer entry wins (so `crypto com` beats any one-token
    entry it contains), then the earliest position in the name. Both are
    determinism requirements — a vocabulary with two simultaneous matches must
    resolve the same way on every call, or the same transaction scores
    differently depending on dictionary order.

    Returns `""` rather than raising or guessing when nothing matches, matching
    `normalize_category`'s convention: no news is not bad news, and a merchant
    this table has never heard of must not be treated as a risky one.

    Callers combine this with the CATEGORY, name first — see
    `FeatureEngine.transform` and `RuleEngine.evaluate`. One vocabulary, two
    readers, per the D7-3 principle at the top of this file.
    """
    tokens = _merchant_tokens(value)
    if not tokens:
        return ""
    for length in _PHRASE_LENGTHS:
        if length > len(tokens):
            continue
        for start in range(len(tokens) - length + 1):
            match = _PHRASE_INDEX.get(tokens[start : start + length])
            if match is not None:
                return match
    return ""


# ---------------------------------------------------------------------------
# D2 — the amount magnitude of the `high_amount` rule
# ---------------------------------------------------------------------------
#
# `high_amount` used to be a switch: 1,001.00 EUR and 400,000.00 USD both scored
# 35. A coffee and a quarter of bitcoin were the same evidence. These three
# constants turn it back into a magnitude.
#
# The base weight is unchanged and stays in `RuleEngine.WEIGHTS`, because that is
# the base rule and other rules share the table. Only the magnitude term is here,
# and both of its numbers are derived from a consumer rather than picked.

#: The line `high_amount` is about, in the transaction's own units. Lives here
#: rather than on `RuleEngine` so the threshold and the shape of the response
#: above it are one decision in one place.
HIGH_AMOUNT_THRESHOLD: float = 1000.0

#: Points added per order of magnitude above :data:`HIGH_AMOUNT_THRESHOLD`.
#: log10 is the right shape because it is the only common curve that is
#: unbounded, strictly increasing and equal to zero AT the threshold, so crossing
#: the line changes nothing and everything above it is strictly graded.
AMOUNT_MAGNITUDE_POINTS: float = 8.0

#: Ceiling on the magnitude term, and the reason it is not optional.
#:
#: Derived from the consumer. `EnsembleScorer` weights the rule layer at 0.60
#: (`settings.ensemble_rule_weight`) and the strictest amount tier sets the fraud
#: threshold at 40, so a rule score of 40 / 0.60 = 66.67 is the smallest score at
#: which `high_amount` ALONE can produce a `fraud` classification while the other
#: two layers read zero. The rule's base weight is 35, so the ceiling must stay
#: below 31.67 for the "suspicious vs clearly fraud" distinction to survive; 25
#: is chosen for headroom, and the arithmetic is asserted in
#: tests/test_rule_engine_amount_magnitude.py so the constant cannot drift away
#: from the geometry that justifies it.
#:
#: Without a ceiling the term is proportional to log10(amount), so a $50M
#: transfer scores higher than a $1,100 one by more than the whole rest of the
#: rulebook — and `min()` at the top of the sum stops mattering, because the one
#: rule has already spent the scale on its own.
AMOUNT_MAGNITUDE_CAP: float = 25.0

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
