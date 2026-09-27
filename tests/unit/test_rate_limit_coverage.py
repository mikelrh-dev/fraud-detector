"""A4/A3: rate-limit coverage and ingress topology.

A4: ``check_rate_limit`` is a no-op unless the request path matches a prefix in
``RATE_LIMITS`` *and* the router actually declares the dependency. The audit
router and the reports router declared neither, so ``/audit/export`` streamed a
full CSV unmetered.

A3: the API port used to be published as ``8000:8000``. The frontend container is
nginx and already proxies ``/api``, so that port was a second ingress that
skipped the one component able to overwrite ``X-Real-IP``. With it reachable, a
client could send a fresh ``X-Real-IP`` on every request and bypass the per-IP
limiter entirely.

These are configuration invariants with no runtime coverage, so they are pinned
here. A regression in either is silent.
"""

from pathlib import Path

import pytest
import yaml

from src.api.v1.rate_limit import RATE_LIMITS

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
NGINX_CONF_PATH = REPO_ROOT / "docker" / "nginx.conf"


def _prefix_for(path: str) -> str | None:
    """Mirror the matching loop in check_rate_limit: first prefix wins."""
    for prefix in RATE_LIMITS:
        if path.startswith(prefix):
            return prefix
    return None


class TestRateLimitCoverage:
    """Every registered route must resolve to a rate-limit prefix."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/transactions",
            "/api/v1/transactions/abc-123",
            "/api/v1/transactions/abc-123/report",
            "/api/v1/alerts",
            "/api/v1/monitoring/dashboard",
            "/api/v1/audit/transactions/abc-123",
            "/api/v1/audit/analysts/user-1",
            "/api/v1/audit/export",
        ],
    )
    def test_path_is_metered(self, path: str) -> None:
        assert _prefix_for(path) is not None, f"{path} would be unmetered"

    def test_audit_prefix_exists(self) -> None:
        assert "/api/v1/audit" in RATE_LIMITS

    def test_logout_prefix_exists(self) -> None:
        assert "/api/v1/auth/logout" in RATE_LIMITS

    def test_specific_auth_prefixes_are_not_shadowed(self) -> None:
        """Dict order decides the winner, so a broad /auth prefix would break login."""
        assert _prefix_for("/api/v1/auth/login") == "/api/v1/auth/login"
        assert _prefix_for("/api/v1/auth/register") == "/api/v1/auth/register"
        assert _prefix_for("/api/v1/auth/refresh") == "/api/v1/auth/refresh"
        assert _prefix_for("/api/v1/auth/logout") == "/api/v1/auth/logout"

    def test_every_limit_has_a_positive_budget(self) -> None:
        for prefix, (max_requests, window) in RATE_LIMITS.items():
            assert max_requests > 0, f"{prefix} would allow nothing"
            assert window > 0, f"{prefix} has a non-positive window"

    def test_login_stays_the_tightest_auth_limit(self) -> None:
        """Login is the credential-stuffing target; it must not be loosened."""
        login = RATE_LIMITS["/api/v1/auth/login"][0]
        assert login <= RATE_LIMITS["/api/v1/auth/logout"][0]
        assert login <= RATE_LIMITS["/api/v1/auth/register"][0]


class TestRouterDeclaresLimiter:
    """The dependency must be declared on the router, not just configured."""

    @pytest.mark.parametrize("module", ["audit", "reports"])
    def test_router_has_check_rate_limit(self, module: str) -> None:
        source = (REPO_ROOT / "src" / "api" / "v1" / f"{module}.py").read_text(
            encoding="utf-8"
        )
        router_block = source.split("APIRouter(", 1)[1].split(")", 1)[0]
        assert "check_rate_limit" in router_block, (
            f"{module} router does not declare the limiter dependency; the "
            "prefix in RATE_LIMITS alone would not meter it"
        )

    def test_auth_logout_route_has_limiter(self) -> None:
        source = (REPO_ROOT / "src" / "api" / "v1" / "auth.py").read_text(
            encoding="utf-8"
        )
        logout_block = source.split("async def logout_endpoint", 1)[1]
        signature = logout_block.split(") -> None:", 1)[0]
        assert "check_rate_limit" in signature


class TestIngressTopology:
    """The API must not be reachable except through nginx."""

    def test_compose_file_parses(self) -> None:
        assert yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))

    def test_api_port_is_not_published(self) -> None:
        compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
        api = compose["services"]["api"]
        assert "ports" not in api, (
            "the api service publishes a host port, which is a second ingress "
            "that bypasses nginx and makes the per-IP rate limiter spoofable"
        )
        assert "8000" in str(api.get("expose", [])), (
            "the api port should still be exposed to the internal network so "
            "nginx can reach it"
        )

    def test_api_trusts_proxy_headers_in_compose(self) -> None:
        """nginx is the only ingress, so the limiter needs the real client IP."""
        compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
        value = compose["services"]["api"]["environment"]["TRUST_PROXY_HEADERS"]
        assert str(value).lower() == "true", (
            "with nginx as the only ingress, trust_proxy_headers=false would "
            "make every request look like the nginx container and the login "
            "limit would apply to all users at once"
        )

    def test_nginx_overwrites_rather_than_appends_the_client_ip(self) -> None:
        """Appending X-Forwarded-For would let a client prepend a fake address."""
        conf = NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "proxy_set_header X-Real-IP $remote_addr;" in conf
        assert "proxy_set_header X-Forwarded-For $remote_addr;" in conf, (
            "X-Forwarded-For must be overwritten with $remote_addr, not "
            "appended to, or the first entry is client-controlled"
        )

    def test_nginx_proxies_the_api(self) -> None:
        conf = NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "proxy_pass http://api:8000;" in conf
