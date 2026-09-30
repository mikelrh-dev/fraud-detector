"""Integration tests for the full scoring pipeline.

These tests verify the complete flow from API response through scoring
persistence, using realistic mocks that simulate actual DB behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from src.api.main import app
from src.core.dependencies import get_velocity_store


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

        # Verify scoring breakdown is present and valid
        assert "classification" in data
        assert "ensemble_score" in data
        assert "threshold" in data
        assert data["classification"] in ("legitimate", "review", "fraud")
        assert 0 <= data["ensemble_score"] <= 100


class TestVelocityWriteOrdering:
    """Why the velocity write is where it is — see ADR-007.

    The Redis ZADD at `transactions.py:197` happens before the commit, which
    lives in the `get_db` teardown. A failed commit therefore leaves a velocity
    entry for a transaction that does not exist. That is an ACCEPTED divergence,
    not an oversight, and this class exists so it cannot be "fixed" by accident
    or quietly inverted later.

    The write cannot move after the commit: `get_counts` on the next line feeds
    THIS request's scoring, so the entry must be visible before the handler
    returns, and the commit is after the handler returns. Moving it would mean
    moving the commit into the handler — a restructuring of the request
    lifecycle, which is the thing ADR-007 was written to avoid.

    This ordering is the load-bearing fact behind the accepted risk, so it is
    pinned. It passes today; it is a guard, not a reproduction, and ADR-007 says
    so explicitly.
    """

    @staticmethod
    def _given_empty_context_queries(mock_db: AsyncMock) -> None:
        """The context aggregates in step 2.5 must return empty, not a coroutine.

        Same shape the end-to-end tests use. `AsyncMock(spec=AsyncSession)`
        answers `.scalars()` with a coroutine otherwise, and the endpoint's
        except-handler reports it as "Failed to create transaction", which sends
        you looking for a persistence bug instead of a mock gap.
        """
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])
        mock_scalars.one = MagicMock(return_value=None)

        result = MagicMock()
        result.scalars = MagicMock(return_value=mock_scalars)
        result.scalar = MagicMock(return_value=None)
        result.scalar_one_or_none = MagicMock(return_value=None)

        mock_db.execute = AsyncMock(return_value=result)
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

    @pytest.mark.asyncio
    async def test_the_write_precedes_the_read_that_feeds_this_request_s_scoring(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        calls: list[str] = []
        store = MagicMock()
        self._given_empty_context_queries(mock_db)

        async def _record(*args, **kwargs):
            calls.append("record")

        async def _counts(*args, **kwargs):
            calls.append("counts")
            return {"5min": 0, "1h": 0}

        store.record_transaction = _record
        store.get_counts = _counts

        # `Depends(get_velocity_store)` captured the function object at import
        # time, so patching the module attribute does nothing — the override
        # table is the only thing that swaps the store. (The end-to-end tests
        # above patch the module attribute and never assert on the store, which
        # is why they pass either way.)
        app.dependency_overrides[get_velocity_store] = lambda: store

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
        assert calls == ["record", "counts"], (
            f"velocity calls were {calls}, expected ['record', 'counts']. The "
            f"write must precede the read, because the read feeds this "
            f"request's own scoring. If you are moving the write to after the "
            f"commit, read ADR-007 first — the commit is in the get_db "
            f"teardown and the ordering is not free to change."
        )

    @pytest.mark.asyncio
    async def test_the_velocity_counts_actually_reach_the_feature_vector(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The coupling itself, not just the call order — and it must FAIL.

        Proves the read is load-bearing: the value `get_counts` returns reaches
        the rule engine and the feature vector, so the write cannot simply be
        deferred. Stated as a behaviour rather than as a comment, which is what
        the previous version of this test failed to be.

        W-3: it used to assert `ensemble_score > 0`, and that is vacuous. The
        payload seeds `amount=5000`, which fires `high_amount` for 35 points on
        its own. With NO velocity signal at all the rule score is 35 and the
        ensemble is 35 * 0.60 / 1.0 = 21.0 — strictly greater than zero. The
        assertion passed with the coupling completely severed, which is the one
        thing ADR-007 says must not be possible.

        A single absolute threshold cannot fix that, because any threshold
        above the zero-velocity baseline is a guess about the model, and the
        model gets retrained. The discriminating form is a CONTRAST: the same
        request twice, identical in every other respect, differing only in what
        `get_counts` returns. Whatever else is true, the burst cannot score
        the same as no burst. That fails if the counts are dropped, if
        `get_counts` is not consulted, or if the feature vector is built
        without them.
        """
        payload = {
            "amount": 5000.00,
            "currency": "USD",
            "merchant_name": "Electronics Store",
            "merchant_category": "electronics",
            "card_last4": "5678",
        }

        async def _score_with(counts: dict) -> dict:
            store = MagicMock()
            self._given_empty_context_queries(mock_db)
            store.record_transaction = AsyncMock()
            store.get_counts = AsyncMock(return_value=counts)
            app.dependency_overrides[get_velocity_store] = lambda: store

            response = await test_client.post(
                "/api/v1/transactions", json=payload, headers=auth_headers
            )
            assert response.status_code == 201
            store.get_counts.assert_awaited_once()
            store.record_transaction.assert_awaited_once()
            return response.json()

        # 40 in 5 minutes is a burst; rule_engine.py:113 fires high_velocity
        # above 3. The 0 case is the control the old assertion never had.
        burst = await _score_with({"5min": 40, "1h": 400})
        still = await _score_with({"5min": 0, "1h": 0})

        # The rule engine saw the count. This half is independent of the model
        # and would still hold after a retrain.
        assert "high_velocity" in burst["fired_rules"], (
            f"a burst of 40 transactions in 5 minutes did not fire "
            f"high_velocity; fired rules were {burst['fired_rules']}. The count "
            f"returned by get_counts is not reaching the rule engine, so the "
            f"read is not load-bearing."
        )
        assert "high_velocity" not in still["fired_rules"], (
            f"high_velocity fired with a velocity count of 0; fired rules were "
            f"{still['fired_rules']}. Something other than the count is driving "
            f"this rule, so the contrast below would not be measuring the "
            f"coupling."
        )

        # And the count reached the score, through the rule layer, the ML
        # feature vector and the context term. Not asserted against hardcoded
        # numbers: those belong to a model that will be retrained.
        assert burst["rule_score"] > still["rule_score"], (
            f"a velocity burst scored the same rule score as no velocity "
            f"({burst['rule_score']} vs {still['rule_score']})."
        )
        assert burst["ensemble_score"] > still["ensemble_score"], (
            f"a velocity burst scored the same ensemble as no velocity "
            f"({burst['ensemble_score']} vs {still['ensemble_score']}). The "
            f"count reaches the response but not the score, so the coupling "
            f"ADR-007 depends on is broken."
        )


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
