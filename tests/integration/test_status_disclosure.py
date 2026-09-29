"""`/api/v1/status` must not fingerprint the build it is running.

OPS-01, audit 2026-09-29. The endpoint returned
`{"version": "0.1.0", "environment": settings.environment}` with no auth
dependency, so anyone who could reach it learned which release was deployed
and whether it was running dev defaults. The endpoint itself is worth keeping
— a health probe may use it — so the fix is to the payload, not the route.

The interesting property is the one that is easy to lose: the *route stays*.
A future edit that "restores" version and environment re-adds a finding that
was closed, and these tests are what make that a build failure rather than a
line in a changelog nobody rereads.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestStatusEndpointDisclosure:
    async def test_reports_liveness(self, test_client: AsyncClient):
        """The reason the endpoint exists: it answers "is the service up"."""
        response = await test_client.get("/api/v1/status")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_does_not_disclose_the_version(self, test_client: AsyncClient):
        response = await test_client.get("/api/v1/status")
        body = response.json()
        assert "version" not in body
        # Not merely renamed: no value anywhere in the payload that looks
        # like a release number.
        assert "0.1.0" not in str(body)

    async def test_does_not_disclose_the_environment(
        self, test_client: AsyncClient
    ):
        """Not even the current one. Asserting the absence of a key is the
        contract; asserting its value would let someone re-add it with a
        different name and still call it covered."""
        response = await test_client.get("/api/v1/status")
        body = response.json()
        assert "environment" not in body
        assert "development" not in str(body)
        assert "production" not in str(body)

    async def test_needs_no_authentication(self, test_client: AsyncClient):
        """Unauthenticated by design — that is what makes it usable as a
        probe, and is the whole point of OPS-01 being about the payload
        rather than about adding a dependency."""
        response = await test_client.get("/api/v1/status")
        assert response.status_code == 200
