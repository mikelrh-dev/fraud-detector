"""D1: the merchant NAME reaches the features and the rules.

The transaction that produced this file
---------------------------------------
400,000 USD, ``merchant_name="binance"``, ``merchant_category="retail"``.
Ensemble 24.1/100, "legitimate", ``high_amount`` fired, ML 0.3.

A quarter of bitcoin at an exchange is not a borderline case, and nothing in
the score was borderline either. ``merchant_name`` was not consulted by ANY
consumer. ``FeatureEngine`` derived ``is_crypto`` and ``merchant_risk_level``
from the category alone, and ``RuleEngine`` derived its adversarial and
regulated tiers from the category alone, so two of the ten features — and the
only two that know what kind of merchant this is — were decided by whichever
string the payload happened to carry. Writing "binance" changed nothing at all.

What is asserted here
---------------------
1. The tokenization rule, on the cases that have to work and the ones that must
   not. Substring matching would pass the first group and fail the second.
2. That ``is_crypto`` AND ``merchant_risk_level`` both read the name, not one
   of them.
3. That the rule engine reads the SAME vocabulary, so a crypto merchant is not
   scored as crypto by the features and as retail by the rules — the D7-3
   disagreement, moved one field over.
4. That a name can only RAISE the tier. A recognised venue must not be
   overridable by a benign category, and a name nothing matches must not be
   treated as a safe one.
5. That the unknown-category counter still fires for a bad CATEGORY even when
   the NAME was recognised: they are separate facts, and D3's edge validation
   does not authorise deleting the instrumentation for the batch consumers that
   never reach an endpoint.
"""

import math

import pytest

from src.core import counters
from src.core.ml_constants import (
    KNOWN_MERCHANT_CATEGORIES,
    KNOWN_MERCHANT_PHRASES,
    MERCHANT_ADVERSARIAL_CATEGORIES,
    MERCHANT_REGULATED_CATEGORIES,
    _merchant_tokens,
    merchant_category_from_name,
)
from src.services.feature_engine import FEATURE_NAMES, FeatureEngine
from src.services.rule_engine import RuleEngine

RISK = FEATURE_NAMES.index("merchant_risk_level")
CRYPTO = FEATURE_NAMES.index("is_crypto")

DAY = "2026-10-01T14:00:00+00:00"
NIGHT = "2026-10-01T03:00:00+00:00"


@pytest.fixture(autouse=True)
def _reset_observation_state():
    """Both observation channels are process-global; clear them per test."""
    from src.services import feature_engine

    counters.reset()
    feature_engine._WARNED_CATEGORIES.clear()
    yield
    counters.reset()
    feature_engine._WARNED_CATEGORIES.clear()


def features_for(merchant_name: str, category: str | None = "retail") -> list[float]:
    return list(
        FeatureEngine().transform(
            {
                "amount": 400_000.0,
                "merchant_name": merchant_name,
                "merchant_category": category,
                "timestamp": DAY,
            }
        )
    )


class TestTokenization:
    """The rule, stated so it can be disagreed with."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("binance", ("binance",)),
            ("BINANCE", ("binance",)),
            ("Binance", ("binance",)),
            # Every punctuation a merchant name actually arrives with.
            ("BINANCE.COM", ("binance", "com")),
            ("binance.com", ("binance", "com")),
            ("Binance-Exchange", ("binance", "exchange")),
            ("binance_exchange", ("binance", "exchange")),
            ("Binance / Berlin", ("binance", "berlin")),
            ("  Binance   Berlin  ", ("binance", "berlin")),
            ("Binance  Berlin", ("binance", "berlin")),
            ("Binance,Berlin;DE", ("binance", "berlin", "de")),
            # Punctuation-only and empty produce no tokens, not a token of "".
            ("...", ()),
            ("   ", ()),
            ("", ()),
            (None, ()),
            # Non-ASCII letters are letters, so a Spanish merchant name
            # tokenizes instead of collapsing to nothing.
            ("Farmacia San Juan", ("farmacia", "san", "juan")),
            ("Ñandú Tienda", ("ñandú", "tienda")),
        ],
    )
    def test_tokenization(self, raw, expected) -> None:
        assert _merchant_tokens(raw) == expected

    @pytest.mark.parametrize("bad", [123, 1.5, ["Merchant"], {"name": "M"}, object()])
    def test_a_non_string_name_never_raises(self, bad) -> None:
        """A12's contract, applied to the new reader.

        Batch and replay consumers pass plain dicts, so a `merchant_name` that
        is an int or an object reaches here. It has to answer "I recognise no
        merchant in that", never raise.
        """
        assert merchant_category_from_name(bad) == ""


class TestTheVocabularyItself:
    def test_every_key_survives_the_round_trip(self) -> None:
        """A key written in the wrong form matches nothing, silently.

        `_PHRASE_INDEX` tokenizes the keys, so `"crypto.com"` or
        `"Binance Exchange"` would produce an entry that can never match — the
        exact silent-miss this change exists to remove, committed as data.
        """
        for phrase, category in KNOWN_MERCHANT_PHRASES.items():
            assert _merchant_tokens(phrase) == tuple(phrase.split()), (
                f"{phrase!r} is not in the canonical form (lowercase, "
                "space-separated alphanumeric tokens), so it will never match a "
                "merchant name"
            )
            assert _merchant_tokens(phrase), f"{phrase!r} tokenizes to nothing"

    def test_every_entry_names_a_known_risk_category(self) -> None:
        """An entry pointing outside the vocabulary reintroduces the miss on the
        far side — and a name match feeding a non-risky category would make the
        name able to LOWER risk, which the design forbids."""
        for phrase, category in KNOWN_MERCHANT_PHRASES.items():
            assert category in KNOWN_MERCHANT_CATEGORIES, (
                f"{phrase!r} maps to {category!r}, which is not a known category"
            )
            assert category in (
                MERCHANT_ADVERSARIAL_CATEGORIES | MERCHANT_REGULATED_CATEGORIES
            ), f"{phrase!r} maps to {category!r}, which is not a risk category"

    def test_no_entry_is_merely_a_category_word(self) -> None:
        """The admissibility rule, enforced rather than described.

        A SINGLE-token entry must IDENTIFY a merchant, not DESCRIBE a kind of
        business. If a bare `crypto` or `casino` entry ever appears here, this
        fails — which is the point, because such an entry fires on "Crypto
        Consulting" and "Casino Barcelona": the payload choosing the features
        again, one field over. `merchant_category` is the validated field for
        that question.

        A MULTI-token phrase is a different claim and is allowed to contain a
        word that reads like a category: `crypto com` is the brand Crypto.com, and
        it matches "Crypto.com", "Crypto.Com Berlin" and "Crypto Com SA" while
        `crypto` alone would match every one of them *and* "Crypto Consulting".
        The phrase is what identifies the merchant; the single token does not.
        """
        descriptors = {
            "crypto",
            "cryptocurrency",
            "casino",
            "gambling",
            "bet",
            "bets",
            "apuestas",
            "apuesta",
            "juego",
            "juegos",
            "adult",
            "adulto",
            "exchange",
            "pharmacy",
            "farmacia",
            "money",
            "transfer",
            "transferencia",
            "remesa",
            "remesas",
        }
        for phrase in KNOWN_MERCHANT_PHRASES:
            tokens = phrase.split()
            if len(tokens) != 1:
                continue
            assert tokens[0] not in descriptors, (
                f"{phrase!r} is a bare category descriptor, not a merchant "
                "identifier. A one-token entry here fires on any merchant whose "
                "name contains that word — 'Crypto Consulting', 'Casino "
                "Barcelona' — which is the payload choosing the features again. "
                "Write the full brand instead, as a phrase."
            )

    def test_the_reported_transaction_has_an_entry(self) -> None:
        """The vocabulary is not decorative: the name in the finding is in it."""
        assert KNOWN_MERCHANT_PHRASES["binance"] == "cryptocurrency"


class TestMatching:
    """Contiguous-run matching: word-boundary exact, context tolerant."""

    @pytest.mark.parametrize(
        "name",
        [
            "binance",
            "BINANCE",
            "Binance Exchange",
            "Binance  Berlin",
            "BINANCE.COM",
            "Binance.com.ar",
            "binance_berlin",
            "Binance / Berlin",
            "Binance, Berlin",
            "Binance GmbH",
            "Binance-Berlin",
            "Berlin Binance",
        ],
    )
    def test_the_real_merchants_match(self, name: str) -> None:
        assert merchant_category_from_name(name) == "cryptocurrency"

    @pytest.mark.parametrize(
        "name",
        [
            # Every one of these CONTAINS "binance" as a substring, and none of
            # them is an exchange. A substring matcher fires on all six; this is
            # the whole reason the rule is token-based.
            "BinanceCard",
            "PreBinance",
            "Rebinance",
            "binances",
            "Rebinanzas SA",
            "Rebinancen",
            # And the same for a multi-token entry: contains "crypto com" as a
            # substring, is not a crypto exchange.
            "cryptocurrency consulting",
            "CryptoCom2",
        ],
    )
    def test_an_incidental_substring_does_not_match(self, name: str) -> None:
        assert merchant_category_from_name(name) == ""

    @pytest.mark.parametrize(
        "name",
        [
            "Amazon",
            "Walmart",
            "Starbucks",
            "Supermercado del Barrio",
            "Whole Foods",
            "Shell Gas",
        ],
    )
    def test_an_ordinary_retail_merchant_matches_nothing(self, name: str) -> None:
        assert merchant_category_from_name(name) == ""

    def test_a_name_worth_nothing_returns_the_empty_answer_not_a_guess(self) -> None:
        """Same convention as `normalize_category`: no news is not bad news."""
        assert merchant_category_from_name("Tienda del Sur") == ""
        assert merchant_category_from_name(None) == ""
        assert merchant_category_from_name("") == ""

    def test_resolution_is_deterministic_when_two_phrases_are_present(self) -> None:
        """A name carrying two known phrases must resolve the same way always.

        Order-dependence would make the score of one transaction depend on
        dictionary iteration order — the kind of defect that reproduces on one
        machine and not another.
        """
        name = "Crypto.com Berlin"
        results = {merchant_category_from_name(name) for _ in range(50)}
        assert results == {"cryptocurrency"}

    def test_the_longest_phrase_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The resolution rule itself, on data the live table does not contain.

        No two entries in `KNOWN_MERCHANT_PHRASES` currently overlap, so this
        rule has no observable effect on today's vocabulary — which is exactly
        why it needs a test that would still be there when someone adds an
        overlapping pair. The index and the length order are swapped in for a
        synthetic pair that does overlap, because the resolver reads them at call
        time; monkeypatch restores both on teardown.
        """
        import src.core.ml_constants as ml_constants

        monkeypatch.setattr(
            ml_constants,
            "_PHRASE_INDEX",
            {
                ("crypto",): "cryptocurrency",
                ("crypto", "exchange"): "gambling",
            },
        )
        monkeypatch.setattr(ml_constants, "_PHRASE_LENGTHS", (2, 1))

        # Longest first: the two-token entry wins even though the one-token
        # entry starts at the same position.
        assert merchant_category_from_name("Crypto Exchange Berlin") == "gambling"
        # One-token entry still matches on its own.
        assert merchant_category_from_name("Crypto Berlin") == "cryptocurrency"


class TestFeaturesReadTheName:
    def test_the_reported_transaction_is_no_longer_a_retail_purchase(self) -> None:
        """The defect, restated as the measurement that closes it.

        Before D1 this vector was `merchant_risk_level = 0.0, is_crypto = 0.0` —
        byte-identical to a genuine 400,000 EUR retail purchase.
        """
        vector = features_for("binance", "retail")
        assert vector[RISK] == 1.0
        assert vector[CRYPTO] == 1.0

    def test_both_features_read_the_name_not_just_one(self) -> None:
        """The original code had two separate lines and both were category-only.

        Fixing `is_crypto` alone would have left `merchant_risk_level` at 0.0 for
        the same transaction, and vice versa — half a fix that still scores the
        finding's transaction as retail on one of the two features.
        """
        vector = features_for("Coinbase", "grocery")
        assert vector[RISK] == 1.0
        assert vector[CRYPTO] == 1.0

    def test_a_gambling_brand_moves_merchant_risk_without_being_crypto(self) -> None:
        """The name maps to a CATEGORY and the existing sets decide what that
        means. A gambling brand must not light up `is_crypto`."""
        vector = features_for("Bet365", "retail")
        assert vector[RISK] == 1.0
        assert vector[CRYPTO] == 0.0

    def test_a_name_that_matches_nothing_changes_nothing(self) -> None:
        assert features_for("BinanceCard", "retail") == features_for(
            "Amazon", "retail"
        )


class TestTheNameCanOnlyRaise:
    def test_a_recognised_venue_beats_a_benign_category(self) -> None:
        """Name first. A name identifies a business; a category labels one.

        With the precedence reversed, `merchant_category=retail` would erase a
        recognised exchange — and the caller picks the category, which is the
        entire problem D3 closes at the edge.
        """
        vector = features_for("binance", "grocery")
        assert (vector[RISK], vector[CRYPTO]) == (1.0, 1.0)

    def test_a_recognised_name_overrules_a_regulated_category_in_the_rules(self) -> None:
        """`money_transfer` is corroboration-only; an exchange is adversarial.

        A name hit on a crypto venue with the category `pharmacy` has to land in
        the adversarial tier, because otherwise a caller could downgrade a
        recognised exchange by labelling it a regulated business.
        """
        _, fired = RuleEngine().evaluate(
            {
                "amount": 100.0,
                "merchant_name": "Binance Berlin",
                "merchant_category": "money_transfer",
                "timestamp": DAY,
            }
        )
        assert "unusual_merchant" in fired

    def test_an_unrecognised_name_never_lowers_a_risky_category(self) -> None:
        _, fired = RuleEngine().evaluate(
            {
                "amount": 100.0,
                "merchant_name": "BinanceCard",
                "merchant_category": "cryptocurrency",
                "timestamp": DAY,
            }
        )
        assert "unusual_merchant" in fired


class TestOneVocabularyTwoReaders:
    """D7-3's principle, one field over.

    The feature engine and the rule engine are two readers of the same
    transaction in the same pipeline. When they had two independent alias
    lookups they were the same two lines; when the name was unreadable they both
    read nothing. Either way the two could disagree about a merchant, and a
    transaction scored as crypto by one layer and retail by the other is the
    same defect D7-3 was written for.
    """

    @pytest.mark.parametrize("name", sorted(KNOWN_MERCHANT_PHRASES))
    def test_both_layers_reach_the_same_conclusion(self, name: str) -> None:
        """Every entry, checked against both readers.

        Derived from the table rather than transcribed, so an entry cannot be
        added and land in one engine only.
        """
        category = KNOWN_MERCHANT_PHRASES[name]
        vector = features_for(name, "retail")
        assert vector[RISK] == 1.0, f"{name!r} did not reach merchant_risk_level"

        _, fired = RuleEngine().evaluate(
            {
                "amount": 100.0,
                "merchant_name": name,
                "merchant_category": "retail",
                "timestamp": DAY,
            }
        )
        if category in MERCHANT_ADVERSARIAL_CATEGORIES:
            assert "unusual_merchant" in fired, (
                f"{name!r} maps to the adversarial {category!r} but the rule "
                "engine did not treat it as adversarial"
            )
        else:
            assert category in MERCHANT_REGULATED_CATEGORIES
            assert "unusual_merchant" not in fired, (
                f"{name!r} maps to the regulated {category!r}, which is "
                "corroboration-only and must not fire on its own"
            )

    def test_the_rule_engine_fires_velocity_burst_through_the_name(self) -> None:
        """The third consumer of the risk vocabulary, and the one the original
        defect reached through the category as well."""
        _, fired = RuleEngine().evaluate(
            {
                "amount": 100.0,
                "merchant_name": "Binance Berlin",
                "merchant_category": "retail",
                "timestamp": DAY,
            },
            {"recent_transactions": 5},
        )
        assert "velocity_burst" in fired

    def test_the_rule_engine_fires_off_hours_crypto_through_the_name(self) -> None:
        _, fired = RuleEngine().evaluate(
            {
                "amount": 100.0,
                "merchant_name": "Binance Berlin",
                "merchant_category": "retail",
                "timestamp": NIGHT,
            }
        )
        assert "off_hours_crypto" in fired
        assert "unusual_hours" in fired

    def test_the_rule_engine_does_not_double_count_the_unknown_category(self) -> None:
        """One observation per transaction, as D7-3 established for aliases."""
        RuleEngine().evaluate(
            {
                "amount": 100.0,
                "merchant_name": "Binance Berlin",
                "merchant_category": "zzyzx-plugh-frobnitz",
                "timestamp": DAY,
            }
        )
        assert counters.snapshot().get("unknown_merchant_category", 0) == 0


class TestTheCounterStillFires:
    """D3 validated the edge. It did not remove defence in depth.

    ``FeatureEngine`` is driven by batch imports, replay tools and workers that
    never pass through ``TransactionCreate``, so the unknown-category
    observation is the only instrumentation those paths have. It is also the
    instrumentation that explains WHY D1 exists, so removing it would delete the
    evidence for the defect being fixed.
    """

    def test_an_unknown_category_is_counted_even_when_the_name_is_known(self) -> None:
        FeatureEngine().transform(
            {
                "amount": 400_000.0,
                "merchant_name": "Binance Berlin",
                "merchant_category": "zzyzx-plugh-frobnitz",
                "timestamp": DAY,
            }
        )
        assert counters.snapshot().get("unknown_merchant_category", 0) == 1

    def test_the_category_and_the_name_are_answered_independently(self) -> None:
        """A known name must not mask an unknown category, and vice versa."""
        FeatureEngine().transform(
            {
                "amount": 100.0,
                "merchant_name": "Supermercado",
                "merchant_category": "zzyzx-plugh-frobnitz",
                "timestamp": DAY,
            }
        )
        assert counters.snapshot()["unknown_merchant_category"] == 1


class TestTheFindingIsClosed:
    """The end-to-end shape of the defect, as a single measurement.

    Measured through `ScoringService`, WITH the model loaded, because a degraded
    ensemble is not the production number and asserting against one would measure
    the wrong thing. `ScoringService` does not load the model itself —
    `api/v1/transactions.py` does that at import — so a service built here would
    otherwise report the ML layer as absent and redistribute its 0.25 to the
    rules, quietly making every assertion below true for the wrong reason.
    """

    @pytest.fixture(scope="class")
    def service(self):
        import asyncio

        from src.services.ml_model import MLModelService
        from src.services.scoring_service import ScoringService

        ml = MLModelService()
        if not ml.load_model():
            pytest.skip(f"model at {ml.model_path} failed to load")
        scoring = ScoringService(ml_service=ml)
        return lambda tx: asyncio.run(
            scoring.compute_scores(
                tx,
                {"recent_transactions": 0, "graph_features": {}},
                {"avg_amount": 0.0, "std_amount": 0.0},
            )
        )

    def test_the_reported_transaction_scores_as_fraud_not_legitimate(self, service) -> None:
        """Rule score, ML score and ensemble, for the transaction in the plan.

        400,000 is above the last tier boundary of 50,000, so the fraud threshold
        is 40. For the rule layer to carry the transaction there on its own it
        needs more than 40 / 0.60 = 66.67, and 35 (base) + 20.82 (magnitude) +
        20 (adversarial merchant) = 75.82 clears it.
        """
        transaction = {
            "amount": 400_000.0,
            "merchant_name": "binance",
            "merchant_category": "retail",
            "timestamp": DAY,
        }
        rule_score, fired = RuleEngine().evaluate(transaction)
        assert rule_score > 66.67, (
            "the rule score alone must exceed 40 / 0.60, otherwise the ensemble "
            "cannot reach fraud even with both other layers silent"
        )
        assert {"high_amount", "unusual_merchant"} <= set(fired)

        result = service(transaction)
        assert result.threshold == 40.0
        assert "ml" in result.layers_used, (
            "the ML layer was absent, so this measured the degraded ensemble "
            "rather than the production one"
        )
        assert result.classification == "fraud", (
            f"the reported transaction still classifies as "
            f"{result.classification!r} at ensemble {result.ensemble_score:.2f} "
            f"(rule {result.rule_score:.2f}, ml {result.ml_score:.2f})"
        )

    def test_a_small_ordinary_purchase_is_untouched(self, service) -> None:
        """The other half of the claim: the fix is not a blunt instrument.

        1,100 EUR at a grocery store crosses `high_amount` — 35 (base) + 0.33
        (magnitude) = 35.33 — and 1,100 sits in the medium amount tier, whose
        threshold is 50 and whose review band starts at 37.5. So a routine
        purchase is still `legitimate`, which is where it belongs: the magnitude
        term is 20 points at 400,000 and 0.33 at 1,100.
        """
        transaction = {
            "amount": 1_100.0,
            "merchant_name": "Supermercado del Barrio",
            "merchant_category": "grocery",
            "timestamp": DAY,
        }
        result = service(transaction)
        assert result.threshold == 50.0
        assert result.rule_score == pytest.approx(35.33, abs=0.01)
        assert result.classification == "legitimate", (
            f"a 1,100 EUR grocery scored {result.ensemble_score:.2f} "
            f"(rule {result.rule_score:.2f}, ml {result.ml_score:.2f})"
        )
        assert math.isfinite(result.ensemble_score)