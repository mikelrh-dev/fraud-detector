"""A12: the rule engine must not inherit a crash from unvalidated input.

``amount > 1000`` raises TypeError on a string and ``.lower()`` raises
AttributeError on a non-str merchant. Pydantic keeps the HTTP path clean, which
is exactly why nobody noticed: any other consumer — a batch import, a replay
tool, a future queue worker — would have inherited a 500.

A malformed amount is treated as untrusted and fires ``high_amount`` rather than
scoring as clean. Coercing to 0 would be the dangerous direction: anyone who can
make the amount unparseable would dodge every rule.
"""

import math

import pytest

from src.services.rule_engine import RuleEngine


@pytest.fixture
def engine() -> RuleEngine:
    return RuleEngine()


class TestMalformedAmount:
    @pytest.mark.parametrize(
        "bad",
        [
            "abc",
            "",
            [1000],
            {"amount": 1},
            object(),
            True,
            float("nan"),
            float("inf"),
            float("-inf"),
        ],
    )
    def test_does_not_raise(self, engine: RuleEngine, bad: object) -> None:
        score, fired = engine.evaluate({"amount": bad, "merchant_name": "X"})
        assert isinstance(score, float)
        assert math.isfinite(score)

    @pytest.mark.parametrize(
        "bad",
        [
            "abc",
            [1000],
            float("nan"),
            float("inf"),
            float("-inf"),
            True,
        ],
    )
    def test_fires_high_amount_rather_than_scoring_clean(
        self, engine: RuleEngine, bad: object
    ) -> None:
        """Garbage input must not produce a low-risk score.

        D1-3. `float("-inf")` is the case that made this test's coverage look
        complete while the guard it protects was one identifier away from
        broken. `rule_engine.py:101` reads `not math.isfinite(...)`; narrow it to
        `math.isnan(...)` and nothing in the suite objects, because:

            -inf  ->  isnan() is False  ->  the else branch takes it verbatim
                  ->  `-inf > 1000` is False  ->  high_amount does NOT fire
                  ->  the transaction scores 0.0 and fires nothing

        A negative infinity is the most negative number there is, so `not
        amount > 1000` is the one comparison that a non-finite amount can pass
        while a human would call it obviously not-clean. Scored 0.0, it is
        indistinguishable from a real small purchase.

        `+inf` is caught by a narrowing to `isnan` too, and `nan` is caught by
        accident (every `nan > 1000` is already False, but `isfinite` sends it
        to the same untrusted branch as everything else, and `isnan` keeps
        doing that). Only `-inf` slips, which is why it is listed explicitly
        instead of trusting the neighbouring cases to carry it.

        NOT REACHABLE OVER HTTP. `TransactionCreate.amount` declares `gt=0` and
        `allow_inf_nan=False` (src/schemas/transaction.py:17), so pydantic
        rejects both infinities with a 422 before the engine is called. That is
        the whole point of the A12 note at the top of this file: the HTTP path
        is clean, and the engine's own docstring names the consumers that are
        not -- a batch import, a replay tool, a future queue worker. Those pass
        plain dicts, and a -inf that reaches one of them reaches the engine
        directly. The guard is the only thing between that input and a clean
        score.
        """
        _, fired = engine.evaluate({"amount": bad, "merchant_name": "X"})
        assert "high_amount" in fired, (
            "an unparseable amount means we do not know the value; scoring it "
            "clean would let malformed input dodge the rules"
        )

    def test_absent_amount_is_an_incomplete_record_not_an_attack(
        self, engine: RuleEngine
    ) -> None:
        """Absent and malformed are different, and conflating them is harmful.

        A consumer that passes partial dicts is missing data, not attacking.
        Firing high_amount on every such record would flood it with false
        positives, which is a worse failure than the one being fixed.
        """
        score, fired = engine.evaluate({"merchant_name": "X"})
        assert fired == []
        assert score == 0.0

    def test_explicit_none_amount_is_treated_as_absent(
        self, engine: RuleEngine
    ) -> None:
        _, fired = engine.evaluate({"amount": None, "merchant_name": "X"})
        assert fired == []

    def test_bool_is_not_treated_as_a_number(self, engine: RuleEngine) -> None:
        """bool is an int subclass, so True must not read as an amount of 1."""
        _, fired = engine.evaluate({"amount": True, "merchant_name": "X"})
        assert "high_amount" in fired

    def test_valid_amounts_are_unaffected(self, engine: RuleEngine) -> None:
        score, fired = engine.evaluate({"amount": 10.0, "merchant_name": "Cafe"})
        assert score == 0.0
        assert fired == []

    def test_large_valid_amount_still_fires(self, engine: RuleEngine) -> None:
        _, fired = engine.evaluate({"amount": 5000.0, "merchant_name": "X"})
        assert "high_amount" in fired

    def test_int_amount_is_accepted(self, engine: RuleEngine) -> None:
        _, fired = engine.evaluate({"amount": 2000, "merchant_name": "X"})
        assert "high_amount" in fired


class TestMalformedStrings:
    @pytest.mark.parametrize(
        "bad",
        [
            123,
            1.5,
            ["Merchant"],
            {"name": "Merchant"},
            None,
            b"bytes",
            object(),
        ],
    )
    def test_merchant_name_does_not_raise(
        self, engine: RuleEngine, bad: object
    ) -> None:
        score, fired = engine.evaluate({"amount": 10.0, "merchant_name": bad})
        assert isinstance(score, float)

    @pytest.mark.parametrize("bad", [123, ["Merchant"], object()])
    def test_category_does_not_raise(self, engine: RuleEngine, bad: object) -> None:
        engine.evaluate(
            {"amount": 10.0, "merchant_name": "X", "merchant_category": bad},
            {"recent_transactions": 5},
        )

    def test_blacklist_entries_do_not_raise(self, engine: RuleEngine) -> None:
        engine.evaluate(
            {"amount": 10.0, "merchant_name": "X"},
            {"merchant_blacklist": [123, None, "Real Merchant"]},
        )

    def test_missing_keys_are_fine(self, engine: RuleEngine) -> None:
        score, fired = engine.evaluate({})
        assert score == 0.0
        assert fired == []

    def test_string_merchant_still_matches_the_blacklist(
        self, engine: RuleEngine
    ) -> None:
        _, fired = engine.evaluate(
            {"amount": 10.0, "merchant_name": "Bad Shop"},
            {"merchant_blacklist": ["Bad Shop"]},
        )
        assert "unusual_merchant" in fired

    def test_numeric_merchant_matches_a_numeric_blacklist_entry(
        self, engine: RuleEngine
    ) -> None:
        """Coercion must stay consistent between the transaction and the list."""
        _, fired = engine.evaluate(
            {"amount": 10.0, "merchant_name": 123},
            {"merchant_blacklist": [123]},
        )
        assert "unusual_merchant" in fired
