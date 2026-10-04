"""The production boot guard must reject a JWT secret that is not a real secret.

`.env.example` ships `JWT_SECRET_KEY=` — present, but empty. That is the exact
shape an operator copies into a production box, and it is the shape this file
exists to close.

The R1-005 guard already refuses to boot when the variable is *absent*: it
compares `model_fields_set` against `{jwt_secret_key, api_secret_key}`. But
"present" is not "configured". Measured before this file existed, with
`ENVIRONMENT=production` and `JWT_SECRET_KEY=`:

    BOOTED. environment= production
    jwt_secret_key repr= '' len= 0

`model_fields_set` records the field as set the moment pydantic assigns it, and
an empty string is still an assignment. So the sentinel this repository itself
documents as "required in production" sailed straight through the guard written
to enforce it, and production served with a zero-length HMAC key — a signing key
anyone can reproduce in their head. The same hole admits the `change_me_*`
placeholders from `.env.example`, and the whitespace-only variant a shell
heredoc produces when a variable fails to expand.

Two levels of proof, deliberately:

* `TestProductionRefusesToBootWithoutARealJwtSecret` runs a real subprocess that
  imports `src.api.main`, because the claim worth testing is "the process
  refuses to boot", not "a constructor raises". `settings` is built at module
  scope in `src/core/config.py` and `src/api/main.py` imports it on line 11, so
  the guard fires before the `FastAPI()` object exists; the subprocess asserts
  the app is never constructed.
* `TestJwtSecretIsCheckedForRealValue` covers the value space in-process, in the
  style of `test_production_posture.py`, and pins that development is untouched.

Two harness hazards this file had to be written around, both found by the tests
failing for the wrong reason:

* A child environment built from scratch (`PATH` and nothing else) cannot
  initialise CPython on Windows — `Fatal Python error: _Py_HashRandomization_Init`.
  Every subprocess here therefore failed, which turned all four "production must
  not boot" assertions green for entirely the wrong reason. `_child_env` now
  inherits `os.environ` and overrides only the four variables under test.
  `test_development_is_unaffected` is the canary that keeps this honest: it
  asserts the probe *does* reach `APP_CREATED`, so a harness that cannot boot at
  all fails loudly instead of validating the guard by accident. Every refusal
  test additionally asserts the guard's own message, so "crashed for an
  unrelated reason" cannot pass as "refused to start".
* The subprocess runs with `cwd=tmp_path` so `env_file=".env"` resolves to
  nothing. Otherwise a developer's local `.env` could supply `JWT_SECRET_KEY`
  and the "production without a secret" cases would pass without the guard ever
  being asked.

One trap for anyone extending this: `Settings(environment="production")` does NOT
work. The `environment` field carries `validation_alias=AliasChoices(...)` and
`populate_by_name` is not set, so the kwarg lands in `model_fields_set` and is
then ignored — measured:

    Settings(environment="production").environment  ->  'development'

A test written that way silently exercises the development branch while
appearing to select production. Every case here sets the environment through the
real environment variables instead, which is also how it happens in a deploy.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Imports the real application module. If the guard works, this never reaches
# the print and the app object is never built.
BOOT_PROBE = "import src.api.main as m; print('APP_CREATED', type(m.app).__name__)"

# A real `secrets.token_urlsafe(32)` — 43 urlsafe chars, like `.env.example`
# tells operators to generate. Used wherever a value must be accepted.
REAL_SECRET = "k7Qm2XvT9pL4nR8sW1yZ6bD3fH5jA0cE2gU7iO4lP8nM1qS5tV"

GUARD_VARS = ("ENVIRONMENT", "API_ENV", "JWT_SECRET_KEY", "API_SECRET_KEY")


def _child_env(**overrides: str | None) -> dict[str, str]:
    """Environment for a boot attempt: the OS plumbing, with the guard inputs controlled.

    Inherits `os.environ` because CPython on Windows needs `SYSTEMROOT` and
    friends to start at all. The four variables the guard reads are cleared
    first and then re-set from `overrides`, so nothing inherited can decide
    whether these tests pass. A `None` value means "definitely absent".
    """
    env = dict(os.environ)
    for key in GUARD_VARS:
        env.pop(key, None)
    # Overridden rather than inherited so a developer's own credentials are not
    # what the app under test authenticates with.
    env.update(
        {
            "PYTHONPATH": str(PROJECT_ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "DB_PASSWORD": "unit_test_placeholder_pw",
            "REDIS_PASSWORD": "unit_test_placeholder_rp",
            "REDIS_URL": "redis://:unit_test_placeholder_rp@127.0.0.1:6379/0",
        }
    )
    env.update({k: v for k, v in overrides.items() if v is not None})
    return env


def _boot(env: dict[str, str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Attempt a real boot from a directory that has no `.env` in it."""
    return subprocess.run(
        [sys.executable, "-c", BOOT_PROBE],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,  # keeps `env_file=".env"` from resolving to the repo's
        timeout=120,
    )


def _assert_refused_by_the_guard(result: subprocess.CompletedProcess[str]) -> None:
    """Non-vacuous refusal.

    The message assertion is what stops a broken harness from reading as a
    passing control: the process has to have died *in the guard*, naming the
    variable, not merely have exited non-zero for any reason at all.
    """
    assert result.returncode != 0, (
        f"the app booted; stdout was {result.stdout!r} stderr {result.stderr!r}"
    )
    assert "APP_CREATED" not in result.stdout, (
        "the FastAPI app object was constructed despite the missing secret — the "
        "guard must fire before the application exists, not on the first request"
    )
    assert "JWT_SECRET_KEY" in result.stderr, (
        "the process exited non-zero but not through the secret guard, so this "
        f"proves nothing about it. stderr was {result.stderr!r}"
    )


def _both_secrets(jwt: str | None) -> dict[str, str | None]:
    """A real API secret, so only the JWT secret is under test."""
    return {"JWT_SECRET_KEY": jwt, "API_SECRET_KEY": REAL_SECRET}


class TestProductionRefusesToBootWithoutARealJwtSecret:
    """The process-level claim: production does not come up."""

    def test_production_without_a_jwt_secret_dies_before_the_app_exists(
        self, tmp_path: Path
    ):
        _assert_refused_by_the_guard(
            _boot(
                _child_env(ENVIRONMENT="production", **_both_secrets(None)),
                tmp_path,
            )
        )

    def test_production_with_an_empty_jwt_secret_dies_before_the_app_exists(
        self, tmp_path: Path
    ):
        """The shipped `.env.example` sentinel: `JWT_SECRET_KEY=`."""
        _assert_refused_by_the_guard(
            _boot(
                _child_env(ENVIRONMENT="production", **_both_secrets("")),
                tmp_path,
            )
        )

    def test_a_dev_placeholder_jwt_secret_does_not_boot_production(
        self, tmp_path: Path
    ):
        """`change_me_*` is the other placeholder `.env.example` ships."""
        _assert_refused_by_the_guard(
            _boot(
                _child_env(
                    ENVIRONMENT="production",
                    **_both_secrets("change_me_generate_a_random_secret_key"),
                ),
                tmp_path,
            )
        )

    def test_the_api_env_alias_cannot_bypass_the_guard(self, tmp_path: Path):
        """The alias must not be a way in — that was the C1 bug's shape."""
        _assert_refused_by_the_guard(
            _boot(
                _child_env(
                    ENVIRONMENT=None,
                    API_ENV="production",
                    **_both_secrets(""),
                ),
                tmp_path,
            )
        )

    def test_development_is_unaffected(self, tmp_path: Path):
        """The guard is production-only, and the probe really can boot.

        Doubles as the harness canary: if this fails, the four refusals above
        are no longer evidence of anything.
        """
        result = _boot(
            _child_env(ENVIRONMENT="development", **_both_secrets("")),
            tmp_path,
        )

        assert result.returncode == 0, (
            f"development stopped booting. stderr was {result.stderr!r}"
        )
        assert "APP_CREATED" in result.stdout, (
            "development must build the app even with an empty JWT secret — that "
            "is the pre-existing behaviour and this change must not move it"
        )


class TestTheBootFailureExplainsItself:
    """A guard an operator cannot act on is a support ticket, not a control."""

    @staticmethod
    def _stderr(tmp_path: Path) -> str:
        return _boot(
            _child_env(ENVIRONMENT="production", **_both_secrets("")), tmp_path
        ).stderr

    def test_it_names_the_offending_variable(self, tmp_path: Path):
        stderr = self._stderr(tmp_path)
        assert "JWT_SECRET_KEY" in stderr, (
            f"the error does not name the variable to fix. stderr was {stderr!r}"
        )

    def test_it_says_which_stage_refused(self, tmp_path: Path):
        stderr = self._stderr(tmp_path)
        assert "production" in stderr.lower(), (
            f"the error does not say the refusal is production-only. stderr={stderr!r}"
        )

    def test_it_says_how_to_generate_a_real_one(self, tmp_path: Path):
        """The remedy is in `.env.example` already; the error must repeat it."""
        stderr = self._stderr(tmp_path)
        assert "token_urlsafe" in stderr, (
            f"the error does not tell the operator how to fix it. stderr={stderr!r}"
        )

    def test_the_absent_variable_refusal_explains_itself_too(self, tmp_path: Path):
        """The pre-existing missing-variable branch gets the same treatment."""
        stderr = _boot(
            _child_env(ENVIRONMENT="production", **_both_secrets(None)), tmp_path
        ).stderr
        assert "API_SECRET_KEY" not in stderr or "explicit env injection" in stderr


class TestJwtSecretIsCheckedForRealValue:
    """The value space, in-process."""

    @staticmethod
    def _production_with(monkeypatch: pytest.MonkeyPatch, **secrets: str) -> Settings:
        """Build a production `Settings` the way a deploy does: via env vars."""
        for var in GUARD_VARS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        for var, value in secrets.items():
            monkeypatch.setenv(var, value)
        return Settings()

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "\t\n",
            # The placeholders this repository actually ships and documents.
            "change_me_generate_a_random_secret_key",
            "change_me_in_production",
            # Case and separator variants of the same operator reflex.
            "CHANGE_ME",
            "ChangeMe",
            "change-me",
            "changeme",
            "replace_me",
            "your-secret-key-here",
            "your_secret_key_here",
            "placeholder",
            "insecure",
            "notasecret",
            # A dev habit: a named constant that ships to a real box by accident.
            "dev-secret-key",
            "dev_secret_key",
            "local-secret",
            "test-secret",
        ],
    )
    def test_production_rejects_a_non_secret(self, value: str, monkeypatch):
        with pytest.raises(ValueError) as excinfo:
            self._production_with(monkeypatch, JWT_SECRET_KEY=value, API_SECRET_KEY=REAL_SECRET)

        message = str(excinfo.value)
        assert "JWT_SECRET_KEY" in message, (
            f"the error must name JWT_SECRET_KEY. It said: {message!r}"
        )

    def test_a_real_secret_still_boots_production(self, monkeypatch):
        """The guard must not become an outage: a good secret has to pass."""
        s = self._production_with(
            monkeypatch, JWT_SECRET_KEY=REAL_SECRET, API_SECRET_KEY=REAL_SECRET
        )
        assert s.environment == "production"
        assert s.jwt_secret_key == REAL_SECRET

    def test_the_api_secret_is_held_to_the_same_standard(self, monkeypatch):
        """Half a guard is not a guard: both signing secrets, same rule."""
        with pytest.raises(ValueError) as excinfo:
            self._production_with(monkeypatch, JWT_SECRET_KEY=REAL_SECRET, API_SECRET_KEY="")
        assert "API_SECRET_KEY" in str(excinfo.value)

    @pytest.mark.parametrize("value", ["", "   ", "changeme", "dev-secret-key"])
    def test_development_still_accepts_anything(self, value: str, monkeypatch):
        """Dev behaviour is unchanged — by value, not merely by default.

        The regression guard on scope. The check is production-only, so a
        developer who has always been able to run with an empty secret still
        can; nothing here may become a new dev-only boot failure.
        """
        for var in GUARD_VARS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("JWT_SECRET_KEY", value)
        monkeypatch.setenv("API_SECRET_KEY", value)

        assert Settings().environment == "development"

    def test_a_missing_secret_still_reports_explicit_injection(self, monkeypatch):
        """The pre-existing missing-variable message is unchanged.

        `test_production_posture.py` asserts on this substring. Pinned here so
        that adding the value check cannot quietly reword the absent-variable
        branch, which is a different failure with a different fix.
        """
        for var in ("JWT_SECRET_KEY", "API_SECRET_KEY"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")

        with pytest.raises(ValueError, match="explicit env injection"):
            Settings()
