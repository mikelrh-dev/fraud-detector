"""Transaction API integration tests — CRUD, scoring pipeline, soft delete, auth.

Uses the test client with mocked DB and Redis dependencies.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from redis.exceptions import ConnectionError

from src.models.fraud_score import FraudClassification, FraudScore
from src.models.transaction import Transaction, TransactionStatus

pytestmark = pytest.mark.asyncio


def _make_mock_transaction(**overrides) -> MagicMock:
    """Helper to create a mock Transaction with sensible defaults."""
    txn = MagicMock(spec=Transaction)
    txn.id = overrides.get("id", uuid4())
    txn.amount = overrides.get("amount", 100.0)
    txn.currency = overrides.get("currency", "USD")
    txn.merchant_name = overrides.get("merchant_name", "Test Store")
    txn.merchant_category = overrides.get("merchant_category", "retail")
    txn.card_last4 = overrides.get("card_last4", "1234")
    txn.status = overrides.get("status", TransactionStatus.PENDING)
    txn.user_id = overrides.get("user_id", uuid4())
    txn.deleted_at = overrides.get("deleted_at", None)
    txn.created_at = overrides.get("created_at", "2024-01-15T12:00:00+00:00")
    txn.updated_at = overrides.get("updated_at", "2024-01-15T12:00:00+00:00")
    return txn


def _make_mock_score(**overrides) -> MagicMock:
    """Helper to create a mock FraudScore with sensible defaults."""
    score = MagicMock(spec=FraudScore)
    score.transaction_id = overrides.get("transaction_id", uuid4())
    score.rule_score = overrides.get("rule_score", 45.0)
    score.ml_score = overrides.get("ml_score", 60.0)
    score.ensemble_score = overrides.get("ensemble_score", 52.0)
    score.threshold = overrides.get("threshold", 70.0)
    score.classification = overrides.get("classification", FraudClassification.REVIEW)
    return score


def _velocity_pipe(*execute_results: object) -> MagicMock:
    """Build a mock Redis pipeline whose execute resolves to the given results."""
    pipe = MagicMock()
    pipe.zadd = MagicMock(return_value=1)
    pipe.expire = MagicMock(return_value=True)
    pipe.zremrangebyscore = MagicMock(return_value=0)
    pipe.zcount = MagicMock(return_value=0)
    pipe.execute = AsyncMock(return_value=list(execute_results))
    return pipe


def _empty_scalars_result() -> MagicMock:
    """Mock execute result whose scalars().all() yields no rows."""
    scalar = MagicMock()
    scalar.all.return_value = []
    result = MagicMock()
    result.scalars.return_value = scalar
    return result


class TestCreateTransaction:
    """POST /api/v1/transactions."""

    async def test_create_transaction_returns_score(self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict):
        """Creating a valid transaction should return 201 with scoring breakdown."""
        # Mock the two context queries (recent + all-user) used by the scoring pipeline
        mock_scalar_result = MagicMock()
        mock_scalar_result.all.return_value = []

        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value = mock_scalar_result

        mock_db.execute = AsyncMock(return_value=mock_select_result)

        response = await test_client.post(
            "/api/v1/transactions",
            json={
                "amount": 500.00,
                "currency": "USD",
                "merchant_name": "Grocery Store",
                "merchant_category": "groceries",
                "card_last4": "1234",
                "user_id": "00000000-0000-0000-0000-000000000001",
            },
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "transaction_id" in data
        assert "rule_score" in data
        assert "ml_score" in data
        assert "ensemble_score" in data
        assert "threshold" in data
        assert "classification" in data
        assert "fired_rules" in data
        assert isinstance(data["fired_rules"], list)
        assert data["classification"] in ("legitimate", "review", "fraud")

    async def test_invalid_payload_returns_422(self, test_client: AsyncClient, auth_headers: dict):
        """Missing required fields should return 422."""
        response = await test_client.post(
            "/api/v1/transactions",
            json={"amount": "not_a_number"},  # missing currency, merchant, etc.
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_negative_amount_returns_422(self, test_client: AsyncClient, auth_headers: dict):
        """Negative amount should return 422."""
        response = await test_client.post(
            "/api/v1/transactions",
            json={
                "amount": -100,
                "currency": "USD",
                "merchant_name": "Store",
                "card_last4": "1234",
                "user_id": "00000000-0000-0000-0000-000000000001",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_missing_auth_returns_401(self, test_client: AsyncClient):
        """No auth header should return 401."""
        response = await test_client.post(
            "/api/v1/transactions",
            json={
                "amount": 100,
                "currency": "USD",
                "merchant_name": "Store",
                "card_last4": "1234",
                "user_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert response.status_code == 401


class TestGetTransaction:
    """GET /api/v1/transactions/{id}."""

    async def test_get_existing_transaction_returns_200(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """Existing transaction should return 200 with details and scoring breakdown."""
        txn = _make_mock_transaction()
        score = _make_mock_score(transaction_id=txn.id)

        txn_result = MagicMock()
        txn_result.scalar_one_or_none.return_value = txn

        score_scalar = MagicMock()
        score_scalar.all.return_value = [score]
        score_result = MagicMock()
        score_result.scalars.return_value = score_scalar

        # Order matters: transaction lookup first, then batched score query
        mock_db.execute = AsyncMock(side_effect=[txn_result, score_result])

        response = await test_client.get(
            f"/api/v1/transactions/{txn.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["merchant_name"] == "Test Store"
        assert data["currency"] == "USD"
        # Score-aware fields (FRD-DASH-SCORE-001 / FRD-DASH-SCORE-003)
        assert data["risk_score"] == 52.0
        assert data["classification"] == "review"
        assert data["scoring"]["rule_score"] == 45.0
        assert data["scoring"]["ml_score"] == 60.0
        assert data["scoring"]["ensemble_score"] == 52.0
        assert data["scoring"]["threshold"] == 70.0
        assert data["scoring"]["classification"] == "review"

    async def test_get_transaction_without_score_returns_nulls(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """Transaction without a fraud_scores row returns nulls and HTTP 200."""
        txn = _make_mock_transaction()

        txn_result = MagicMock()
        txn_result.scalar_one_or_none.return_value = txn

        empty_scalar = MagicMock()
        empty_scalar.all.return_value = []
        empty_score_result = MagicMock()
        empty_score_result.scalars.return_value = empty_scalar

        mock_db.execute = AsyncMock(side_effect=[txn_result, empty_score_result])

        response = await test_client.get(
            f"/api/v1/transactions/{txn.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["risk_score"] is None
        assert data["scoring"] is None
        assert data["classification"] is None

    async def test_get_nonexistent_transaction_returns_404(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """Nonexistent transaction should return 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await test_client.get(
            f"/api/v1/transactions/{uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestListTransactions:
    """GET /api/v1/transactions."""

    async def test_list_transactions_returns_paginated(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """List should return paginated results with score-aware rows."""
        txn = _make_mock_transaction()
        score = _make_mock_score(transaction_id=txn.id)

        # Mock the result for list query (scalars().all())
        mock_scalar_result = MagicMock()
        mock_scalar_result.all.return_value = [txn]

        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value = mock_scalar_result

        # Mock the count query
        mock_count_result = MagicMock()
        mock_count_result.all.return_value = [(txn.id,)]

        # Mock the batched score query
        score_scalar = MagicMock()
        score_scalar.all.return_value = [score]
        score_result = MagicMock()
        score_result.scalars.return_value = score_scalar

        mock_db.execute = AsyncMock()
        # Order matters: count → page → batched scores (third position)
        mock_db.execute.side_effect = [
            mock_count_result,
            mock_select_result,
            score_result,
        ]

        response = await test_client.get(
            "/api/v1/transactions?page=1&page_size=20",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["page"] == 1
        assert data["page_size"] == 20
        # Score-aware fields (FRD-DASH-SCORE-002 / FRD-DASH-SCORE-003)
        assert data["items"][0]["risk_score"] == 52.0
        assert data["items"][0]["classification"] == "review"

    async def test_list_batches_score_queries_no_n_plus_1(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """Scores for a 2-row page must come from exactly one batched query."""
        txns = [_make_mock_transaction(), _make_mock_transaction()]
        scores = [
            _make_mock_score(transaction_id=txns[0].id),
            _make_mock_score(transaction_id=txns[1].id),
        ]

        # Count query
        mock_count_result = MagicMock()
        mock_count_result.all.return_value = [(t.id,) for t in txns]

        # Page query
        page_scalar = MagicMock()
        page_scalar.all.return_value = txns
        page_result = MagicMock()
        page_result.scalars.return_value = page_scalar

        # Batched score query (one for both rows)
        score_scalar = MagicMock()
        score_scalar.all.return_value = scores
        score_result = MagicMock()
        score_result.scalars.return_value = score_scalar

        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            mock_count_result,
            page_result,
            score_result,
        ]

        response = await test_client.get(
            "/api/v1/transactions?page=1&page_size=20",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        # count + page + exactly ONE batched score query — no per-row queries
        assert mock_db.execute.call_count == 3


class TestDeleteTransaction:
    """DELETE /api/v1/transactions/{id}."""

    async def test_admin_can_soft_delete(
        self, test_client: AsyncClient, mock_db: AsyncMock, admin_headers: dict
    ):
        """Admin can soft-delete a transaction."""
        txn = _make_mock_transaction()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = txn
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await test_client.delete(
            f"/api/v1/transactions/{txn.id}",
            headers=admin_headers,
        )
        assert response.status_code == 204

    async def test_analyst_cannot_delete(
        self, test_client: AsyncClient, auth_headers: dict
    ):
        """Analyst cannot delete (admin only)."""
        response = await test_client.delete(
            "/api/v1/transactions/00000000-0000-0000-0000-000000000001",
            headers=auth_headers,
        )
        assert response.status_code == 403


class TestCreateTransactionVelocity:
    """POST /api/v1/transactions — Redis velocity counts drive scoring (FD-VEL-001..003)."""

    _PAYLOAD = {
        "amount": 500.00,
        "currency": "USD",
        "merchant_name": "Grocery Store",
        "merchant_category": "groceries",
        "card_last4": "1234",
        "user_id": "00000000-0000-0000-0000-000000000001",
    }

    async def test_velocity_count_fires_high_velocity_rule(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_redis: AsyncMock, auth_headers: dict
    ):
        """Seeded 5min count of 4 must fire high_velocity (>3, self-inclusive)."""
        mock_db.execute = AsyncMock(return_value=_empty_scalars_result())
        # record pipeline (ignored) then read pipeline with 4 txns in 5min / 1h
        mock_redis.pipeline.side_effect = [
            _velocity_pipe(1, True, 0),
            _velocity_pipe(0, 4, 4),
        ]

        response = await test_client.post("/api/v1/transactions", json=self._PAYLOAD, headers=auth_headers)

        assert response.status_code == 201
        assert "high_velocity" in response.json()["fired_rules"]

    async def test_1h_count_is_distinct_from_5min_and_no_query_a(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_redis: AsyncMock, auth_headers: dict
    ):
        """2 txns in 5min / 7 in 1h: the pipeline must be asked both windows
        (FD-VEL-002) and Query A is gone — only Query B touches Postgres."""
        mock_db.execute = AsyncMock(return_value=_empty_scalars_result())
        pipe_read = _velocity_pipe(0, 2, 7)
        mock_redis.pipeline.side_effect = [
            _velocity_pipe(1, True, 0),
            pipe_read,
        ]

        response = await test_client.post("/api/v1/transactions", json=self._PAYLOAD, headers=auth_headers)

        assert response.status_code == 201
        assert "high_velocity" not in response.json()["fired_rules"]
        # Both velocity windows were counted in the read pipeline (real 1h, not the 5min dup)
        assert pipe_read.zcount.call_count == 2
        mins = [call.args[1] for call in pipe_read.zcount.call_args_list]
        assert mins[0] != mins[1]
        assert all(call.args[2] == "+inf" for call in pipe_read.zcount.call_args_list)
        # Exactly one Postgres query (Query B — known cards / amount stats); no 5-min scan
        assert mock_db.execute.call_count == 1

    async def test_redis_down_falls_back_to_postgres(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_redis: AsyncMock,
        auth_headers: dict, caplog: pytest.LogCaptureFixture,
    ):
        """Redis unreachable: scoring completes via PG velocity values, HTTP 201 (FD-VEL-003)."""
        mock_redis.pipeline = MagicMock(side_effect=ConnectionError("redis down"))

        now = datetime.now(tz=timezone.utc)
        pg_scalar = MagicMock()
        pg_scalar.all.return_value = [
            now - timedelta(minutes=1),  # in 5min
            now - timedelta(minutes=20),  # in 1h but not 5min
        ]
        pg_result = MagicMock()
        pg_result.scalars.return_value = pg_scalar
        # fallback query first, then Query B
        mock_db.execute = AsyncMock(side_effect=[pg_result, _empty_scalars_result()])

        response = await test_client.post("/api/v1/transactions", json=self._PAYLOAD, headers=auth_headers)

        assert response.status_code == 201
        assert mock_db.execute.call_count == 2  # _pg_counts + Query B
        assert any("redis" in r.message.lower() for r in caplog.records)
