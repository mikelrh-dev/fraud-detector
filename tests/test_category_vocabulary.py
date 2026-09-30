"""D7-3: `merchant_category` is free text, and a miss was silently inert.

`CATEGORY_ALIASES` mapped exactly two spellings -- `crypto` and `btc` -- to the
canonical `cryptocurrency`. Everything else that means the same thing fell
through the lookup as itself, matched no set membership test, and produced a
feature vector with `is_crypto = 0.0` and `merchant_risk_level = 0.0`:

    'crypto'          -> risk 1.0  is_crypto 1.0
    'bitcoin'         -> risk 0.0  is_crypto 0.0
    'cripto'          -> risk 0.0  is_crypto 0.0
    'crypto-exchange' -> risk 0.0  is_crypto 0.0

No error, no log, no counter. The audit measured the consequence at 47.29 ->
0.63 on the crypto feature. A misspelled or translated category was not a
category the system failed to understand; it was a category the system
reported as safe, and the report was indistinguishable from a correct one.

Two properties are asserted, and the second is the one that matters:

  1. Every alias resolves to the same feature vector as its canonical form.
  2. A value that matches nothing in the vocabulary is *visible* -- counted and
     logged -- instead of quietly reading as "not a risky merchant".

The alternative to (2) is a hard enum on the schema. That is not done here and
the reason is in `normalize_category`'s docstring: a hard enum rejects every
existing row whose category is not in the list, and the list cannot be
complete without a product decision about which categories the business
accepts. Making the miss loud is reversible; narrowing the accepted input is
not.
"""

import logging

import pytest

from src.core.counters import snapshot
from src.core.ml_constants import (
    CATEGORY_ALIASES,
    KNOWN_MERCHANT_CATEGORIES,
    normalize_category,
)
from src.services.feature_engine import FEATURE_NAMES, FeatureEngine
from src.services.rule_engine import RuleEngine

CANONICAL_CRYPTO = "cryptocurrency"

#: Spellings that all mean `cryptocurrency`. Drawn from the audit's list plus
#: the ones a Spanish-language product would actually receive, since the UI and
#: the report prompt are both in Spanish.
CRYPTO_ALIASES = [
    "crypto",
    "btc",
    "cryptocurrency",
    "bitcoin",
    "bitcoins",
    "cripto",
    "criptocurrency",
    "criptomoneda",
    "cripto-exchange",
    "crypto-exchange",
    "crypto exchange",
    "crypto_currency",
    "crypto-coin",
    "blockchain",
    "ethereum",
    "eth",
    "xbt",
    "Criptomoneda",
    "  BITCOIN  ",
    "Crypto-Exchange",
]

#: Spellings that mean the other canonical categories, so the same class of miss
#: is covered on more than one of them.
OTHER_ALIASES = {
    "apuestas": "gambling",
    "betting": "gambling",
    "apuestas-deportivas": "gambling",
    "juego de azar": "gambling",
    "sportsbook": "gambling",
    "casinos": "casino",
    "transferencia de dinero": "money_transfer",
    "remittance": "money_transfer",
    "wire transfer": "money_transfer",
    "p2p": "money_transfer",
    "farmacia": "pharmacy",
}


@pytest.fixture(autouse=True)
def _reset_observation_state():
    """Counters and the warned-set are process-global, so both must be cleared
    between tests or a test that asserts a log line sees the one an earlier
    test already emitted.

    `_WARNED_CATEGORIES` is private and reached for directly rather than through
    a new public reset helper: a reset function would be a public symbol in
    `src/` with no production caller, which is exactly the shape
    `tests/test_audit_orphans.py` exists to fail on."""
    from src.core import counters
    from src.services import feature_engine

    counters.reset()
    feature_engine._WARNED_CATEGORIES.clear()
    yield
    counters.reset()
    feature_engine._WARNED_CATEGORIES.clear()


def vector_for(category: str) -> list[float]:
    engine = FeatureEngine()
    return list(engine.transform({"amount": 100.0, "merchant_category": category}))


class TestAliasResolution:
    @pytest.mark.parametrize("alias", CRYPTO_ALIASES)
    def test_crypto_alias_produces_the_canonical_feature_vector(self, alias: str):
        assert vector_for(alias) == vector_for(CANONICAL_CRYPTO)

    @pytest.mark.parametrize(("alias", "canonical"), sorted(OTHER_ALIASES.items()))
    def test_other_aliases_resolve_to_their_canonical_category(
        self, alias: str, canonical: str
    ):
        assert vector_for(alias) == vector_for(canonical)

    def test_alias_actually_moves_the_crypto_feature(self):
        """The vectors are equal, but equal is only meaningful if they differ
        from the unrecognized case. Without this the assertions above would
        pass if every category scored 0.0."""
        crypto = vector_for(CANONICAL_CRYPTO)
        unknown = vector_for("zzyzx-plugh-frobnitz")
        assert crypto[FEATURE_NAMES.index("is_crypto")] == 1.0
        assert unknown[FEATURE_NAMES.index("is_crypto")] == 0.0

    def test_case_and_whitespace_are_normalized(self):
        """Not cosmetic: '  BITCOIN  ' previously missed every set test."""
        assert normalize_category("  BITCOIN  ") == CANONICAL_CRYPTO
        assert normalize_category("Crypto-Exchange") == CANONICAL_CRYPTO

    def test_separators_are_equivalent(self):
        """`crypto-exchange` and `crypto exchange` are the same word to a
        human; they were two different misses."""
        assert normalize_category("crypto-exchange") == normalize_category(
            "crypto exchange"
        )

    def test_normalization_is_idempotent(self):
        once = normalize_category("crypto-exchange")
        assert normalize_category(once) == once

    def test_a_canonical_name_normalizes_to_itself(self):
        for canonical in KNOWN_MERCHANT_CATEGORIES:
            assert normalize_category(canonical) == canonical

    def test_none_and_empty_normalize_to_empty(self):
        """`merchant_category` is nullable; absent is not an unknown category."""
        assert normalize_category(None) == ""
        assert normalize_category("") == ""
        assert normalize_category("   ") == ""


class TestUnrecognizedValuesAreVisible:
    """The second half of the defect: silence is what made it dangerous."""

    def test_unknown_value_increments_a_counter(self):
        FeatureEngine().transform(
            {"amount": 100.0, "merchant_category": "zzyzx-plugh-frobnitz"}
        )
        assert snapshot().get("unknown_merchant_category", 0) == 1

    def test_recognized_value_does_not_increment_the_counter(self):
        FeatureEngine().transform({"amount": 100.0, "merchant_category": "bitcoin"})
        assert snapshot().get("unknown_merchant_category", 0) == 0

    def test_absent_category_does_not_increment_the_counter(self):
        """A transaction with no category is incomplete, not suspicious."""
        FeatureEngine().transform({"amount": 100.0, "merchant_category": None})
        assert snapshot().get("unknown_merchant_category", 0) == 0

    def test_counter_accumulates_across_transactions(self):
        engine = FeatureEngine()
        for _ in range(3):
            engine.transform({"amount": 100.0, "merchant_category": "no-such-thing"})
        assert snapshot()["unknown_merchant_category"] == 3

    def test_unknown_value_is_logged(self, caplog: pytest.LogCaptureFixture):
        with caplog.at_level(logging.WARNING, logger="src.services.feature_engine"):
            FeatureEngine().transform(
                {"amount": 100.0, "merchant_category": "zzyzx-plugh-frobnitz"}
            )
            # Asserted inside the context: pytest removes the capture handler on
            # exit, so `caplog.text` is empty afterwards.
            #
            # The logged value is the NORMALIZED form ('zzyzx plugh
            # frobnitz'), which is also what belongs in the line — it is the key
            # an operator would add to CATEGORY_ALIASES, and the raw spelling
            # may be caller-supplied free text.
            assert "zzyzx plugh frobnitz" in caplog.text
            assert "unknown_merchant_category" in caplog.text

    def test_unknown_value_is_logged_once_per_distinct_value(self, caplog: pytest.LogCaptureFixture):
        """Log per distinct value, not per transaction: a merchant that always
        sends the same unknown value should produce one warning, not one per
        scored transaction. The counter still counts every occurrence.

        'cripto' is deliberately NOT used as the example: it is now an alias,
        so it resolves and must not warn. That is the point of the alias work."""
        engine = FeatureEngine()
        with caplog.at_level(logging.WARNING, logger="src.services.feature_engine"):
            for _ in range(5):
                engine.transform(
                    {"amount": 100.0, "merchant_category": "zzyzx-plugh-frobnitz"}
                )
            assert caplog.text.count("unknown_merchant_category") == 1
        assert snapshot()["unknown_merchant_category"] == 5

    def test_two_distinct_unknown_values_log_twice(self, caplog: pytest.LogCaptureFixture):
        engine = FeatureEngine()
        with caplog.at_level(logging.WARNING, logger="src.services.feature_engine"):
            engine.transform({"amount": 100.0, "merchant_category": "zzyzx-a"})
            engine.transform({"amount": 100.0, "merchant_category": "zzyzx-b"})
            assert caplog.text.count("unknown_merchant_category") == 2

    def test_a_known_low_risk_category_is_not_counted_as_unknown(self):
        """The vocabulary is broader than the risky set. A grocery purchase is
        a known category that carries no risk, and counting it as unknown
        would make the counter useless for the thing it exists to detect."""
        for category in ("retail", "grocery", "restaurant", "travel", "utilities"):
            FeatureEngine().transform({"amount": 100.0, "merchant_category": category})
        assert snapshot().get("unknown_merchant_category", 0) == 0


class TestRuleEngineSharesTheSameVocabulary:
    """The feature engine and the rule engine must not disagree about what a
    category is. They are two readers of one field; before the fix they had
    two independent alias lookups that happened to be the same two lines."""

    def test_rule_engine_sees_the_adversarial_category_through_an_alias(self):
        engine = RuleEngine()
        tx = {
            "amount": 100.0,
            "merchant_name": "Some Exchange",
            "merchant_category": "cripto",
            "timestamp": "2026-09-29T14:00:00",
        }
        score, fired = engine.evaluate(tx, {"recent_transactions": 0})
        assert "unusual_merchant" in fired
        assert score == RuleEngine.WEIGHTS["unusual_merchant"]

    def test_rule_engine_fires_velocity_burst_through_an_alias(self):
        engine = RuleEngine()
        tx = {
            "amount": 100.0,
            "merchant_name": "Some Exchange",
            "merchant_category": "crypto-exchange",
            "timestamp": "2026-09-29T14:00:00",
        }
        _, fired = engine.evaluate(tx, {"recent_transactions": 5})
        assert "velocity_burst" in fired

    def test_rule_engine_does_not_count_the_alias_against_the_feature_engine(self):
        """One observation per scored transaction, not two.

        The feature engine is the single owner of the observation. The rule
        engine runs on the same transaction in the same pipeline, and counting
        in both would double every unknown-category request for one event.
        """
        from src.core import counters

        engine = RuleEngine()
        engine.evaluate(
            {
                "amount": 100.0,
                "merchant_name": "M",
                "merchant_category": "zzyzx-plugh-frobnitz",
                "timestamp": "2026-09-29T14:00:00",
            },
            {"recent_transactions": 0},
        )
        assert snapshot().get("unknown_merchant_category", 0) == 0
        assert counters is not None


class TestConstants:
    def test_every_alias_maps_to_a_known_category(self):
        """An alias pointing outside the vocabulary would reintroduce the miss
        on the far side."""
        for alias, canonical in CATEGORY_ALIASES.items():
            assert canonical in KNOWN_MERCHANT_CATEGORIES, (
                f"alias {alias!r} maps to {canonical!r}, which is not a known category"
            )

    def test_every_known_category_resolves_to_itself(self):
        for category in KNOWN_MERCHANT_CATEGORIES:
            assert CATEGORY_ALIASES.get(category, category) == category

    def test_every_advertised_spelling_normalizes_to_its_canonical(self):
        """The contract that makes it safe to WRITE an alias into a corpus.

        A producer emitting `"cripto"` only produces a truthful row if the
        serving path turns it back into `"cryptocurrency"` before the features
        are built. A spelling that failed to round-trip would turn spelling
        variety into mislabelled training rows, so this is asserted directly on
        the constant rather than only through whatever consumes it.
        """
        from src.core.ml_constants import CATEGORY_ALIAS_SPELLINGS

        for canonical, spellings in CATEGORY_ALIAS_SPELLINGS.items():
            for spelling in spellings:
                assert normalize_category(spelling) == canonical, (
                    f"{spelling!r} is advertised as a spelling of {canonical!r} "
                    f"but normalizes to {normalize_category(spelling)!r}"
                )

    def test_no_advertised_spelling_is_the_canonical_name_itself(self):
        """An identity entry is not a spelling variant.

        `"adult": "adult"` and `"pharmacy": "pharmacy"` are in the forward table
        because they are keyed like an alias, not because they are one. If they
        leaked into the reverse table, a producer could "emit an alias" that was
        the canonical string — the dead branch this constant replaced.
        """
        from src.core.ml_constants import CATEGORY_ALIAS_SPELLINGS

        for canonical, spellings in CATEGORY_ALIAS_SPELLINGS.items():
            assert canonical not in spellings, (
                f"{canonical!r} is listed as its own alias spelling"
            )

    def test_the_three_spellable_risk_categories_are_covered(self):
        """The categories the corpus generator draws all have real variants.

        Guarding this by name is deliberate: it fails loudly if someone adds a
        risk category to the generator's vocabulary and forgets it has no
        aliases, which is the exact shape of the bug being fixed here.
        """
        from src.core.ml_constants import CATEGORY_ALIAS_SPELLINGS

        for canonical in ("cryptocurrency", "gambling", "money_transfer"):
            assert CATEGORY_ALIAS_SPELLINGS.get(canonical), (
                f"{canonical!r} has no alias spelling, so the corpus generator "
                f"cannot emit a variant for it"
            )

    def test_the_risky_vocabulary_normalizes_into_the_known_vocabulary(self):
        """A risky category the normalizer cannot produce is unreachable.

        The risky sets deliberately carry alias spellings alongside the
        canonical names ("Includes both canonical names and recognized aliases
        so consumers can match against a single set without pre-normalization"
        — the header comment). That comment is now stale: both in-process
        consumers normalize first. The sets are left alone because the training
        scripts generate from them, and changing generated training data is a
        much larger change than this finding is. The invariant that matters is
        that every one of those entries normalizes to a known category, which
        is what makes the rules reachable no matter which spelling arrives.
        """
        from src.core.ml_constants import (
            MERCHANT_ADVERSARIAL_CATEGORIES,
            MERCHANT_REGULATED_CATEGORIES,
            MERCHANT_RISK_CATEGORIES,
        )

        for risky in (
            MERCHANT_RISK_CATEGORIES
            | MERCHANT_ADVERSARIAL_CATEGORIES
            | MERCHANT_REGULATED_CATEGORIES
        ):
            assert normalize_category(risky) in KNOWN_MERCHANT_CATEGORIES, (
                f"risky category {risky!r} normalizes to "
                f"{normalize_category(risky)!r}, which is not known"
            )
