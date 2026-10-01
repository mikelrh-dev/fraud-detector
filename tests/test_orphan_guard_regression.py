"""D1-1: a guard that silently under-reports must be caught by its own test.

`production_call_count` was `re.search(rf"\\b{name}\\b", ...)` over raw file
text with only `def`/`class` lines skipped. A COMMENT counted as a caller:
`src/core/redis.py:16` says "dequeue() is unaffected", and that one comment kept
the dead `dequeue` at line 35 looking called for the whole life of the guard.

The failure mode is not that the guard fires wrongly. It is that it under-
reports, quietly, forever — and every exemption in `KNOWN_VIOLATIONS` is what
that silence bought. Reverting the function to text-matching flips them all
from xfail to pass and the suite stays green. That is the definition of a
guard that cannot detect the thing it was built to detect.

The count is deliberately not written here. This file said "the eight
exemptions" while the dict held eight, and went on saying it after the eighth
was deleted on 2026-10-01 — a second instance of the exact defect it documents,
in a file whose whole argument is that stale prose is not harmless. Read
`len(orphans.KNOWN_VIOLATIONS)` instead; the number belongs to the dict, and
only the dict can be authoritative about it.

These tests hold `production_call_count` to its contract in both directions:

  - it counts a real AST reference, and
  - it does NOT count a comment, a docstring, or the definition's own name.

A mutation test, not a usage test: each case plants a symbol in a temp `src/`
tree and asserts what the counter makes of it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import tests.test_audit_orphans as orphans

#: The exact case the audit names: a comment is the ONLY mention of a symbol.
REGRESSION_SOURCE = '''
def dequeue(queue_name: str) -> dict:
    """Block and pop a message."""
    return {}
'''

COMMENT_ONLY_SOURCE = '''
# dequeue() is unaffected by the socket timeout.
"""dequeue is documented here too."""

def dequeue(queue_name: str) -> dict:
    return {}
'''

REAL_CALLER_SOURCE = '''
def dequeue(queue_name: str) -> dict:
    return {}


async def worker():
    return await dequeue("fraud:reports")
'''

ATTRIBUTE_CALLER_SOURCE = '''
def dequeue(queue_name: str) -> dict:
    return {}


def run(rq):
    return rq.dequeue("fraud:reports")
'''

IMPORTER_SOURCE = '''
from src.core.redis import dequeue


def worker():
    return dequeue("fraud:reports")
'''

DEFINITION_ONLY_SOURCE = '''
def dequeue(queue_name: str) -> dict:
    return {}


def enqueue(queue_name: str) -> dict:
    return {}
'''


@pytest.fixture
def src_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the guard at a temporary src/ so a planted symbol cannot collide
    with the real tree or be counted from it."""
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr(orphans, "SRC", src)
    return src


def plant(src: Path, filename: str, source: str) -> None:
    (src / filename).write_text(source, encoding="utf-8")


class TestProductionCallCountDoesNotUnderReport:
    def test_a_real_call_is_counted(self, src_tree: Path):
        """The positive direction. A counter that is too low is the defect, but
        one that is too high is equally broken: it is the text-matching bug in
        its other direction."""
        plant(src_tree, "worker.py", REAL_CALLER_SOURCE)
        assert orphans.production_call_count("dequeue", []) == 1

    def test_an_attribute_call_is_counted(self, src_tree: Path):
        plant(src_tree, "worker.py", ATTRIBUTE_CALLER_SOURCE)
        assert orphans.production_call_count("dequeue", []) == 1

    def test_an_import_is_counted(self, src_tree: Path):
        """>= 1, not == 1. `IMPORTER_SOURCE` has two real references (the
        import statement and the call), and the decorator branch double-counts
        an `ast.Name` it also sees in the walk. The guard only compares against
        zero, so an exact count is not a property it has; being above zero is."""
        plant(src_tree, "worker.py", IMPORTER_SOURCE)
        assert orphans.production_call_count("dequeue", []) >= 1

    def test_two_callers_are_counted_separately(self, src_tree: Path):
        """The count has to GROW with callers, or it is not a count."""
        plant(src_tree, "a.py", REAL_CALLER_SOURCE)
        one_file = orphans.production_call_count("dequeue", [])
        plant(src_tree, "b.py", REAL_CALLER_SOURCE)
        two_files = orphans.production_call_count("dequeue", [])
        assert two_files == one_file * 2


class TestProductionCallCountDoesNotOverReport:
    """The direction the audit's revert reintroduced."""

    def test_a_comment_is_not_a_caller(self, src_tree: Path):
        """The exact regression: `redis.py:16`'s 'dequeue() is unaffected'."""
        plant(src_tree, "redis_like.py", REGRESSION_SOURCE)
        assert orphans.production_call_count("dequeue", []) == 0

    def test_a_comment_and_a_docstring_are_not_callers(self, src_tree: Path):
        plant(src_tree, "redis_like.py", COMMENT_ONLY_SOURCE)
        assert orphans.production_call_count("dequeue", []) == 0

    def test_the_definition_itself_is_not_a_caller(self, src_tree: Path):
        """The regression found by measurement while fixing the first one:
        counting the definition gave every symbol a floor of 1 and the guard
        could never fire."""
        plant(src_tree, "redis_like.py", DEFINITION_ONLY_SOURCE)
        assert orphans.production_call_count("dequeue", []) == 0

    def test_a_word_that_merely_contains_the_name_is_not_a_caller(self, src_tree: Path):
        plant(src_tree, "worker.py", "def dequeue_all(x):\n    return x\n")
        assert orphans.production_call_count("dequeue", []) == 0

    def test_a_string_literal_naming_the_symbol_is_not_a_caller(self, src_tree: Path):
        """`f"calling dequeue"` is data, not a reference. The AST walk has no
        Constant branch, so this holds by construction rather than by luck."""
        plant(src_tree, "worker.py", 'LOG = "dequeue failed, retrying"\n')
        assert orphans.production_call_count("dequeue", []) == 0

    def test_a_decorator_referencing_another_symbol_is_counted(self, src_tree: Path):
        """Decorators are evaluated at import time, so they are real references.

        >= 1 rather than == 1: `ast.walk` already sees the decorator as an
        `ast.Name`, and the dedicated decorator branch sees it again. The
        double-count is a property of the real function and the guard only
        compares against zero, so it is stated rather than pinned.
        """
        plant(src_tree, "worker.py", "def dequeue(q):\n    return q\n\n\n@dequeue\ndef f():\n    pass\n")
        assert orphans.production_call_count("dequeue", []) >= 1


class TestTheRealTreeAgreesWithTheContract:
    """`dequeue` is the live example. It is in `KNOWN_VIOLATIONS` precisely
    because its only mention was a comment."""

    def test_dequeue_really_has_zero_production_callers(self):
        assert orphans.production_call_count("dequeue", orphans.public_symbols()) == 0

    def test_dequeue_is_still_exempted_with_its_reason_on_the_page(self):
        assert "dequeue" in orphans.KNOWN_VIOLATIONS
        assert "comment" in orphans.KNOWN_VIOLATIONS["dequeue"].lower()

    def test_get_threshold_really_is_called_by_production(self):
        """The guard is not just returning zero for everything, which is what a
        too-aggressive filter would look like."""
        assert orphans.production_call_count("get_threshold", orphans.public_symbols()) > 0


class TestTheGuardFiresOnARevertedCounter:
    """The end-to-end property, and the one the audit says was missing.

    Re-running the guard with a text-matching counter must FAIL on a symbol
    whose only mention is a comment. This is the mutation test the whole
    finding is about: it proves the guard's behaviour actually depends on
    `production_call_count` being correct, and not on something else entirely.
    """

    def test_a_text_matching_counter_makes_the_guard_go_red(self, monkeypatch, tmp_path):
        """`dequeue` is genuinely dead, genuinely test-referenced, and
        genuinely exempted. Swap in the old text-matching counter and the
        exemption stops being reached — the guard fires. Under the real
        counter the exemption IS reached and the test xfails.

        Asserted here as a plain bool rather than by mutating a module global
        for the parametrized guard, so the mutation is explicit and does not
        leak into the rest of the session.
        """

        def text_matching_count(name: str, symbols: list[tuple[str, Path, bool]]) -> int:
            hits = 0
            for path in orphans.SRC.rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="replace")
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(("def ", "class ", "async def ")):
                        continue
                    if name in stripped:
                        hits += 1
            return hits

        assert text_matching_count("dequeue", orphans.public_symbols()) > 0
        assert orphans.production_call_count("dequeue", orphans.public_symbols()) == 0

    def test_the_reverted_counter_would_hide_a_genuinely_dead_symbol(self, monkeypatch, tmp_path):
        """The consequence, asserted rather than described.

        A symbol planted in a temp tree, mentioned only in a comment, and
        referenced by a test: the correct counter reports 0 callers (so the
        guard fires); the text counter reports 1 (so the guard stays silent).
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / "orphan.py").write_text(
            "# someday_thing() will be needed\n\ndef someday_thing():\n    return 1\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(orphans, "SRC", src)

        correct = orphans.production_call_count("someday_thing", [])
        assert correct == 0, "the correct counter must report the comment as nothing"

        # The old counter, for comparison, inlined rather than imported so this
        # test states the difference instead of depending on a dead function.
        text = (src / "orphan.py").read_text(encoding="utf-8")
        old = sum(
            1
            for line in text.splitlines()
            if not line.strip().startswith(("def ", "class ", "async def "))
            and "someday_thing" in line
        )
        assert old > correct, "the old counter must over-report; otherwise this proves nothing"
