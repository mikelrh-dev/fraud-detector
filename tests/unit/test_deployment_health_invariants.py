"""A16/A17/A18/A23/A24: deployment and health invariants.

None of these had runtime coverage, so a regression in any of them is silent:
the stack starts, reports healthy, and quietly loses a capability. They are
pinned here against the actual compose file, Dockerfile and engine config.

A16 — nothing ran migrations, and the container healthcheck hit a static
       `/health` that never touches the database, so an unmigrated volume
       produced a "healthy" container and 500s on the first request.
A17 — `models/` was never copied into the image, so it only worked because
       compose bind-mounts it. Without the mount the whole 0.25-weighted ML
       layer silently returned 0.0.
A18 — a misconfigured SHAP worker acked messages with nothing written, and
       `/health/workers` reported "ok" because its only signal is PEL depth.
A23 — the Redis healthcheck could not authenticate, and `redis-cli ping` exits 0
       while printing NOAUTH, so it was a false green.
A24 — Postgres had no pool bounds and no timeouts, while Redis did.
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
DOCKERFILE_API = REPO_ROOT / "docker" / "Dockerfile.api"
NGINX_CONF = REPO_ROOT / "docker" / "nginx.conf"


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def api_dockerfile() -> str:
    return DOCKERFILE_API.read_text(encoding="utf-8")


class TestMigrations:
    """A16: the image ships alembic but nothing ran it."""

    def test_entrypoint_script_exists(self) -> None:
        assert (REPO_ROOT / "docker" / "entrypoint.api.sh").is_file()

    def test_api_image_runs_migrations_before_serving(self, api_dockerfile: str) -> None:
        assert "entrypoint.api.sh" in api_dockerfile
        assert "ENTRYPOINT" in api_dockerfile, (
            "the entrypoint must be registered, or the migrations never run"
        )

    def test_migrations_run_and_fail_loudly(self) -> None:
        script = (REPO_ROOT / "docker" / "entrypoint.api.sh").read_text(
            encoding="utf-8"
        )
        assert "alembic upgrade head" in script
        # `set -e` is what turns a migration failure into a non-zero exit rather
        # than a container that boots and 500s later.
        assert "set -e" in script
        assert "exec \"$@\"" in script, (
            "exec is what makes uvicorn PID 1 and receive signals"
        )

    def test_container_healthcheck_can_see_the_database(self, compose: dict) -> None:
        test = " ".join(compose["services"]["api"]["healthcheck"]["test"])
        assert "/health/ready" in test, (
            "/health is a static literal and cannot detect an unmigrated database"
        )
        assert "/health'" not in test


class TestMlArtifacts:
    """A17: models/ must be in the image, not only bind-mounted."""

    def test_models_are_copied_into_the_image(self, api_dockerfile: str) -> None:
        assert "COPY models/" in api_dockerfile

    def test_models_are_copied_before_the_user_switch(self, api_dockerfile: str) -> None:
        """Otherwise the files land owned by root and the app cannot read them."""
        copy_at = api_dockerfile.index("COPY models/")
        user_at = api_dockerfile.index("USER appuser")
        assert copy_at < user_at


class TestRedisHealthcheck:
    """A23: the check has to authenticate to mean anything."""

    def test_healthcheck_sends_the_password(self, compose: dict) -> None:
        test = " ".join(compose["services"]["redis"]["healthcheck"]["test"])
        assert "PONG" in test, (
            "exit code alone is not enough: redis-cli ping prints NOAUTH and "
            "exits 0, which is why the check was a false green"
        )

    def test_healthcheck_has_no_shell_expansion(self, compose: dict) -> None:
        """`$$VAR` in a healthcheck cannot be verified without a running daemon.

        An earlier version passed the password with `redis-cli -a "$$REDIS_PASSWORD"`.
        Whether the container receives `$REDIS_PASSWORD` or the literal `$$` is
        only observable at runtime, and getting it wrong silently reintroduces
        the false green. REDISCLI_AUTH removes the expansion entirely, so the
        invariant is that no `$` appears at all.
        """
        test = " ".join(compose["services"]["redis"]["healthcheck"]["test"])
        assert "$" not in test, (
            "the redis healthcheck should use REDISCLI_AUTH, not shell expansion: "
            "an expansion that cannot be verified here is an expansion that can "
            "be silently wrong"
        )

    def test_uses_rediscli_auth(self, compose: dict) -> None:
        """Keeps the secret out of the process list too, unlike `-a`."""
        assert "REDISCLI_AUTH" in compose["services"]["redis"].get("environment", {})

    def test_server_still_requires_a_password(self, compose: dict) -> None:
        """If the server stopped requiring auth, the check would pass vacuously."""
        assert "--requirepass" in compose["services"]["redis"]["command"]


class TestDatabaseEngineBounds:
    """A24: Postgres needs the same discipline Redis already has."""

    def test_pool_is_bounded(self) -> None:
        from src.core.database import engine

        assert engine.pool.size() > 0
        assert engine.pool._max_overflow > 0, (
            "an unbounded overflow means bursty load queues forever"
        )

    def test_pool_has_a_timeout(self) -> None:
        from src.core.database import engine

        assert engine.pool._timeout > 0, (
            "without pool_timeout a caller waits forever for a free connection"
        )

    def test_stale_connections_are_revalidated(self) -> None:
        """pool_pre_ping: a connection that died while idle must not be handed out."""
        from src.core.database import engine

        assert engine.pool._pre_ping is True

    def test_driver_has_a_command_timeout(self) -> None:
        """The load-bearing one: turns 'hangs forever' into 'fails after N seconds'."""
        from src.core.database import engine

        # Read the source rather than the engine internals: SQLAlchemy does not
        # expose connect_args back from an async engine's pool, and reaching into
        # private attributes would make this test break on an upgrade rather
        # than on a regression.
        source = (REPO_ROOT / "src" / "core" / "database.py").read_text(
            encoding="utf-8"
        )
        assert "command_timeout" in source
        assert engine is not None

    def test_redis_was_already_bounded(self) -> None:
        """Documents the asymmetry this change removed."""
        from src.core.redis import redis_pool

        assert redis_pool.connection_kwargs.get("socket_timeout") is not None


class TestHealthDoesNotLeak:
    """A6: unauthenticated endpoints must not return raw exception text."""

    def test_health_module_has_no_str_exc_in_responses(self) -> None:
        source = (REPO_ROOT / "src" / "api" / "v1" / "health.py").read_text(
            encoding="utf-8"
        )
        assert '"error": str(exc)' not in source, (
            "an unauthenticated endpoint returning str(exc) can leak the "
            "database username, host, SQLSTATE or the failing statement"
        )

    def test_failures_are_logged_in_full(self) -> None:
        """Sanitising the response must not mean losing the diagnostic."""
        source = (REPO_ROOT / "src" / "api" / "v1" / "health.py").read_text(
            encoding="utf-8"
        )
        assert "exc_info=True" in source


class TestShapFailureIsObservable:
    """A18: a misconfigured worker must not look healthy."""

    def test_unavailable_error_does_not_ack(self) -> None:
        source = (REPO_ROOT / "src" / "workers" / "shap_worker.py").read_text(
            encoding="utf-8"
        )
        block = source.split("except ShapUnavailableError", 1)[1]
        handler = block.split("\n    except", 1)[0]
        # Strip comments: the handler explains the old contract in prose, and
        # matching that prose would make this test assert against its own
        # documentation.
        code = "\n".join(
            line for line in handler.splitlines() if not line.strip().startswith("#")
        )
        assert "return True" not in code, (
            "returning True acks the message with nothing written and no DLQ "
            "entry, so the failure leaves no evidence anywhere"
        )
        assert "return False" in code

    def test_failure_is_counted(self) -> None:
        source = (REPO_ROOT / "src" / "workers" / "shap_worker.py").read_text(
            encoding="utf-8"
        )
        block = source.split("except ShapUnavailableError", 1)[1]
        handler = block.split("\n    except", 1)[0]
        assert "shap_skipped_unavailable" in handler

    def test_counters_are_exposed_in_worker_health(self) -> None:
        source = (REPO_ROOT / "src" / "api" / "v1" / "health.py").read_text(
            encoding="utf-8"
        )
        assert "counters.snapshot()" in source

    def test_counters_are_exposed_in_prometheus_metrics(self) -> None:
        source = (REPO_ROOT / "src" / "api" / "v1" / "health.py").read_text(
            encoding="utf-8"
        )
        assert "fraud_detector_worker_failures_total" in source

    def test_counters_module_is_importable_and_works(self) -> None:
        from src.core import counters

        counters.reset()
        counters.shap_skipped_unavailable.inc()
        counters.shap_skipped_unavailable.inc()
        assert counters.snapshot()["shap_skipped_unavailable"] == 2
        counters.reset()


class TestMetricsNotExposed:
    """OPS-02: `/metrics` publishes worker topology with no auth. Accepted.

    ADR-006 accepts that risk and changes no application code, because every
    available fix is worse than the finding: auth breaks scraping the day a
    scraper is added, deleting the endpoint discards the only signal that a
    worker is stuck (A18), and an nginx allow-list cannot be verified without
    a container.

    What makes the acceptance safe is the deployment, not the code — and the
    deployment is configuration that nothing else would catch if it changed.
    So these tests pin the *state that makes the risk acceptable*. They fail
    when someone wires up Prometheus, which is precisely the moment ADR-006
    says the decision has to be revisited rather than inherited.
    """

    def test_api_publishes_no_port(self, compose: dict) -> None:
        """With no published port, the API is only reachable inside the
        compose network — including `/metrics`."""
        assert "ports" not in compose["services"]["api"], (
            "OPS-02 / ADR-006: publishing the api port puts /metrics, which "
            "serves worker topology unauthenticated, on the network"
        )

    def test_nginx_does_not_proxy_metrics(self) -> None:
        """`/metrics` matches neither `location /api/` nor `location /health`,
        so it falls into `location /`, which serves the SPA. That is the only
        reason the endpoint is not reachable from outside."""
        source = NGINX_CONF.read_text(encoding="utf-8")
        proxied = [
            line.strip()
            for line in source.splitlines()
            if "proxy_pass" in line and not line.strip().startswith("#")
        ]
        assert proxied, "no proxy_pass at all — the config no longer matches this test"
        for line in proxied:
            assert "/metrics" not in line, (
                "OPS-02 / ADR-006: nginx now proxies /metrics. Restrict it to "
                "the scraper's IP, a separate listener, or mTLS BEFORE "
                "exposing it, and update ADR-006."
            )

    def test_no_prometheus_scrape_config_in_the_repo(self) -> None:
        """No scraper today, which is why the accepted decision is coherent:
        there is nothing to protect and nothing to break."""
        matches = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in REPO_ROOT.rglob("*.yml")
            if "node_modules" not in path.parts
            and "scrape_configs" in path.read_text(encoding="utf-8", errors="replace")
        ]
        assert not matches, (
            "a Prometheus scrape config appeared. OPS-02 / ADR-006: revisit "
            f"the decision before the first scrape. Found in {matches}"
        )

    def test_the_endpoint_still_exists(self) -> None:
        """The capability is kept on purpose. A19's failure counter is the
        only thing that says a worker is stuck, so this asserts the endpoint
        is not deleted as a side effect of 'fixing' the finding."""
        source = (REPO_ROOT / "src" / "api" / "v1" / "health.py").read_text(
            encoding="utf-8"
        )
        assert '@router.get("/metrics")' in source
