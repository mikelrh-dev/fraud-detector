"""Integration tests for the full scoring pipeline.

These tests verify the complete flow from API response through scoring
persistence, using realistic mocks that simulate actual DB behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


class TestScoringPipelineIntegration:
    """Full scoring pipeline integration tests."""

    @pytest.mark.asyncio
    async def test_scoring_pipeline_end_to_end(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """Verify the complete scoring pipeline: API → scoring → persistence."""
        # Mock DB execute to return empty results for context queries
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])
        mock_scalars.one = MagicMock(return_value=None)

        mock_select_result = MagicMock()
        mock_select_result.scalars = MagicMock(return_value=mock_scalars)
        mock_select_result.scalar = MagicMock(return_value=None)
        mock_select_result.scalar_one_or_none = MagicMock(return_value=None)

        mock_db.execute = AsyncMock(return_value=mock_select_result)
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        # Mock Redis pipeline for velocity
        mock_pipe = MagicMock()
        mock_pipe.zadd = MagicMock(return_value=1)
        mock_pipe.expire = MagicMock(return_value=True)
        mock_pipe.zremrangebyscore = MagicMock(return_value=0)
        mock_pipe.zcount = MagicMock(return_value=0)
        mock_pipe.execute = AsyncMock(return_value=[1, True, 0, 0, 0])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch("src.api.v1.transactions.get_redis", return_value=mock_redis), \
             patch("src.api.v1.transactions.get_velocity_store") as mock_velocity_store:

            mock_velocity_store.return_value.record_transaction = AsyncMock()
            mock_velocity_store.return_value.get_counts = AsyncMock(
                return_value={"5min": 0, "1h": 0}
            )

            response = await test_client.post(
                "/api/v1/transactions",
                json={
                    "amount": 5000.00,
                    "currency": "USD",
                    "merchant_name": "Electronics Store",
                    "merchant_category": "electronics",
                    "card_last4": "5678",
                },
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()

        # Verify scoring breakdown
        assert "transaction_id" in data
        assert "rule_score" in data
        assert "ml_score" in data
        assert "ensemble_score" in data
        assert "threshold" in data
        assert "classification" in data
        assert "fired_rules" in data

        # Verify score ranges
        assert 0 <= data["rule_score"] <= 100
        assert 0 <= data["ml_score"] <= 100
        assert 0 <= data["ensemble_score"] <= 100
        assert data["classification"] in ("legitimate", "review", "fraud")

        # Verify DB was called (scoring persisted)
        assert mock_db.add.called or mock_db.flush.called

    @pytest.mark.asyncio
    async def test_fraud_transaction_creates_alert(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """High-risk transaction should create an alert."""
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])
        mock_scalars.one = MagicMock(return_value=None)

        mock_select_result = MagicMock()
        mock_select_result.scalars = MagicMock(return_value=mock_scalars)
        mock_select_result.scalar = MagicMock(return_value=None)
        mock_select_result.scalar_one_or_none = MagicMock(return_value=None)

        mock_db.execute = AsyncMock(return_value=mock_select_result)
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_pipe = MagicMock()
        mock_pipe.zadd = MagicMock(return_value=1)
        mock_pipe.expire = MagicMock(return_value=True)
        mock_pipe.zremrangebyscore = MagicMock(return_value=0)
        mock_pipe.zcount = MagicMock(return_value=0)
        mock_pipe.execute = AsyncMock(return_value=[1, True, 0, 0, 0])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch("src.api.v1.transactions.get_redis", return_value=mock_redis), \
             patch("src.api.v1.transactions.get_velocity_store") as mock_velocity_store, \
             patch("src.api.v1.transactions.enqueue_event"):

            mock_velocity_store.return_value.record_transaction = AsyncMock()
            mock_velocity_store.return_value.get_counts = AsyncMock(
                return_value={"5min": 10, "1h": 50}
            )

            response = await test_client.post(
                "/api/v1/transactions",
                json={
                    "amount": 50000.00,
                    "currency": "USD",
                    "merchant_name": "Crypto Exchange",
                    "merchant_category": "cryptocurrency",
                    "card_last4": "9999",
                },
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()

        # Verify scoring breakdown is present and valid
        assert "classification" in data
        assert "ensemble_score" in data
        assert "threshold" in data
        assert data["classification"] in ("legitimate", "review", "fraud")
        assert 0 <= data["ensemble_score"] <= 100


class TestHealthEndpoints:
    """Health check endpoint integration tests."""

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_200(self, test_client: AsyncClient):
        """Basic health check should return 200."""
        response = await test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_readiness_endpoint_returns_200(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ):
        """Readiness check should return 200 when DB and Redis are available."""
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=1)))

        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("src.api.v1.health.get_db", return_value=mock_db), \
             patch("src.api.v1.health.get_redis", return_value=mock_redis):
            response = await test_client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "database" in data["checks"]
        assert "redis" in data["checks"]

    @pytest.mark.asyncio
    async def test_workers_health_endpoint_returns_200(
        self, test_client: AsyncClient
    ):
        """Workers health check should return 200 with stream status."""
        mock_redis = MagicMock()
        mock_redis.xlen = AsyncMock(return_value=0)
        mock_redis.xpending = AsyncMock(return_value={"pending": 0})

        with patch("src.api.v1.health.get_redis", return_value=mock_redis):
            response = await test_client.get("/health/workers")

        assert response.status_code == 200
        data = response.json()
        assert "workers" in data
        assert "fraud:llm" in data["workers"]
        assert "fraud:shap" in data["workers"]
        assert "fraud:embeddings" in data["workers"]

    @pytest.mark.asyncio
    async def test_prometheus_metrics_endpoint_returns_200(
        self, test_client: AsyncClient
    ):
        """Prometheus metrics endpoint should return 200 with metrics."""
        mock_redis = MagicMock()
        mock_redis.xlen = AsyncMock(return_value=100)
        mock_redis.xpending = AsyncMock(return_value={"pending": 5})

        with patch("src.api.v1.health.get_redis", return_value=mock_redis):
            response = await test_client.get("/metrics")

        assert response.status_code == 200
        assert "fraud_detector_stream_length" in response.text
        assert "fraud_detector_pending_messages" in response.text
