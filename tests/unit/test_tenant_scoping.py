"""A7: cross-tenant aggregate reads.

``/monitoring/dashboard`` and ``/monitoring/drift`` ran four and one aggregate
queries respectively with no tenant predicate, guarded only by a valid JWT.
``/transactions/graph/stats`` returned whole-graph counts to any authenticated
caller.

The listing route in ``transactions.py`` already scoped non-admins to their own
rows (R1-003), so the correct behaviour was established in the codebase and
simply not applied here.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.security import create_access_token

pytestmark = pytest.mark.asyncio


def _headers(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id=str(uuid.uuid4()), role=role)}"}


class TestDashboardScoping:
    """Non-admins must only ever see their own aggregates."""

    async def test_non_admin_queries_are_scoped_to_their_own_user(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.execute = AsyncMock(
            side_effect=lambda *a, **k: MagicMock(scalar=MagicMock(return_value=1))
        )

        response = await test_client.get("/api/v1/monitoring/dashboard", headers=_headers("analyst"))

        assert response.status_code == 200
        assert mock_db.execute.await_count >= 4, "expected the four aggregates"

        # Every aggregate must carry a user filter. Comparing the compiled
        # statement is the only way to prove the predicate exists, since a mock
        # returns the same value either way.
        for call in mock_db.execute.await_args_list:
            sql = str(call.args[0])
            assert "user_id" in sql, f"unscoped aggregate leaked: {sql}"

    async def test_admin_keeps_the_cross_user_view(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """A monitoring dashboard exists to show the fleet; admins keep it."""
        mock_db.execute = AsyncMock(
            side_effect=lambda *a, **k: MagicMock(scalar=MagicMock(return_value=1))
        )

        response = await test_client.get("/api/v1/monitoring/dashboard", headers=_headers("admin"))

        assert response.status_code == 200
        for call in mock_db.execute.await_args_list:
            assert "user_id" not in str(call.args[0]), (
                "an admin must still see cross-user metrics"
            )

    async def test_a_role_without_analyst_privileges_is_still_scoped(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """The old guard was a bare JWT, so even a low-privilege role read everything."""
        mock_db.execute = AsyncMock(
            side_effect=lambda *a, **k: MagicMock(scalar=MagicMock(return_value=1))
        )

        await test_client.get("/api/v1/monitoring/dashboard", headers=_headers("guest"))

        for call in mock_db.execute.await_args_list:
            assert "user_id" in str(call.args[0]), (
                "scoping must not depend on the role holding analyst privileges"
            )


class TestDriftScoping:
    """The drift window was global, so one analyst saw everyone's scores."""

    async def test_non_admin_drift_window_is_scoped(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        await test_client.get("/api/v1/monitoring/drift", headers=_headers("analyst"))

        assert mock_db.execute.await_count >= 1
        for call in mock_db.execute.await_args_list:
            assert "user_id" in str(call.args[0]), "drift window is not scoped"

    async def test_admin_drift_window_is_global(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        await test_client.get("/api/v1/monitoring/drift", headers=_headers("admin"))

        for call in mock_db.execute.await_args_list:
            assert "user_id" not in str(call.args[0])


class TestGraphStatsIsAdminOnly:
    """The fraud graph is cross-user by design, so it cannot be scoped."""

    async def test_non_admin_is_refused(self, test_client: AsyncClient) -> None:
        response = await test_client.get(
            "/api/v1/transactions/graph/stats", headers=_headers("analyst")
        )
        assert response.status_code == 403

    async def test_admin_is_allowed(self, test_client: AsyncClient) -> None:
        response = await test_client.get(
            "/api/v1/transactions/graph/stats", headers=_headers("admin")
        )
        assert response.status_code in (200, 500)
        assert response.status_code != 403

    async def test_graph_features_stay_available_to_non_admins(
        self, test_client: AsyncClient
    ) -> None:
        """Scoping must not break the endpoint that actually feeds scoring."""
        user_id = str(uuid.uuid4())
        response = await test_client.get(
            f"/api/v1/transactions/{user_id}/graph-features",
            headers={
                "Authorization": f"Bearer {create_access_token(user_id=user_id, role='analyst')}"
            },
        )
        assert response.status_code != 403
