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
