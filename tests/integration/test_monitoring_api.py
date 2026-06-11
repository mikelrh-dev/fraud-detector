"""Monitoring API integration tests — drift, metrics, dashboard, reference data."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


class TestDriftEndpoint:
    """GET /api/v1/monitoring/drift — drift report."""

    @pytest.mark.asyncio
    async def test_get_drift_report_returns_200(self, test_client: AsyncClient, auth_headers: dict, mock_db: AsyncMock):
        """GET /monitoring/drift should return 200 with drift report."""
        # Mock empty fraud scores
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await test_client.get(
            "/api/v1/monitoring/drift",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "drift_detected" in data
        assert "drift_score" in data
        assert "feature_drifts" in data
        assert "evaluated_at" in data

    @pytest.mark.asyncio
    async def test_drift_report_requires_auth(self, test_client: AsyncClient):
        """GET /monitoring/drift without auth should return 401."""
        response = await test_client.get("/api/v1/monitoring/drift")
        assert response.status_code == 401


class TestMetricsEndpoint:
    """GET /api/v1/monitoring/metrics — model performance metrics."""

    @pytest.mark.asyncio
    async def test_get_metrics_returns_200(self, test_client: AsyncClient, auth_headers: dict, mock_db: AsyncMock):
        """GET /monitoring/metrics should return 200 with metrics."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await test_client.get(
            "/api/v1/monitoring/metrics",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "runs" in data

    @pytest.mark.asyncio
    async def test_metrics_requires_auth(self, test_client: AsyncClient):
        """GET /monitoring/metrics without auth should return 401."""
        response = await test_client.get("/api/v1/monitoring/metrics")
        assert response.status_code == 401


class TestDashboardEndpoint:
    """GET /api/v1/monitoring/dashboard — summary dashboard metrics."""

    @pytest.mark.asyncio
    async def test_get_dashboard_returns_200(self, test_client: AsyncClient, auth_headers: dict, mock_db: AsyncMock):
        """GET /monitoring/dashboard should return 200 with summary."""
        def mock_execute_side_effect(*args, **kwargs):
            r = MagicMock()
            r.scalar.return_value = 0
            r.scalar_one_or_none.return_value = None
            r.all.return_value = []
            return r

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        response = await test_client.get(
            "/api/v1/monitoring/dashboard",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_transactions" in data
        assert "fraud_percentage" in data
        assert "avg_score" in data
        assert "active_alerts" in data

    @pytest.mark.asyncio
    async def test_dashboard_requires_auth(self, test_client: AsyncClient):
        """GET /monitoring/dashboard without auth should return 401."""
        response = await test_client.get("/api/v1/monitoring/dashboard")
        assert response.status_code == 401


class TestReferenceDataEndpoint:
    """POST /api/v1/monitoring/reference-data — admin-only reference data upload."""

    @pytest.mark.asyncio
    async def test_admin_can_set_reference_data(
        self,
        test_client: AsyncClient,
        admin_headers: dict,
    ):
        """POST /monitoring/reference-data with admin should return 200."""
        response = await test_client.post(
            "/api/v1/monitoring/reference-data",
            headers=admin_headers,
            json={"data": [10.0, 20.0, 30.0, 40.0, 50.0]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    @pytest.mark.asyncio
    async def test_analyst_cannot_set_reference_data(
        self,
        test_client: AsyncClient,
        auth_headers: dict,
    ):
        """POST /monitoring/reference-data with analyst should return 403."""
        response = await test_client.post(
            "/api/v1/monitoring/reference-data",
            headers=auth_headers,
            json={"data": [10.0, 20.0, 30.0]},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_reference_data_requires_auth(self, test_client: AsyncClient):
        """POST /monitoring/reference-data without auth should return 401."""
        response = await test_client.post(
            "/api/v1/monitoring/reference-data",
            json={"data": [10.0, 20.0]},
        )
        assert response.status_code == 401
