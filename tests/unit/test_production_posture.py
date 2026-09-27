"""Production posture tests — the switches that guard a real deployment.

C1 regression: ``.env.example`` shipped ``API_ENV`` while the Settings field is
``environment``, so pydantic read ``ENVIRONMENT``. Every branch keyed on
``settings.environment == "production"`` was therefore unreachable, and a box
configured with ``API_ENV=production`` silently ran dev secrets, wildcard CORS
and public API docs. These tests pin the actual behaviour, not the intent.
"""

import pytest

from src.core.config import Settings
from src.core.dependencies import require_any_role


def _clear_secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("JWT_SECRET_KEY", "API_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)


def _set_secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "j" * 43)
    monkeypatch.setenv("API_SECRET_KEY", "a" * 43)


class TestEnvironmentSwitch:
    """The environment switch must be readable from both documented names."""

    def test_defaults_to_development(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("API_ENV", raising=False)
        _set_secret_env(monkeypatch)
        assert Settings().environment == "development"

    def test_reads_canonical_environment_name(self, monkeypatch: pytest.MonkeyPatch):
        """ENVIRONMENT is the name the code actually reads."""
        monkeypatch.delenv("API_ENV", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        _set_secret_env(monkeypatch)
        assert Settings().environment == "production"

    def test_legacy_api_env_alias_reaches_production(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """API_ENV must not be a dead variable (the C1 bug).

        Before the alias, this produced environment='development' with an
        open CORS list and dev secrets.
        """
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("API_ENV", "production")
        _set_secret_env(monkeypatch)

        settings = Settings()

        assert settings.environment == "production"
        # And the production-only consequences must actually engage.
        assert settings.cors_origins == [settings.frontend_url]
        assert settings.cors_origins != ["*"]


class TestProductionSecretGuard:
    """The R1-005 guard must fire — and only for production."""

    def test_production_without_secrets_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        _clear_secret_env(monkeypatch)
        with pytest.raises(ValueError, match="explicit env injection"):
            Settings()

    def test_production_reached_through_api_env_also_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """The guard must not be bypassable via the legacy name."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("API_ENV", "production")
        _clear_secret_env(monkeypatch)
        with pytest.raises(ValueError, match="explicit env injection"):
            Settings()

    def test_production_with_secrets_boots(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        _set_secret_env(monkeypatch)
        assert Settings().environment == "production"

    def test_development_does_not_require_secrets(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        _clear_secret_env(monkeypatch)
        assert Settings().environment == "development"


class TestProductionHardening:
    """The production branch must be materially different from dev."""

    def test_cors_is_locked_in_production(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
        _set_secret_env(monkeypatch)
        assert Settings().cors_origins == ["https://app.example.com"]

    def test_cors_is_wildcard_in_development(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        _set_secret_env(monkeypatch)
        assert Settings().cors_origins == ["*"]


class TestRequireAnyRole:
    """require_role is exact equality; require_any_role accepts a set."""

    def test_rejects_empty_role_set(self):
        with pytest.raises(ValueError):
            require_any_role()

    @pytest.mark.parametrize(
        ("role", "allowed", "expected"),
        [
            ("analyst", ("analyst", "admin"), True),
            ("admin", ("analyst", "admin"), True),
            ("analyst", ("admin",), False),
            ("guest", ("analyst", "admin"), False),
        ],
    )
    def test_membership(self, role: str, allowed: tuple[str, ...], expected: bool):
        from fastapi import HTTPException

        checker = require_any_role(*allowed)
        try:
            checker({"user_id": "u", "role": role})
            allowed_result = True
        except HTTPException as exc:
            assert exc.status_code == 403
            allowed_result = False
        assert allowed_result is expected

    def test_admin_passes_an_analyst_or_admin_route(self):
        """The A8 bug: an admin got 403 from require_role('analyst')."""
        checker = require_any_role("analyst", "admin")
        user = {"user_id": "u", "role": "admin"}
        assert checker(user) is user
