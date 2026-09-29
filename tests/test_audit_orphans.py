"""No public symbol may be exercised only by tests.

`classificationPillClass` kept nine green tests while production called it zero
times. The suite was not lying about anything it asserted — it was protecting
code that no request ever reached. A test that guards a function nothing calls is
not coverage; it is a monument.

This asserts the property across the whole backend, so the class cannot regrow
without the build going red.

Two known false-positive classes are handled explicitly, because a check that
cries wolf gets disabled:

- Route handlers are invoked by FastAPI through the router, never by name.
- Deliberate maintainer-only surfaces (counter resets) are reachable by hand by
  design, and are listed with that reason attached so the exemption is visible.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
TESTS = REPO / "tests"

#: Public surface that exists to be called by a human operator, not by a request.
#: Each entry carries its reason so a reader can challenge the exemption.
DELIBERATE_MAINTENANCE_API = {
    "reset": "counters.py maintenance primitive; never automatic, by design",
}

#: Violations found by this test, recorded rather than deleted. Each names the
#: audit finding that produced it.
#:
#: EMPTY. Both entries the 2026-09-29 audit added are resolved:
#:
#: - `list_transactions` (TST-02) — deleted, with its service-only test. The
#:   endpoint's `list_transactions_endpoint` was always the real implementation.
#: - `enqueue_for_retry` (TST-01) — deleted, with its tests. The LLM worker's
#:   `_recovery_loop` already owns requeue/PEL/DLQ handling.
#:
#: The dict is kept rather than removed so the next real violation has a named
#: place to be recorded, and so the absence of entries is a fact on the page
#: rather than an absence nobody has to go looking for.
#:
#: On strictness, because the earlier version of this comment claimed it: the
#: exemption used the imperative `pytest.xfail(reason)`, which has NO `strict`
#: parameter (`pytest.xfail(reason: str = "")` is the entire signature) and so
#: never turned a resolved exemption into an XPASS failure. The enforcement
#: that actually happened ran the other way -- taking a name OUT of this dict
#: turns a live dead symbol red, which is how TST-01 was caught.
#:
#: On coverage, because the previous revision of this comment ALSO claimed it
#: and was wrong twice over. With this dict empty it is true that no
#: `KNOWN_VIOLATIONS` entry can exempt anything. It is NOT true that nothing is
#: exempt, and this file must not imply that: two skip paths remain live and
#: deliberate -- `is_route` (FastAPI invokes handlers through the router, never
#: by name) and `DELIBERATE_MAINTENANCE_API` (one entry, `reset`, with its
#: reason on the page). Both are stated rather than hidden because a guard whose
#: own comment overstates it is the defect class this repository keeps auditing.
#:
#: Two further limits, so the property is not read as stronger than it is:
#:   - It covers `src/` only. A caller in `scripts/`, `alembic/` or `notebooks/`
#:     is invisible, and no CI gate reads those either.
#:   - It fires only for a symbol that is BOTH uncalled and test-referenced.
#:     Dead code no test touches cannot be seen by it at all.
#: Violations found by this test, recorded rather than deleted, so the gate stays
#: green and each one is visible on the page. All eight surfaced at once when
#: `production_call_count` was corrected to parse instead of text-match: a comment
#: had been counting as a caller, which hid every symbol whose only mention was
#: prose. See `tests/test_audit_orphans.py` module docstring.
KNOWN_VIOLATIONS = {
    "MonitoringService": (
        "AUDIT-2026-09-29: NOT dead code — a capability that is wired nowhere. "
        "scoring_service.compute_scores takes `monitoring_service` and calls "
        "_track_model_run only when it is not None; nothing constructs one, so "
        "no model run is ever recorded in ml_model_runs. Decide: wire it, or "
        "delete it and say the ML4 model-run tracking is not in use."
    ),
    "FrozenClock": (
        "AUDIT-2026-09-29: a test utility living in src/. It belongs in tests/ "
        "and should move there, not be deleted."
    ),
    "enqueue": (
        "AUDIT-2026-09-29: the LLM worker requeues via redis_client.xadd "
        "directly (llm_worker.py:275); this was the unused wrapper for it."
    ),
    "dequeue": (
        "AUDIT-2026-09-29: same module as enqueue; no caller. Its only mention "
        "anywhere was a comment, which is what hid it until the count was fixed."
    ),
    "migrate_legacy_list": (
        "AUDIT-2026-09-29: a stream migration path that was built and never "
        "wired to a caller."
    ),
    "alerts_per_day": "AUDIT-2026-09-29: dead in cost_model.py; see the module's other three.",
    "optimal_threshold": "AUDIT-2026-09-29: dead in cost_model.py.",
    "breakeven_cost_ratio": "AUDIT-2026-09-29: dead in cost_model.py.",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _is_route_handler(node: ast.AST) -> bool:
    decorators = getattr(node, "decorator_list", [])
    for dec in decorators:
        target = dec.func if isinstance(dec, ast.Call) else dec
        name = getattr(target, "attr", "") or getattr(target, "id", "")
        if name in {"get", "post", "put", "patch", "delete", "websocket", "api_route"}:
            return True
    return False


def public_symbols() -> list[tuple[str, Path, bool]]:
    """(name, defining file, is_route_handler) for every public definition."""
    found = []
    for path in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(_read(path))
        except SyntaxError:  # pragma: no cover - a parse failure fails the gates
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if node.name.startswith("_"):
                continue
            found.append((node.name, path, _is_route_handler(node)))
    return found


def _corpus(paths: list[Path]) -> str:
    return "\n".join(_read(p) for p in paths)


def production_call_count(name: str, symbols: list[tuple[str, Path, bool]]) -> int:
    """Real references to `name` in src/, parsed — not text-matched.

    The previous version counted `\\bname\\b` occurrences over raw file text and
    skipped only `def`/`class` lines, so a COMMENT counted as a caller:
    `src/core/redis.py:16` says "dequeue() is unaffected" and that single
    comment kept the dead `dequeue` at line 35 looking called. The guard
    silently under-reports, which is the failure mode a team cannot see and
    therefore never disables.

    Now the module is parsed and only real name usages count: `ast.Name`,
    `ast.Attribute`, imports and decorator references. Comments and docstrings
    are not AST, so they cannot reach the count.

    The definition itself is deliberately NOT counted. Counting it would give
    every symbol a floor of 1 and the guard could never fire — which is exactly
    the regression an earlier draft of this function introduced, caught by
    measuring `dequeue` at 1 while it is dead.
    """
    hits = 0
    for path in SRC.rglob("*.py"):
        try:
            tree = ast.parse(_read(path))
        except SyntaxError:  # pragma: no cover - a parse failure fails the gates
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == name:
                hits += 1
            elif isinstance(node, ast.Attribute) and node.attr == name:
                hits += 1
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Decorators reference other symbols; the body of this one is a
                # usage; its own `def` line is not.
                for dec in getattr(node, "decorator_list", []):
                    target = dec.func if isinstance(dec, ast.Call) else dec
                    if getattr(target, "id", None) == name or getattr(target, "attr", None) == name:
                        hits += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if (alias.asname or alias.name).split(".")[0] == name:
                        hits += 1
    return hits


@pytest.mark.parametrize(
    ("name", "path", "is_route"),
    public_symbols(),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_audit_no_symbol_is_exercised_only_by_tests(name: str, path: Path, is_route: bool):
    """A public symbol with zero production callers is dead code with a green suite."""
    if is_route:
        pytest.skip("route handler: FastAPI invokes it through the router")
    if name in DELIBERATE_MAINTENANCE_API:
        pytest.skip(DELIBERATE_MAINTENANCE_API[name])

    if production_call_count(name, public_symbols()) == 0:
        tested = re.search(rf"\b{re.escape(name)}\b", _corpus(list(TESTS.rglob("*.py"))))
        if tested:
            if name in KNOWN_VIOLATIONS:
                pytest.xfail(KNOWN_VIOLATIONS[name])
            pytest.fail(
                f"{name} ({path.relative_to(REPO)}) has zero production callers but is "
                f"asserted by tests. Those tests protect a path no request reaches. "
                f"Either call it or delete it and its tests."
            )
