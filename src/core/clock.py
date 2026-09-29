"""Injectable clock — the seam that makes time-dependent logic testable.

Why this exists
---------------
Two tests in ``tests/test_rule_engine.py`` failed every night and passed every
other hour. The cause was not the rule engine: it never reads the wall clock
at all. It reads the hour from the *transaction's own* ``timestamp``. The
tests built that timestamp with ``datetime.now()`` and then asserted an exact
score, so the assertion was a statement about what time of day CI happened to
run. Measured across all 24 hours, ``test_high_velocity_rule_fires`` and
``test_high_amount_and_velocity`` fail in exactly the six hours 00:00-05:59
UTC, because ``unusual_hours`` (+10) legitimately fires then and the scores
come out 35 and 70 instead of 25 and 60.

The fix is not to relax those assertions. The engine is right: a transaction
at 03:00 UTC *is* an unusual-hour transaction. The fix is to stop asking the
wall clock what time it is when the answer must not vary.

``VelocityStore`` is the one component in the scoring path that did read the
clock directly, and it now takes one of these. That is a real change, not a
formality: velocity counts are computed from elapsed time, so any test that
exercises a window boundary is at the mercy of when it runs.

Usage::

    from src.core.clock import FrozenClock, SystemClock

    clock = FrozenClock(datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc))
    store = VelocityStore(clock=clock)

    # or, for a fixture that wants a specific hour of the day:
    FrozenClock.at_hour(3)
"""

from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """A source of the current time.

    Every implementation must return a timezone-aware UTC datetime. A naive
    datetime is a bug waiting to happen: it is interpreted in the host's local
    zone, so the same code passes in Madrid and fails in Auckland.
    """

    def now_utc(self) -> datetime:  # pragma: no cover - protocol definition
        ...


class SystemClock:
    """The real wall clock. The default everywhere in production."""

    __slots__ = ()

    def now_utc(self) -> datetime:
        return datetime.now(tz=timezone.utc)

    def __repr__(self) -> str:
        return "SystemClock()"


class FrozenClock:
    """A clock pinned to one instant, for tests.

    ``FrozenClock`` is the whole point of the module: a test that cares about
    an hour-of-day rule asks for that hour explicitly instead of inheriting
    whatever hour the machine happens to be in. ``advance()`` exists so a test
    can still exercise elapsed-time logic (velocity windows, token expiry)
    without sleeping.
    """

    __slots__ = ("_now",)

    def __init__(self, now: datetime) -> None:
        self._now = self._coerce(now)

    @staticmethod
    def _coerce(now: datetime) -> datetime:
        if now.tzinfo is None:
            raise ValueError(
                f"FrozenClock requires a timezone-aware datetime, got {now!r}. "
                f"A naive datetime is read in the host's local zone, which is "
                f"exactly the class of bug this class exists to remove."
            )
        return now.astimezone(timezone.utc)

    @classmethod
    def at_hour(cls, hour: int, *, day: int = 15, month: int = 1, year: int = 2024) -> "FrozenClock":
        """A clock pinned to ``hour``:00:00 UTC on a fixed date.

        A no-argument date is deliberate. The point is to control the *hour*;
        pinning the date too means a second of drift cannot move the test into
        a neighbouring hour and make it flaky in the other direction.
        """
        if not 0 <= hour <= 23:
            raise ValueError(f"hour must be 0-23, got {hour}")
        return cls(datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc))

    def now_utc(self) -> datetime:
        return self._now

    def advance(self, **timedelta_kwargs: float) -> "FrozenClock":
        """Move this clock forward, in place. Returns self for chaining."""
        self._now = self._now + timedelta(**timedelta_kwargs)
        return self

    def __repr__(self) -> str:
        return f"FrozenClock({self._now.isoformat()})"
