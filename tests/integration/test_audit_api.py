"""Audit API integration tests — transaction audit trail, analyst activity, export."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


class TestTransactionAuditEndpoint:
    """GET /api/v1/audit/transactions/{id} — audit trail for a transaction."""

    @pytest.mark.asyncio
    async def test_get_audit_trail_returns_200(self, test_client: AsyncClient, auth_headers: dict, mock_db: AsyncMock):
        """GET /audit/transactions/{id} should return 200 with audit entries."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await test_client.get(
            "/api/v1/audit/transactions/00000000-0000-0000-0000-000000000001",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_audit_trail_requires_auth(self, test_client: AsyncClient):
        """GET /audit/transactions/{id} without auth should return 401."""
        response = await test_client.get(
            "/api/v1/audit/transactions/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401


class TestAnalystAuditEndpoint:
    """GET /api/v1/audit/analysts/{id} — analyst activity (admin only)."""

    @pytest.mark.asyncio
    async def test_admin_can_query_analyst_activity(
        self,
        test_client: AsyncClient,
        admin_headers: dict,
        mock_db: AsyncMock,
    ):
        """GET /audit/analysts/{id} with admin should return 200."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await test_client.get(
            "/api/v1/audit/analysts/00000000-0000-0000-0000-000000000002",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_analyst_cannot_query_other_analyst(
        self,
        test_client: AsyncClient,
        auth_headers: dict,
    ):
        """GET /audit/analysts/{id} with analyst should return 403."""
        response = await test_client.get(
            "/api/v1/audit/analysts/00000000-0000-0000-0000-000000000002",
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_analyst_activity_requires_auth(self, test_client: AsyncClient):
        """GET /audit/analysts/{id} without auth should return 401."""
        response = await test_client.get(
            "/api/v1/audit/analysts/00000000-0000-0000-0000-000000000002",
        )
        assert response.status_code == 401


class TestAuditExportEndpoint:
    """POST /api/v1/audit/export — export audit trail (admin only)."""

    @pytest.mark.asyncio
    async def test_admin_can_export_audit(
        self,
        test_client: AsyncClient,
        admin_headers: dict,
        mock_db: AsyncMock,
    ):
        """POST /audit/export with admin should return 200."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await test_client.post(
            "/api/v1/audit/export",
            headers=admin_headers,
            json={
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-12-31T23:59:59Z",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data
        assert "generated_at" in data

    @pytest.mark.asyncio
    async def test_analyst_cannot_export_audit(
        self,
        test_client: AsyncClient,
        auth_headers: dict,
    ):
        """POST /audit/export with analyst should return 403."""
        response = await test_client.post(
            "/api/v1/audit/export",
            headers=auth_headers,
            json={
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-12-31T23:59:59Z",
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_export_requires_auth(self, test_client: AsyncClient):
        """POST /audit/export without auth should return 401."""
        response = await test_client.post(
            "/api/v1/audit/export",
            json={
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-12-31T23:59:59Z",
            },
        )
        assert response.status_code == 401
