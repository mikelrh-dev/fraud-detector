"""An offset-aware timestamp must be read as the UTC instant it denotes.

`rule_engine.evaluate` and `FeatureEngine.transform` both parsed the
transaction's `timestamp` and read `dt.hour` straight off the result. For a
timestamp carrying a non-UTC offset that is the LOCAL hour, not the UTC hour the
rules are written against.

The concrete miss: a transaction at `2024-01-15T23:00:00-05:00` is 04:00 UTC.
The rules saw 23, `unusual_hours` (00:00-05:59) did not fire, and the
`hour_of_day` feature recorded 23.0 instead of 4.0. The transaction was scored
as a quiet late-evening purchase when it was a small-hours one.

## NOT REACHABLE FROM THE HTTP API TODAY — stated so the severity is honest

`transactions.py:244-251` builds the scoring input with
`now = datetime.now(tz=timezone.utc)` and `"timestamp": now.isoformat()`, so
every request-scored transaction carries `+00:00` and the offset is always zero.
No client can send its own timestamp: `TransactionCreate` does not expose the
field, and the IDOR fix at `:176-178` already ignores client identity for the
same reason.

The reachable consumers are the ones the rule engine's own docstring names at
`:27` and `:78-79` — a **batch import**, a **replay tool**, a **future queue
worker** — plus the training pipeline, which reads `merchant_category` and
`timestamp` out of a CSV written by whichever producer supplied it. Those paths
carry whatever offset the source system had, which is the whole problem: a
`-05:00` feed and a `+00:00` feed describing the same instant were scored
differently, and the difference depended on the producer's locale rather than on
anything about the transaction.

So this is a latent defect with a narrow blast radius today and a wide one the
moment a second producer exists. It is fixed now because the fix is two lines
per site and the alternative is a rule whose meaning depends on who called it.

## THE DECISION: naive timestamps are treated as already-UTC

A timestamp with no offset (`2024-01-15T03:00:00`) carries no information about
which zone it belongs to. Two options:

- `dt.astimezone(timezone.utc)` on a naive datetime makes Python assume the
  process's LOCAL timezone. That converts "unknown" into "whatever the host
  happens to be set to", so the same corpus would score differently on a
  developer laptop in Madrid and on a container in UTC. Rejected: it makes the
  score depend on the environment.
- Treat naive as UTC, which is what the code already did by accident and what
  every existing test fixture assumes.

Chosen: naive is UTC. An offset-aware timestamp is converted; a naive one is
used as-is. This never invents a zone.
"""

from __future__ import annotations

import pytest

from src.services.feature_engine import FEATURE_NAMES, FeatureEngine
from src.services.rule_engine import RuleEngine

#: 23:00 at -05:00 is 04:00 UTC the next day. Both engines must see hour 4.
OFFSET_NIGHT = "2024-01-15T23:00:00-05:00"

#: 03:00 at +05:00 is 22:00 UTC the previous day — the other direction, so a
#: fix that only handles negative offsets is caught.
OFFSET_EVENING = "2024-01-15T03:00:00+05:00"

#: The same instant written three ways. All three must score identically.
SAME_INSTANT_UTC = "2024-01-16T04:00:00+00:00"
SAME_INSTANT_NEG = "2024-01-15T23:00:00-05:00"
SAME_INSTANT_POS = "2024-01-16T09:00:00+05:00"


def _evaluate(timestamp: str) -> tuple[float, list[str]]:
    engine = RuleEngine()
    return engine.evaluate(
        {"amount": 100, "timestamp": timestamp}, {}
    )


def _hour_feature(timestamp: str) -> float:
    engine = FeatureEngine()
    vector = engine.transform({"amount": 100, "timestamp": timestamp}, {})
    return float(vector[FEATURE_NAMES.index("hour_of_day")])


class TestRuleEngineReadsUtcHour:
    def test_an_offset_timestamp_can_still_fire_unusual_hours(self):
        """The miss. 23:00-05:00 is 04:00 UTC, which is night."""
        score, fired = _evaluate(OFFSET_NIGHT)

        assert "unusual_hours" in fired, (
            "a transaction at 23:00-05:00 is 04:00 UTC; unusual_hours covers "
            "00:00-05:59 and must fire on the UTC hour, not the local one"
        )
        assert score == 10.0

    def test_a_positive_offset_does_not_invent_a_night(self):
        """03:00+05:00 is 22:00 UTC — the evening, not the small hours."""
        _, fired = _evaluate(OFFSET_EVENING)

        assert "unusual_hours" not in fired, (
            "03:00+05:00 is 22:00 UTC; reading the local hour charged a "
            "night-time rule to an ordinary evening transaction"
        )

    @pytest.mark.parametrize(
        "timestamp", [SAME_INSTANT_UTC, SAME_INSTANT_NEG, SAME_INSTANT_POS]
    )
    def test_the_same_instant_scores_the_same_whatever_the_offset(self, timestamp):
        """The property the other two are instances of, stated directly.

        Three spellings of one instant must not produce three scores. Before the
        fix these returned 10, 0 and 0 for the same transaction.
        """
        assert _evaluate(timestamp) == _evaluate(SAME_INSTANT_UTC)


class TestFeatureEngineReadsUtcHour:
    def test_hour_of_day_is_the_utc_hour(self):
        assert _hour_feature(OFFSET_NIGHT) == 4.0

    def test_hour_of_day_is_not_the_local_hour(self):
        """The negative assertion, because 4.0 could arrive by accident."""
        assert _hour_feature(OFFSET_NIGHT) != 23.0

    def test_a_positive_offset_is_converted_too(self):
        assert _hour_feature(OFFSET_EVENING) == 22.0

    def test_weekday_uses_the_utc_day_not_the_local_one(self):
        """Weekday has the same bug and the same fix.

        2024-01-15 is a Monday and 2024-01-16 a Tuesday, so the instant above
        is Monday 23:00 in New York and Tuesday 04:00 in UTC. `is_weekend` must
        be derived from the UTC day or a Sunday-evening transaction is labelled
        a weekend one — or the reverse, which is worse: a Saturday purchase
        scored as a weekday.
        """
        engine = FeatureEngine()
        saturday_evening = engine.transform(
            {"amount": 100, "timestamp": "2024-01-20T23:00:00-05:00"}, {}
        )
        # 2024-01-20 23:00-05:00 == 2024-01-21 04:00 UTC, a SUNDAY either way.
        # Chosen so the local day is Saturday and the UTC day is Sunday, which
        # is the case where the two disagree about `is_weekend`.
        assert float(saturday_evening[FEATURE_NAMES.index("is_weekend")]) == 1.0


class TestNaiveTimestampsAreTreatedAsUtc:
    """The decision, pinned so it cannot drift into local time."""

    def test_a_naive_timestamp_is_not_shifted(self):
        assert _hour_feature("2024-01-15T03:00:00") == 3.0

    def test_a_naive_timestamp_matches_its_utc_spelling(self):
        assert _evaluate("2024-01-15T03:00:00") == _evaluate("2024-01-15T03:00:00+00:00")

    def test_a_naive_evening_is_not_charged_a_night_rule(self):
        _, fired = _evaluate("2024-01-15T22:00:00")

        assert "unusual_hours" not in fired


class TestUnparseableTimestampsKeepTheirDefaults:
    """The fix must not disturb the existing failure path."""

    def test_a_garbage_timestamp_falls_back_to_noon(self):
        assert _hour_feature("not-a-timestamp") == 12.0

    def test_a_missing_timestamp_keeps_its_existing_default_of_zero(self):
        """ABSENT is 0.0, GARBAGE is 12.0. That asymmetry is pre-existing.

        The `except` branch says "use neutral defaults (not midnight)" and
        yields hour 12, but an absent or empty timestamp skips the `try` block
        entirely and keeps the initial `hour = 0`. So a missing timestamp is
        scored as midnight.

        Recorded, not fixed. Changing 0 to 12 here would move `hour_of_day` for
        every transaction that arrives without a timestamp, which is a
        model-visible input-distribution change and emphatically not part of a
        timezone fix. It also cuts the opposite way from the parse fallback:
        `unusual_hours` does NOT fire for a missing timestamp, because the rule
        sits behind the same falsy guard, so the feature says midnight while the
        rule says nothing.

        Worth an audit item of its own. Pinned here so that if it is ever
        changed, the change is deliberate and visible.
        """
        assert _hour_feature("") == 0.0
        assert _hour_feature("not-a-timestamp") == 12.0

    def test_a_missing_timestamp_fires_no_hour_rule(self):
        _, fired = _evaluate("")

        assert "unusual_hours" not in fired
