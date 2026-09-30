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

import importlib
import logging
from pathlib import Path

import pytest

from src.core.counters import snapshot
from src.core.ml_constants import (
    CATEGORY_ALIASES,
    KNOWN_MERCHANT_CATEGORIES,
    MERCHANT_RISK_CATEGORIES,
    normalize_category,
)
from src.services.feature_engine import FEATURE_NAMES, FeatureEngine
from src.services.rule_engine import RuleEngine

CANONICAL_CRYPTO = "cryptocurrency"

#: What "a risk category" means for the derivation below. Alias spellings are
#: included on purpose: a generator may legitimately list `crypto` rather than
#: `cryptocurrency`, and the derivation normalizes, so both forms resolve.
RISK_CATEGORY_UNIVERSE = MERCHANT_RISK_CATEGORIES

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


#: The two producers that draw a risk category, and therefore the two whose
#: alias emission can go dead. `train_xgboost_aligned.generate_synthetic_data`
#: is the training corpus; `generate_synthetic_data.generate_fraudulent_tx` is
#: the demo/seed generator. Both build their own risk list inline.
RISK_VOCABULARY_GENERATORS = (
    ("trainer", "scripts.train_xgboost_aligned"),
    ("demo", "scripts.generate_synthetic_data"),
)


def _risk_vocabulary_of(module) -> frozenset[str]:
    """The risk categories a generator module can draw, read from the module.

    Derived by PARSING, not by hardcoding, because the whole failure this guards
    is a name being added to a generator and not to a list of names in a test
    file. The previous version of this guard hardcoded
    `("cryptocurrency", "gambling", "money_transfer")` while both generators
    built five categories, so `adult` and `pharmacy` were unguarded and adding
    a sixth would have restored the silent dead branch with the test still
    green.

    The selection rule is a list literal all of whose members normalize into
    `MERCHANT_RISK_CATEGORIES`. Requiring that membership is deliberate rather
    than incidental: `MERCHANT_RISK_CATEGORIES` is the feature engine's
    contract, so a generator drawing a category that is not in it is drawing
    something `merchant_risk_level` scores as 0.0 — a different defect, and one
    this file's first test already catches.

    It is still a heuristic, so it is checked rather than trusted. A module
    yielding zero such lists, or more than one, fails loudly — a guard that
    matches nothing guards nothing, and that is the defect this exercise keeps
    finding. The message names the members that failed the membership test,
    because "0 lists found" on its own sends you looking in the wrong place.
    """
    import ast

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    lists: list[list[str]] = []
    near_misses: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        elements = node.value.elts
        if not elements or not all(
            isinstance(e, ast.Constant) and isinstance(e.value, str) for e in elements
        ):
            continue
        values = [e.value for e in elements]  # type: ignore[attr-defined]
        if all(normalize_category(v) in RISK_CATEGORY_UNIVERSE for v in values):
            lists.append(values)
        elif sum(
            normalize_category(v) in RISK_CATEGORY_UNIVERSE for v in values
        ) >= len(RISK_CATEGORY_UNIVERSE):
            # Mostly a risk vocabulary with one outsider in it. Record it so
            # the failure below can say WHICH member is not registered.
            near_misses.extend(
                v for v in values if normalize_category(v) not in RISK_CATEGORY_UNIVERSE
            )

    assert len(lists) == 1, (
        f"{module.__name__} yielded {len(lists)} list literals whose members are "
        f"all known risk categories ({lists}), expected exactly 1."
        + (
            f" Members that are not in MERCHANT_RISK_CATEGORIES: "
            f"{sorted(set(near_misses))}. A generator can only draw a risk "
            f"category that the feature engine also treats as one — an "
            f"unregistered name scores merchant_risk_level 0.0."
            if near_misses
            else " Either the generator's risk vocabulary moved somewhere this "
            "does not look, or this derivation has stopped matching the thing "
            "it is supposed to derive, and a guard that matches nothing guards "
            "nothing."
        )
    )
    return frozenset(normalize_category(v) for v in lists[0])


class TestGeneratorRiskVocabularyIsFullyCovered:
    """W-4: every risk category a generator can draw must be emittable.

    The corpus generator emits alias spellings so the model is trained on the
    same normalized vocabulary a live request produces. That emission is a
    lookup keyed by canonical name, so a canonical name with no spellings is a
    silently dead branch — the exact defect 15a8eec and 7e81876 fixed, and the
    exact defect the removed hardcoded-by-name guard could not see coming.

    Derived from the generators, not transcribed from them, so adding a risk
    category cannot pass unnoticed.
    """

    def test_each_generator_exposes_exactly_one_risk_vocabulary(self):
        for label, dotted in RISK_VOCABULARY_GENERATORS:
            module = importlib.import_module(dotted)
            vocabulary = _risk_vocabulary_of(module)
            assert vocabulary, f"{label} generator yielded an empty vocabulary"

    def test_every_category_a_generator_draws_can_emit_a_spelling(self):
        """The load-bearing one.

        A category drawn by a generator that has no alias spelling cannot be
        emitted as anything but itself, so the corpus trains on the canonical
        name only and the normalization every live request depends on is never
        exercised. Either it has spellings, or it is declared alias-free in
        `CATEGORIES_WITHOUT_ALIAS_SPELLINGS` — a sentence a human wrote and a
        reviewer can disagree with.
        """
        from src.core.ml_constants import (
            CATEGORIES_WITHOUT_ALIAS_SPELLINGS,
            CATEGORY_ALIAS_SPELLINGS,
        )

        for label, dotted in RISK_VOCABULARY_GENERATORS:
            module = importlib.import_module(dotted)
            for canonical in sorted(_risk_vocabulary_of(module)):
                assert CATEGORY_ALIAS_SPELLINGS.get(canonical) or (
                    canonical in CATEGORIES_WITHOUT_ALIAS_SPELLINGS
                ), (
                    f"{label} generator draws {canonical!r}, which has no alias "
                    f"spelling, so it cannot emit a variant and the corpus "
                    f"generator's alias branch is dead for it. Add spellings to "
                    f"CATEGORY_ALIASES, or declare it in "
                    f"CATEGORIES_WITHOUT_ALIAS_SPELLINGS if it genuinely has "
                    f"none."
                )

    def test_the_derived_vocabulary_covers_more_than_the_old_hardcoded_list(self):
        """Why the derivation exists, stated as an assertion about the old guard.

        The removed test named three categories; both generators draw five.
        If this ever fails the other way — the derived vocabulary shrinking to
        three — something has removed risk categories from the generators and
        that deserves a look of its own.
        """
        trainer, demo = (
            _risk_vocabulary_of(importlib.import_module(dotted))
            for _, dotted in RISK_VOCABULARY_GENERATORS
        )
        assert len(trainer) == 5, f"trainer risk vocabulary is {sorted(trainer)}"
        assert trainer == demo, (
            f"the two generators disagree on their risk vocabulary: "
            f"{sorted(trainer)} vs {sorted(demo)}. They are separate literals "
            f"in separate files and nothing keeps them in step."
        )
        assert {"adult", "pharmacy"} <= trainer, (
            "the two categories the old hardcoded guard omitted are gone from "
            "the generator vocabulary"
        )

    def test_a_declared_alias_free_category_really_has_no_spellings(self):
        """The escape hatch cannot be used to silence a category that has them.

        Otherwise adding one name to `CATEGORIES_WITHOUT_ALIAS_SPELLINGS`
        would switch the coverage guard off for that category forever, which
        is the same class of defect as the hardcoded list it replaced.
        """
        from src.core.ml_constants import (
            CATEGORIES_WITHOUT_ALIAS_SPELLINGS,
            CATEGORY_ALIAS_SPELLINGS,
        )

        for canonical in sorted(CATEGORIES_WITHOUT_ALIAS_SPELLINGS):
            assert not CATEGORY_ALIAS_SPELLINGS.get(canonical), (
                f"{canonical!r} is declared alias-free but does have spellings "
                f"{CATEGORY_ALIAS_SPELLINGS[canonical]}. Remove it from "
                f"CATEGORIES_WITHOUT_ALIAS_SPELLINGS; declaring it exempts it "
                f"from the coverage check for no reason."
            )

    def test_a_declared_alias_free_category_is_actually_drawn_by_a_generator(self):
        """A declaration about a category nothing draws is a stale comment.

        It is allowed to be wrong in one direction only: a generator may drop a
        category, but the declaration must not outlive it.
        """
        from src.core.ml_constants import CATEGORIES_WITHOUT_ALIAS_SPELLINGS

        drawn = set().union(
            *(
                _risk_vocabulary_of(importlib.import_module(dotted))
                for _, dotted in RISK_VOCABULARY_GENERATORS
            )
        )
        orphans = set(CATEGORIES_WITHOUT_ALIAS_SPELLINGS) - drawn
        assert not orphans, (
            f"{sorted(orphans)} declared alias-free but drawn by no generator. "
            f"The declaration has outlived the thing it describes."
        )

    def test_the_declaration_is_empty_while_every_category_has_spellings(self):
        """Currently true, and the reason the set above exists at all.

        Not a style assertion: a non-empty declaration means somebody made a
        decision, and this test is the reminder that the decision needs
        reviewing rather than assuming.
        """
        from src.core.ml_constants import CATEGORIES_WITHOUT_ALIAS_SPELLINGS

        assert CATEGORIES_WITHOUT_ALIAS_SPELLINGS == frozenset(), (
            f"CATEGORIES_WITHOUT_ALIAS_SPELLINGS is "
            f"{sorted(CATEGORIES_WITHOUT_ALIAS_SPELLINGS)}. All five categories "
            f"the generators draw have spellings, so an entry here is a new "
            f"claim that needs a human to agree with it."
        )


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
