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
KNOWN_VIOLATIONS = {
    "enqueue_for_retry": (
        "TST-01 (audit 2026-09-29): dead with green tests. Nothing calls it."
    ),
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
    """References in src/ beyond the definition itself."""
    hits = 0
    for path in SRC.rglob("*.py"):
        for match in re.finditer(rf"\b{re.escape(name)}\b", _read(path)):
            # A definition line or a decorator does not count as a caller.
            line = _read(path).splitlines()[_read(path)[: match.start()].count("\n")]
            if re.match(rf"\s*(async\s+def|def|class)\s+{re.escape(name)}\b", line):
                continue
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
