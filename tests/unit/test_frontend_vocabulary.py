"""D3: the frontend's category list cannot drift from the backend's.

The API validates `merchant_category` against `KNOWN_MERCHANT_CATEGORIES` and
answers 422 for anything else, so the frontend selector has to offer exactly
that set. `scripts/generate_frontend_vocabulary.py` writes it into
`frontend/src/lib/merchant-vocabulary.generated.ts`.

That closes the drift window from one side only. A generated file is stale the
moment the backend constant changes and nobody runs the script, so THIS file is
the other side: it re-renders the generated content and fails when the committed
file differs. The drift cannot reach `main`; it can only be resolved by running
the generator.

Why a test and not a CI step
----------------------------
`tests/ci/test_ci_quality_gate.py` already asserts that CI runs this suite, so
putting the guard here puts it on the existing gate rather than on a second
workflow that could be forgotten.

Why not an endpoint instead of a generated constant
---------------------------------------------------
An endpoint cannot drift, because nothing is copied. It also needs a network
round trip before the form can render its category field, and it needs a
fallback for when that request fails — and the fallback is a copy, which
reintroduces the problem under pressure. The reasoning is written out in the
generator's module docstring; this test exists to hold the choice honest, not to
argue it.

WHAT IS ASSERTED, AND WHAT IS NOT
--------------------------------
The rendered TEXT is compared byte for byte, so the comment header is covered
too — a generator whose docstring drifts from its own output is a generator
whose output nobody can trust. The parsed list is additionally compared as a set
against `KNOWN_MERCHANT_CATEGORIES`, which is the assertion that actually
describes the property; the byte comparison is what catches a hand-edit to the
generated file that happens to leave the list correct.
"""

import importlib
import re

import pytest

from src.core.ml_constants import KNOWN_MERCHANT_CATEGORIES

_generator = importlib.import_module("scripts.generate_frontend_vocabulary")

GENERATED_PATH = _generator.TARGET_PATH


def _categories_in(typescript_source: str) -> list[str]:
    """The category literals out of the generated array.

    Parsed rather than imported: the frontend module cannot be imported here,
    and reading the source is also the stronger check — it verifies what is
    COMMITTED rather than what the generator would produce today.
    """
    match = re.search(
        r"export const MERCHANT_CATEGORIES = \[(.*?)\] as const;",
        typescript_source,
        re.DOTALL,
    )
    assert match, (
        "MERCHANT_CATEGORIES is missing or no longer declared `as const`. The "
        "generator's shape changed and the frontend's imports have to follow."
    )
    return re.findall(r'"([^"]+)"', match.group(1))


class TestTheCommittedFileMatchesTheBackend:
    def test_the_generated_file_exists(self) -> None:
        assert GENERATED_PATH.exists(), (
            f"{GENERATED_PATH} is missing. Run "
            "`python scripts/generate_frontend_vocabulary.py`."
        )

    def test_the_committed_file_is_byte_identical_to_a_fresh_render(self) -> None:
        expected = _generator.render_merchant_vocabulary()
        actual = GENERATED_PATH.read_text(encoding="utf-8")
        assert actual == expected, (
            f"{GENERATED_PATH} is stale.\n"
            "Run `python scripts/generate_frontend_vocabulary.py` and commit "
            "the result.\n"
            + _first_difference(actual, expected)
        )

    def test_the_committed_list_equals_the_backend_vocabulary(self) -> None:
        """The property, stated independently of the generator's formatting."""
        committed = _categories_in(GENERATED_PATH.read_text(encoding="utf-8"))
        assert set(committed) == set(KNOWN_MERCHANT_CATEGORIES), (
            "the frontend offers "
            f"{sorted(set(committed) - set(KNOWN_MERCHANT_CATEGORIES))} that the "
            "API rejects, and is missing "
            f"{sorted(set(KNOWN_MERCHANT_CATEGORIES) - set(committed))} that it "
            "accepts"
        )

    def test_no_category_is_duplicated(self) -> None:
        committed = _categories_in(GENERATED_PATH.read_text(encoding="utf-8"))
        assert len(committed) == len(set(committed)), (
            "a duplicated option renders two identical entries in the selector"
        )

    def test_the_list_is_sorted_so_a_regeneration_is_a_no_op(self) -> None:
        """Determinism is what makes the byte comparison above meaningful.

        Without it, regenerating without a backend change could produce a diff,
        and a diff is what everyone learns to ignore.
        """
        committed = _categories_in(GENERATED_PATH.read_text(encoding="utf-8"))
        assert committed == sorted(committed)

    def test_the_header_says_not_to_hand_edit(self) -> None:
        """The generated file must be self-describing.

        Somebody WILL open this file to add a category, and the reason that is
        wrong is not obvious from a bare array of strings — an array in
        `src/lib/` looks exactly like every other hand-maintained constant in
        the project.
        """
        header = GENERATED_PATH.read_text(encoding="utf-8")[:400]
        assert "GENERATED FILE" in header
        assert "DO NOT EDIT BY HAND" in header
        assert "scripts/generate_frontend_vocabulary.py" in header


class TestTheGeneratorItself:
    def test_the_render_is_deterministic(self) -> None:
        assert _generator.render_merchant_vocabulary() == (
            _generator.render_merchant_vocabulary()
        )

    def test_the_render_tracks_the_backend_constant(self) -> None:
        """A change to the backend must MOVE the rendered output.

        The other half of the stale-file guard, and the half that catches the
        generator silently rendering something constant — a generator with a
        hardcoded list would keep the previous test green forever.
        """
        rendered = _generator.render_merchant_vocabulary()
        for category in KNOWN_MERCHANT_CATEGORIES:
            assert f'"{category}"' in rendered, f"{category} is not rendered"
        assert len(_categories_in(rendered)) == len(KNOWN_MERCHANT_CATEGORIES)

    def test_the_schema_version_is_bumped_by_hand_not_generated(self) -> None:
        """A machine-bumped version would never bump.

        `SCHEMA_VERSION` is a claim a human makes when the SHAPE changes, so it
        is a plain constant; the test here just pins that it is an int, so a
        string slips past nobody.
        """
        assert isinstance(_generator.SCHEMA_VERSION, int)
        assert f"SCHEMA_VERSION = {_generator.SCHEMA_VERSION}" in (
            _generator.render_merchant_vocabulary()
        )


def _first_difference(actual: str, expected: str) -> str:
    """Where the committed file stopped matching, in one readable line."""
    actual_lines = actual.splitlines()
    expected_lines = expected.splitlines()
    for index, (got, want) in enumerate(zip(actual_lines, expected_lines)):
        if got != want:
            return f"first difference at line {index + 1}:\n  committed: {got}\n  expected: {want}"
    if len(actual_lines) != len(expected_lines):
        return (
            f"line count differs: committed {len(actual_lines)}, "
            f"expected {len(expected_lines)}"
        )
    return "files differ only in trailing bytes"


@pytest.fixture(autouse=True)
def _the_generator_must_not_write_during_a_test():
    """This file regenerates in memory and compares; it never writes.

    A test that rewrites the artefact it is asserting on can make itself green.
    The generator's `main()` is the only thing in this path that writes, and it
    is not called here.
    """
    before = GENERATED_PATH.read_bytes() if GENERATED_PATH.exists() else None
    yield
    after = GENERATED_PATH.read_bytes() if GENERATED_PATH.exists() else None
    assert before == after, "a test wrote to the generated file"


def test_no_json_shadow_copy_of_the_vocabulary_exists_in_the_frontend() -> None:
    """There is exactly one copy of this list on the frontend side.

    Belt to the byte comparison's braces: if somebody adds a hand-maintained
    array next to the generated one, this says so. The constant is read as TEXT
    because importing it is not possible from a Python test, and a copy that
    cannot be imported is exactly the kind that goes stale unnoticed.
    """
    frontend = GENERATED_PATH.parent
    offenders = []
    for path in frontend.glob("*.ts"):
        if path.name == GENERATED_PATH.name:
            continue
        source = path.read_text(encoding="utf-8")
        # Every canonical category, and the list is only interesting if several
        # of them appear together.
        if sum(1 for c in KNOWN_MERCHANT_CATEGORIES if f'"{c}"' in source) >= 3:
            offenders.append(path.name)
    assert not offenders, (
        f"{offenders} look like a second copy of the merchant vocabulary. The "
        "list is generated; import MERCHANT_CATEGORIES from "
        f"{GENERATED_PATH.name} instead of restating it."
    )


def test_the_generated_module_declares_no_behaviour() -> None:
    """A generated file that can acquire logic stops being generated.

    Everything in it has to be data or a constant derived from data, or the next
    `render_merchant_vocabulary()` has to reproduce the code too, and a
    hand-edited function in a DO-NOT-EDIT file is the worst possible outcome.
    """
    source = GENERATED_PATH.read_text(encoding="utf-8")
    body = "\n".join(
        line
        for line in source.splitlines()
        if not line.strip().startswith("//") and not line.strip().startswith("*")
    )
    for forbidden in ("function", "=>", "require(", "import "):
        assert forbidden not in body, (
            f"{GENERATED_PATH.name} contains {forbidden!r}. The generated module "
            "must stay data-only; logic belongs in a hand-written module that "
            "imports from it."
        )