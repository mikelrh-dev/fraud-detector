"""Monitoring rate limit tests — the limiter must actually be wired.

Importing ``check_rate_limit`` is not enough: the dependency must be attached
to the router AND a matching budget must exist in ``RATE_LIMITS``, otherwise
``check_rate_limit`` returns early and the endpoint stays unlimited.
"""

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from src.api.v1.rate_limit import RATE_LIMITS

MONITORING_BUDGET = 30


class TestMonitoringRateLimitBudget:
    """The monitoring prefix must have a configured budget."""

    def test_monitoring_has_rate_limit_budget(self):
        assert "/api/v1/monitoring" in RATE_LIMITS

    def test_monitoring_budget_is_tighter_than_transactions(self):
        """Monitoring is expensive; it should not be the cheapest to hammer."""
        monitoring_max = RATE_LIMITS["/api/v1/monitoring"][0]
        transactions_max = RATE_LIMITS["/api/v1/transactions"][0]
        assert monitoring_max < transactions_max


class TestMonitoringRateLimitEnforced:
    """Exceeding the budget must return 429."""

    @staticmethod
    def _db_result():
        """DB result stub satisfying both .scalar() and .scalars().all()."""
        from unittest.mock import MagicMock

        result = MagicMock()
        result.scalar = MagicMock(return_value=0)
        result.scalars.return_value.all.return_value = []
        return result

    @pytest.mark.asyncio
    async def test_monitoring_returns_429_after_budget_exhausted(
        self, test_client: AsyncClient, mock_db, auth_headers: dict
    ):
        mock_db.execute = AsyncMock(return_value=self._db_result())

        statuses = [
            (
                await test_client.get(
                    "/api/v1/monitoring/dashboard", headers=auth_headers
                )
            ).status_code
            for _ in range(MONITORING_BUDGET + 1)
        ]

        assert all(code == 200 for code in statuses[:MONITORING_BUDGET]), (
            f"first {MONITORING_BUDGET} requests should succeed, got {statuses}"
        )
        assert statuses[MONITORING_BUDGET] == 429, (
            f"request {MONITORING_BUDGET + 1} should be rate limited, got {statuses}"
        )

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present_on_429(
        self, test_client: AsyncClient, mock_db, auth_headers: dict
    ):
        mock_db.execute = AsyncMock(return_value=self._db_result())

        responses = [
            await test_client.get(
                "/api/v1/monitoring/metrics", headers=auth_headers
            )
            for _ in range(MONITORING_BUDGET + 1)
        ]
        limited = responses[-1]
        assert limited.status_code == 429
        assert "retry-after" in limited.headers

    @pytest.mark.asyncio
    async def test_health_endpoints_are_not_rate_limited(
        self, test_client: AsyncClient, mock_redis
    ):
        """Probes and scrapers must never be throttled."""
        statuses = [
            (await test_client.get("/health")).status_code
            for _ in range(MONITORING_BUDGET + 5)
        ]
        assert all(code == 200 for code in statuses)
