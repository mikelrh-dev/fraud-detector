"""In-process counters for worker failure modes that no log line can catch.

These exist because a failure can be logged repeatedly and still leave no
evidence in the system. A18 is the motivating case: the SHAP worker used to ack
a message on ``ShapUnavailableError`` with nothing written, no DLQ entry, and
``/health/workers`` reported ``ok`` because its only signal is consumer-group
pending depth — which that path actively drains. A misconfigured worker was
indistinguishable from a healthy one.

A counter is not durable and does not survive a restart. That is the point: it
answers "is this happening right now", which a log file cannot, and it is
cheap enough to check on every scrape.

Deliberately not prometheus_client. The project has no metrics library
installed and adding one is a dependency decision; a plain dict keeps this
honest and testable. If a real exporter is added later, these are the names to
carry over.
"""

from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_counters: defaultdict[str, int] = defaultdict(int)


def increment(name: str, amount: int = 1) -> None:
    """Bump a counter. Cheap enough to call on every failure path."""
    with _lock:
        _counters[name] += amount


def snapshot() -> dict[str, int]:
    """Copy of all counters. Safe to call from an async handler."""
    with _lock:
        return dict(_counters)


def reset() -> None:
    """Clear every counter. For tests only."""
    with _lock:
        _counters.clear()


class _CounterHandle:
    """Binds a counter name so call sites read as ``handle.inc()``."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def inc(self, amount: int = 1) -> None:
        increment(self._name, amount)

    @property
    def name(self) -> str:
        return self._name


#: Messages dropped because SHAP could not run at all (missing library, missing
#: model file, explainer init failure). All three are environmental
#: misconfigurations, not per-transaction errors.
shap_skipped_unavailable = _CounterHandle("shap_skipped_unavailable")

#: A15: transactions scored while the ML layer was absent, so the ensemble
#: redistributed its weight. These scores are systematically different from
#: full-pipeline scores, and nothing downstream could previously tell them
#: apart: `FraudScore.ml_score` is a non-nullable column, so a missing layer was
#: stored as a plain 0.0 and looked like a model that ran and found nothing.
degraded_ml_layer = _CounterHandle("degraded_ml_layer")
