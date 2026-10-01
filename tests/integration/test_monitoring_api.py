"""Monitoring API integration tests — drift, metrics, dashboard, reference data."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


class TestDriftEndpoint:
    """GET /api/v1/monitoring/drift — drift report."""

    @pytest.fixture(autouse=True)
    def _isolate_drift_singleton(self):
        """Save and restore the module-level drift service.

        ``monitoring._drift_service`` is a process-wide singleton that tests
        in this module both seed and inspect. Without this, the two tests
        below leave it un-seeded for whatever runs next — or, worse, seeded
        for whatever ran before, which makes the result depend on test order.
        An order-dependent test is the exact defect b6cb2c6 just removed from
        the rule engine, and it does not get reintroduced here.
        """
        from src.api.v1 import monitoring as monitoring_module

        service = monitoring_module._drift_service
        saved = (service.is_initialized, service.reference_data)
        try:
            yield
        finally:
            service.is_initialized, service.reference_data = saved

    @pytest.mark.asyncio
    async def test_get_drift_report_returns_200(
        self, test_client: AsyncClient, auth_headers: dict, mock_db: AsyncMock
    ):
        """GET /monitoring/drift should return 200 with drift report."""
        # Mock empty fraud scores (endpoint reads via .scalars().all())
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await test_client.get(
            "/api/v1/monitoring/drift",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "drift_detected" in data
        assert "features_drifted" in data
        assert "drift_share" in data

    @pytest.mark.asyncio
    async def test_drift_report_requires_auth(self, test_client: AsyncClient):
        """GET /monitoring/drift without auth should return 401."""
        response = await test_client.get("/api/v1/monitoring/drift")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refuses_to_seed_a_reference_that_is_too_small(
        self, test_client: AsyncClient, auth_headers: dict, mock_db: AsyncMock
    ):
        """DRIFT-002: a baseline too small for a 10-quantile PSI must not persist.

        On a database seeded by ``seed_demo_data.py`` there are 11 fraud
        scores. The old path computed ``reference_size = max(11 // 2, 50) =
        50``, took all 11 rows as the reference, and left an EMPTY current
        window — so the very first call could not compare anything, and what
        it saved became permanent: the module-level ``_drift_service`` keeps
        it for the process lifetime and ``load_reference_from_db`` re-reads it
        into every later process.

        11 rows would then be compared against real traffic forever, at
        whatever PSI a 10-quantile split of 11 points happens to produce. The
        test asserts the refusal instead, and that the operator is told why
        and what to do.
        """
        from src.api.v1 import monitoring as monitoring_module

        scores = [
            _score(i)
            for i in range(11)
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = scores
        mock_db.execute = AsyncMock(return_value=mock_result)

        # The singleton must start un-seeded for this to be the code path under
        # test; other tests in this module may have seeded it.
        monitoring_module._drift_service.is_initialized = False

        response = await test_client.get(
            "/api/v1/monitoring/drift",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reference_transactions_count"] == 0, (
            "a reference was persisted from 11 rows"
        )
        assert "No drift reference" in data["message"]
        assert str(monitoring_module.MIN_DRIFT_REFERENCE_ROWS) in data["message"], (
            "the operator must be told the minimum, not just that it failed"
        )
        assert monitoring_module._drift_service.reference_data is None, (
            "the service must not hold a baseline it refused to persist"
        )

    @pytest.mark.asyncio
    async def test_a_too_small_reference_is_never_written_to_the_database(
        self, test_client: AsyncClient, auth_headers: dict, mock_db: AsyncMock
    ):
        """The refusal must happen BEFORE the write, not after.

        A guard that logs an error and then persists the row anyway has moved
        the failure rather than fixed it. Asserted against the service method
        itself, not against ``db.add``: the module singleton carries no
        database session, so ``save_reference_to_db`` returns early and a
        check on ``db.add`` passes even with the guard removed — which is
        exactly what the first version of this test did.
        """
        from src.api.v1 import monitoring as monitoring_module

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_score(i) for i in range(11)]
        mock_db.execute = AsyncMock(return_value=mock_result)
        monitoring_module._drift_service.is_initialized = False

        with patch.object(
            monitoring_module._drift_service,
            "save_reference_to_db",
            new=AsyncMock(),
        ) as saver:
            await test_client.get("/api/v1/monitoring/drift", headers=auth_headers)

        saver.assert_not_called()


def _score(i: int):
    """A minimal stand-in for a FraudScore row."""
    from src.models.fraud_score import FraudClassification

    row = MagicMock()
    row.rule_score = float(i % 100)
    row.ml_score = float(i % 47)
    row.ensemble_score = float(i % 90)
    row.threshold = 70.0
    row.classification = FraudClassification.LEGITIMATE
    return row


class TestMetricsEndpoint:
    """GET /api/v1/monitoring/metrics — model performance metrics."""

    @pytest.mark.asyncio
    async def test_get_metrics_returns_200(
        self, test_client: AsyncClient, auth_headers: dict, mock_db: AsyncMock
    ):
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
    async def test_get_dashboard_returns_200(
        self, test_client: AsyncClient, auth_headers: dict, mock_db: AsyncMock
    ):
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
    async def test_model_status_is_derived_not_asserted(
        self, test_client: AsyncClient, auth_headers: dict, mock_db: AsyncMock
    ):
        """The dashboard must not claim a working model it never asked about.

        This line used to be the literal `"operational"`, computed from
        nothing: the panel reported a healthy model while `/health/ready`
        reported `not_loaded`, in the same process, off the same object. The
        value now comes from `transactions.ml_model_status()`, and this asserts
        it tracks the real `is_available` in BOTH directions.

        Both directions matter. Asserting only the loaded case would pass again
        the day someone reverted to a literal, because a model IS loaded in
        this environment — a check that cannot fail when the code is wrong is
        not a check.

        `is_available` is a read-only property on MLModelService, so the patch
        lands on the CLASS: that is what a reader would use to simulate an
        absent model, and it is the state a stale or truncated artifact
        actually produces in the container.
        """
        from src.schemas.monitoring import ModelStatus
        from src.services.ml_model import MLModelService

        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.scalar_one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        for available in (True, False):
            with patch.object(MLModelService, "is_available", available):
                response = await test_client.get(
                    "/api/v1/monitoring/dashboard",
                    headers=auth_headers,
                )

                assert response.status_code == 200
                expected = ModelStatus.OK if available else ModelStatus.NOT_LOADED
                assert response.json()["model_status"] == expected, (
                    f"with is_available={available} the dashboard reports a model "
                    "state it did not measure"
                )

    @pytest.mark.asyncio
    async def test_dashboard_and_readiness_agree_on_the_model(
        self, test_client: AsyncClient, auth_headers: dict, mock_db: AsyncMock
    ):
        """One signal, two endpoints — asserted as agreement, not as a shared helper.

        Both read `ml_model_status()`, so they cannot diverge while that holds.
        This test exists to make the DIVERGENCE visible if someone reintroduces a
        literal on either side, which is what a shared helper alone would not
        catch: someone can change `/monitoring/dashboard` to hardcode a string
        and every unit test of the helper still passes.
        """
        from src.services.ml_model import MLModelService

        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.scalar_one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(MLModelService, "is_available", False):
            dashboard = await test_client.get(
                "/api/v1/monitoring/dashboard", headers=auth_headers
            )
            readiness = await test_client.get("/health/ready")

        assert dashboard.status_code == 200
        assert readiness.status_code == 200
        assert dashboard.json()["model_status"] == readiness.json()["checks"]["ml_model"], (
            "the dashboard and the readiness probe disagree about the model"
        )
        assert dashboard.json()["model_status"] == "not_loaded"

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
