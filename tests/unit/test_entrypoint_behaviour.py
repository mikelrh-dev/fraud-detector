"""A16: the entrypoint must migrate before serving, and fail loudly if it cannot.

These exercise `docker/entrypoint.api.sh` as a real POSIX shell script with a
stand-in `alembic` on PATH, rather than only reading it. Reading it proves
nothing about the part that matters: whether a failed migration actually stops
the server from starting, or whether the container boots anyway and 500s on the
first request.

Skipped when no POSIX shell is available; the compose invariants in
test_deployment_health_invariants.py still guard the wiring.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[2] / "docker" / "entrypoint.api.sh"

# Git Bash on Windows, then a plain POSIX shell.
_CANDIDATES = (
    r"C:\Program Files\Git\bin\bash.exe",
    "/bin/sh",
    "/usr/bin/sh",
    shutil.which("bash") or "",
    shutil.which("sh") or "",
)
SHELL = next((p for p in _CANDIDATES if p and Path(p).exists()), None)

pytestmark = pytest.mark.skipif(
    SHELL is None, reason="no POSIX shell available to execute the entrypoint"
)


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """A directory with a fake `alembic` and a fake server command on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exec(
        bin_dir / "alembic",
        "#!/bin/sh\n"
        'echo "FAKE-ALEMBIC $*"\n'
        'if [ "${FAKE_ALEMBIC_FAIL:-0}" = "1" ]; then exit 3; fi\n'
        "exit 0\n",
    )
    _write_exec(
        tmp_path / "fake-server",
        '#!/bin/sh\necho "FAKE-SERVER $*"\nexit 0\n',
    )
    # The entrypoint is executed from the repo, but cwd does not matter to it.
    return tmp_path


def _run(sandbox: Path, *args: str, fail_migration: bool = False) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{sandbox / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    if fail_migration:
        env["FAKE_ALEMBIC_FAIL"] = "1"
    return subprocess.run(
        [SHELL or "sh", str(ENTRYPOINT), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


class TestEntrypointOrder:
    def test_runs_upgrade_head_before_serving(self, sandbox: Path) -> None:
        result = _run(sandbox, str(sandbox / "fake-server"), "src.api.main:app")

        assert result.returncode == 0, result.stderr
        assert "FAKE-ALEMBIC upgrade head" in result.stdout
        assert "FAKE-SERVER src.api.main:app" in result.stdout

    def test_migrations_happen_first(self, sandbox: Path) -> None:
        result = _run(sandbox, str(sandbox / "fake-server"))

        assert result.stdout.index("FAKE-ALEMBIC") < result.stdout.index("FAKE-SERVER"), (
            "the server must not start before migrations are applied"
        )

    def test_passes_the_original_arguments_through(self, sandbox: Path) -> None:
        result = _run(
            sandbox,
            str(sandbox / "fake-server"),
            "src.api.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        )

        assert "FAKE-SERVER src.api.main:app --host 0.0.0.0 --port 8000" in result.stdout


class TestEntrypointFailsLoudly:
    def test_a_failed_migration_stops_the_container(self, sandbox: Path) -> None:
        """A16: the whole point. Booting anyway means 500s on first request."""
        result = _run(
            sandbox,
            str(sandbox / "fake-server"),
            fail_migration=True,
        )

        assert result.returncode != 0, (
            "a failed migration must exit non-zero so the container is marked "
            "failed, not healthy and serving errors"
        )

    def test_the_server_never_starts_after_a_failed_migration(
        self, sandbox: Path
    ) -> None:
        result = _run(
            sandbox,
            str(sandbox / "fake-server"),
            fail_migration=True,
        )

        assert "FAKE-SERVER" not in result.stdout, (
            "uvicorn must not be exec'd when migrations failed"
        )

    def test_propagates_the_migration_exit_code(self, sandbox: Path) -> None:
        result = _run(sandbox, str(sandbox / "fake-server"), fail_migration=True)
        assert result.returncode == 3


class TestEntrypointSyntax:
    def test_is_valid_posix_shell(self) -> None:
        result = subprocess.run(
            [SHELL or "sh", "-n", str(ENTRYPOINT)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr

    def test_uses_set_e(self) -> None:
        """Without `set -e` the script would continue past a failed migration."""
        body = ENTRYPOINT.read_text(encoding="utf-8")
        assert "set -e" in body

    def test_execs_rather_than_spawning(self) -> None:
        """`exec` makes uvicorn PID 1 so it receives SIGTERM and stops cleanly."""
        body = ENTRYPOINT.read_text(encoding="utf-8")
        assert 'exec "$@"' in body
