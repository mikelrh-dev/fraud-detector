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
#: NOT EMPTY. It holds seven live exemptions. An earlier revision of this
#: comment said "EMPTY" three times while this dict carried those entries,
#: which is a dangerous kind of wrong: a maintainer who believed it would delete
#: the dict, turning seven xfails into seven hard failures, and a maintainer who
#: half-believed it could not tell which entries were open. The count below is
#: now enforced by `test_the_exemption_count_on_the_page_is_accurate`.
#:
#: RESOLVED, and recorded here because a ledger that quietly shrinks is not a
#: ledger. `MonitoringService` (audit finding D7-4) was the eighth entry until
#: 2026-10-01. Its exemption said: "a capability wired nowhere, not dead code —
#: decide, wire it or delete it." Decision A was taken in
#: `docs/plans/2026-10-01-monitoring-desenmascarar.md`: `MonitoringService`,
#: `tests/test_monitoring.py` and the unwired `monitoring_service` parameter on
#: `ScoringService.compute_scores` were all deleted, so `DataDriftService` is
#: the only drift service. The symbol is gone, so the exemption is gone with it —
#: which is exactly the rule `test_every_exemption_is_still_a_live_violation`
#: below enforces in the other direction, reached by deletion rather than by
#: wiring. The entry was not dropped to make a count pass; it had no subject.
#:
#: The seven, by what they are:
#:   - `FrozenClock` — a test utility that lives in src/ and should move.
#:   - `enqueue` / `dequeue` — the unused LLM-worker wrapper pair; the worker
#:     calls redis directly. Both were hidden because a COMMENT mentioning
#:     `dequeue` was being counted as a caller.
#:   - `migrate_legacy_list` — a stream migration path never wired up.
#:   - `alerts_per_day` / `optimal_threshold` / `breakeven_cost_ratio` — live
#:     code in cost_model.py that no request path calls. NOT dead: see the
#:     entries in the dict for who calls them.
#:
#: `test_every_exemption_is_still_a_live_violation` keeps the set honest in the
#: other direction: wire one of these up and the entry must be deleted, so an
#: exemption can never outlive the problem it excuses.
#:
#: WHAT THE GUARD DOES NOT COVER. Stated because a guard whose own comment
#: overstates it is the defect class this repository keeps auditing.
#:   - `src/` only. A caller in `scripts/`, `alembic/` or `notebooks/` is
#:     invisible, and no CI gate reads those either. This is the limitation
#:     that matters for the three cost_model entries: their only callers are
#:     in `scripts/evaluate_cost.py`, so this guard reports them as uncalled
#:     whether or not they are used. Read those three as "unreachable from an
#:     HTTP request", which is what was actually measured, and never as
#:     "delete me" — they generate the cost table the README publishes, and
#:     that table was live before this comment said otherwise.
#:   - It fires only for a symbol that is BOTH uncalled and test-referenced.
#:     Dead code no test touches cannot be seen by it all.
#:   - Two skip paths bypass this dict entirely and are deliberate:
#:     `is_route` (FastAPI invokes handlers through the router, never by name)
#:     and `DELIBERATE_MAINTENANCE_API` (one entry, `reset`, with its reason).
#:     So "seven exemptions" is not "seven ways a test can be suppressed" —
#:     those two are skips, not exemptions, and they are counted separately.
#:
#: On strictness, because the earlier version of this comment claimed it: the
#: exemption used the imperative `pytest.xfail(reason)`, which has NO `strict`
#: parameter (`pytest.xfail(reason: str = "")` is the entire signature) and so
#: never turned a resolved exemption into an XPASS failure. The enforcement that
#: actually happened ran the other way -- taking a name OUT of this dict turns a
#: live dead symbol red, which is how TST-01 was caught. That is why the
#: staleness test above is written as an explicit assertion rather than relied on
#: from `xfail` semantics.
KNOWN_VIOLATIONS = {
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
    "alerts_per_day": (
        "AUDIT-2026-09-29: NOT dead, and this entry previously said it was — "
        "a label a maintainer could act on by deleting live code. It is "
        "called from scripts/evaluate_cost.py, which imports it from "
        "src/services/cost_model.py and prints the per-day figure in the cost "
        "sensitivity table the README publishes. This guard only parses src/, "
        "so it cannot see that caller: what is actually established is that no "
        "HTTP request reaches it."
    ),
    "optimal_threshold": (
        "AUDIT-2026-09-29: NOT dead — same correction as alerts_per_day. "
        "scripts/evaluate_cost.py calls it to sweep the cost-optimal flat "
        "threshold across C_fn/C_fp, and its output is the sweep the README "
        "quotes ('moves from 75.00 down to 0.20'). Unreachable from a "
        "request; live as a reporting tool."
    ),
    "breakeven_cost_ratio": (
        "AUDIT-2026-09-29: NOT dead — same correction as alerts_per_day. "
        "scripts/evaluate_cost.py calls it and prints the ratio (99.0) that "
        "the README quotes. Unreachable from a request; live as a reporting "
        "tool."
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


def _known_violations_comment() -> str:
    """The comment block immediately above KNOWN_VIOLATIONS."""
    source = _read(Path(__file__))
    start = source.index("#: Violations found by this test")
    end = source.index("KNOWN_VIOLATIONS = {")
    return source[start:end]


def test_the_exemption_count_on_the_page_is_accurate():
    """The comment states a number. This makes the number true.

    This comment previously said "EMPTY" three times while the dict held eight
    entries, and nothing failed, because prose is not executable. The count is
    pinned here so that adding or removing an entry forces a deliberate edit of
    the sentence describing it, instead of the two drifting apart in silence.

    It is seven as of 2026-10-01: `MonitoringService` was deleted (decision A
    in `docs/plans/2026-10-01-monitoring-desenmascarar.md`), which resolved
    its exemption. The RESOLVED paragraph in the comment block is what records
    that; this assertion only refuses to let the number drift away from the
    dict again.
    """
    assert len(KNOWN_VIOLATIONS) == 7, (
        f"KNOWN_VIOLATIONS holds {len(KNOWN_VIOLATIONS)} entries, not 7. Its "
        f"comment states the count and names the entries — update both, and say "
        f"what the new entry is, so the page stays true."
    )
    assert "seven" in _known_violations_comment().lower()


def test_the_exemption_comment_does_not_claim_the_dict_is_empty():
    """A narrow literal guard on a specific, already-observed regression.

    Weak on purpose and weak on record: this asserts a string, not a behaviour.
    It is here because this exact false claim shipped three times in this
    comment, and a reader who believes it deletes the dict and turns seven
    xfails into seven failures. The substantive guards are the two tests above.
    """
    comment = _known_violations_comment().lower()
    assert "not empty" in comment, (
        "the KNOWN_VIOLATIONS comment must open by denying it is empty, since "
        "it is not and three revisions of this file claimed otherwise"
    )
    for false_claim in ("#: empty.", "dict is empty", "is currently empty"):
        assert false_claim not in comment, (
            f"the KNOWN_VIOLATIONS comment still claims {false_claim!r}, which "
            f"is false — it holds {len(KNOWN_VIOLATIONS)} live exemptions"
        )


@pytest.mark.parametrize("name", sorted(KNOWN_VIOLATIONS))
def test_every_exemption_is_still_a_live_violation(name: str):
    """An exemption for a symbol that now HAS a caller is stale.

    This is the forward guard for the confusion the `KNOWN_VIOLATIONS` comment
    used to cause: a reader who believed the dict was empty would delete it, and
    a reader who could not tell which entries were live would trust a resolved
    finding. Both errors are prevented by the comment now counting the entries
    and naming them, and this test is what keeps that count honest — wiring one
    of these seven symbols up has to remove its exemption, not leave it behind
    reading as an open finding.
    """
    assert production_call_count(name, public_symbols()) == 0, (
        f"{name} is in KNOWN_VIOLATIONS but now has a production caller. "
        f"The exemption is stale — remove it and the guard will police the "
        f"symbol for real from now on."
    )


@pytest.mark.parametrize("name", sorted(KNOWN_VIOLATIONS))
def test_every_exemption_carries_its_reason(name: str):
    """An exemption without a reason is indistinguishable from a suppression.

    The whole reason this dict is allowed to exist at all is that each entry is
    challengeable: a reader has to be able to disagree with it. An empty string
    is a suppression wearing the costume of a finding.
    """
    reason = KNOWN_VIOLATIONS[name]
    assert reason.strip(), f"{name} is exempt with no reason recorded"
    assert "AUDIT-" in reason, (
        f"{name}'s reason does not name the audit finding that produced it, so "
        f"there is nothing to look up"
    )


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
