"""CI install-contract tests — remediation Wave 0 (restore quality gates).

Parses `.github/workflows/ci.yml` and proves the backend jobs install from
the real dependency files instead of a phantom editable install, and that
the docker-build smoke test points at the Dockerfiles that actually exist
(`docker/Dockerfile.api`, `docker/Dockerfile.frontend`). Without this guard,
both backend jobs fail at install on every push and the docker smoke test
never validates the images we ship.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


def _all_run_commands() -> list[str]:
    """Return every `run:` payload across all jobs/steps."""

    commands: list[str] = []

    def _walk(node) -> None:
        if isinstance(node, dict):
            run = node.get("run")
            if isinstance(run, str):
                commands.append(run)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(_workflow())
    return commands


def _install_commands() -> list[str]:
    """Return `run:` payloads that install Python dependencies with pip."""
    return [c for c in _all_run_commands() if "pip install" in c]


def test_no_editable_self_install_in_workflow():
    for command in _all_run_commands():
        assert "pip install -e ." not in command, (
            f"workflow uses 'pip install -e .' but no pyproject.toml/setup.py "
            f"exists, so every backend job fails at install:\n{command}"
        )


def test_pip_installs_reference_requirements_files():
    commands = _install_commands()
    assert commands, "no pip install step found in workflow"
    for command in commands:
        assert "-r requirements.txt" in command, (
            f"pip install step does not install from requirements.txt:\n{command}"
        )


def test_backend_jobs_install_dev_tooling_from_requirements_dev():
    lint_job = _workflow()["jobs"]["backend-lint"]
    lint_runs = [
        s.get("run", "") for s in lint_job["steps"] if isinstance(s, dict) and s.get("run")
    ]
    assert any("-r requirements-dev.txt" in r for r in lint_runs), (
        "backend-lint must install ruff/mypy via requirements-dev.txt"
    )
    test_job = _workflow()["jobs"]["backend-test"]
    test_runs = [
        s.get("run", "") for s in test_job["steps"] if isinstance(s, dict) and s.get("run")
    ]
    assert any("-r requirements-dev.txt" in r for r in test_runs), (
        "backend-test needs pytest/pytest-cov which live in requirements-dev.txt"
    )


def test_docker_build_uses_real_dockerfiles():
    job = _workflow()["jobs"]["docker-build"]
    runs = "\n".join(
        s.get("run", "") for s in job["steps"] if isinstance(s, dict) and s.get("run")
    )
    assert "-f docker/Dockerfile.api" in runs, (
        f"docker-build must build docker/Dockerfile.api (that is where the "
        f"backend image lives), got:\n{runs}"
    )
    assert "-f docker/Dockerfile.frontend" in runs, (
        f"docker-build must build docker/Dockerfile.frontend (that is where "
        f"the frontend image lives), got:\n{runs}"
    )
