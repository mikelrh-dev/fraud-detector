"""CI quality-gate tests — R3-007 (audit-wave1-blockers Phase 4).

Parses `.github/workflows/ci.yml` and proves the pytest step carries both a
coverage measurement flag (`--cov=src`) and a hard coverage floor
(`--cov-fail-under=<T>`). Without this guard, coverage can silently collapse
to zero without failing CI.
"""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

# Honest measured baseline after audit-wave1-blockers Phases 1-3 landed
# (documented in openspec/changes/audit-wave1-blockers/notes.md).
# Interim value <80: wave 4 (test debt) is expected to raise this toward 80.
COVERAGE_FLOOR = 80


def _pytest_run_commands() -> list[str]:
    """Return every `run:` payload across all jobs/steps that invokes pytest."""
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    commands: list[str] = []

    def _walk(node) -> None:
        if isinstance(node, dict):
            run = node.get("run")
            if isinstance(run, str) and any(
                line.strip().startswith("pytest") for line in run.splitlines()
            ):
                commands.append(run)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(workflow)
    return commands


def test_ci_workflow_exists_with_pytest_step():
    commands = _pytest_run_commands()
    assert commands, f"no pytest invocation found in {CI_WORKFLOW}"


def test_pytest_step_measures_src_coverage():
    for command in _pytest_run_commands():
        assert "--cov=src" in command, (
            f"pytest step does not measure src coverage:\n{command}"
        )


def test_pytest_step_pins_coverage_floor():
    pattern = re.compile(r"--cov-fail-under=(\d+)")
    for command in _pytest_run_commands():
        match = pattern.search(command)
        assert match is not None, (
            f"pytest step has no --cov-fail-under floor:\n{command}"
        )
        assert int(match.group(1)) >= COVERAGE_FLOOR, (
            f"coverage floor {match.group(1)} is below the recorded "
            f"baseline {COVERAGE_FLOOR}:\n{command}"
        )


def _mypy_configured_excludes() -> list[str]:
    """The `exclude` list under `[tool.mypy]`, read from the file itself.

    Parsed rather than hardcoded so this guard follows the configuration. If
    `tests/` is ever added to the exclude list, the CI prose it was written for
    becomes true again and this test stops objecting without being edited.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    block = re.search(r"^\[tool\.mypy\]$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    assert block is not None, "no [tool.mypy] section in pyproject.toml"
    exclude = re.search(r'^exclude\s*=\s*\[(.*?)\]', block.group(1), re.M | re.S)
    if exclude is None:
        return []
    return re.findall(r'"([^"]+)"', exclude.group(1))


def test_the_ci_mypy_comment_names_the_command_as_the_source_of_scope():
    """The CI file must say WHERE the scope comes from, not cite a config.

    The mypy step used to comment that keeping mypy on `src/` was "a decision
    already written down in pyproject.toml", quoting a line that said the same
    thing. Both were wrong: `[tool.mypy] exclude` lists `scripts/`, `alembic/`
    and `notebooks/`, and tests are absent from it. The scope comes from the
    COMMAND.

    Asserted positively rather than by forbidding the old wording. A negative
    string check cannot tell a claim from a denial — the first draft of this test
    failed on the corrected comment, because the correction quoted the sentence
    it was correcting. Requiring the true mechanism to be present is both easier
    to satisfy honestly and harder to satisfy by accident.
    """
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    mypy_comments = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("#") and "mypy" in line.lower()
    ]
    assert any("mypy src/" in line for line in mypy_comments), (
        "no CI comment states that the mypy scope comes from the command "
        "`mypy src/`. Say that instead of citing pyproject.toml: its "
        f"[tool.mypy] exclude is {_mypy_configured_excludes()} and does not "
        f"mention tests."
    )


def test_the_pyproject_mypy_comment_names_the_command_too():
    """The origin of the false claim, not just the copy of it.

    `pyproject.toml:47` is where CI's sentence came from, and it was the line
    that actually said tests were ruled out of mypy. Correcting only the copy
    leaves the source in place for the next person to quote.

    Scoped to the "Known looseness debt" list, which is where the claim lived.
    Scoping matters: the first draft checked the whole `[tool.mypy]` comment
    block for the string `mypy src/`, and the block's own header line
    (`# mypy — type gate (`mypy src/`)`) contains it — so the guard passed with
    the false claim restored. A guard that cannot fail is the defect this
    repository keeps auditing, including in the very file it was written for.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    debt = re.search(r"^# Known looseness debt.*?^\[tool\.mypy\]$", text, re.M | re.S)
    assert debt is not None, "no 'Known looseness debt' list in pyproject.toml"

    # Joined, not line-by-line: the correction is a wrapped bullet, and a
    # per-line scan reads only its first fragment and misses the rest.
    region = debt.group(0).lower()
    assert region.strip(), "the looseness list is empty; this guard would be vacuous"

    assert not ("excluded" in region and "test" in region), (
        "the looseness list still claims a configuration exclusion for tests. "
        f"[tool.mypy] exclude is {_mypy_configured_excludes()} — tests are not "
        f"in it. The scope comes from the command `mypy src/`."
    )
    assert "mypy src/" in region, (
        "the looseness list must state that the gate runs `mypy src/`, which is "
        "where the test scope actually comes from"
    )
