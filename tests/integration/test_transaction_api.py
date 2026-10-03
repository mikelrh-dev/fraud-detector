"""Transaction API integration tests — CRUD, scoring pipeline, soft delete, auth.

Uses the test client with mocked DB and Redis dependencies.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import numpy as np
import pytest
from httpx import AsyncClient
from redis.exceptions import ConnectionError

import src.api.v1.transactions as transactions_api
from src.models.fraud_score import FraudClassification, FraudScore
from src.models.shap_attribution import ShapAttribution
from src.models.transaction import Transaction, TransactionStatus
from src.services.feature_engine import FEATURE_NAMES

pytestmark = pytest.mark.asyncio


def _make_mock_transaction(**overrides) -> MagicMock:
    """Build a mock Transaction; defaults match the conftest analyst user
    (R1-003) so owner-scoped reads succeed under auth_headers.
    """
    txn = MagicMock(spec=Transaction)
    txn.id = overrides.get("id", uuid4())
    txn.amount = overrides.get("amount", 100.0)
    txn.currency = overrides.get("currency", "USD")
    txn.merchant_name = overrides.get("merchant_name", "Test Store")
    txn.merchant_category = overrides.get("merchant_category", "retail")
    txn.card_last4 = overrides.get("card_last4", "1234")
    txn.status = overrides.get("status", TransactionStatus.PENDING)
    # Default owner = the conftest analyst user that auth_headers authenticates,
    # so owner-scoped reads (R1-003) succeed for same-user requests.
    txn.user_id = overrides.get("user_id", UUID("00000000-0000-0000-0000-000000000001"))
    txn.deleted_at = overrides.get("deleted_at")
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

    async def test_create_transaction_returns_score(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
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
                # D3: this said "groceries", which is NOT in
                # KNOWN_MERCHANT_CATEGORIES and is not an alias of "grocery" —
                # an unknown category scoring merchant_risk_level = 0.0 and
                # is_crypto = 0.0, and now a 422. "grocery" is the canonical
                # spelling and produces the same two features.
                "merchant_category": "grocery",
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

    async def test_invalid_payload_returns_422(
        self, test_client: AsyncClient, auth_headers: dict
    ):
        """Missing required fields should return 422."""
        response = await test_client.post(
            "/api/v1/transactions",
            json={"amount": "not_a_number"},  # missing currency, merchant, etc.
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_negative_amount_returns_422(
        self, test_client: AsyncClient, auth_headers: dict
    ):
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


class TestMerchantCategoryIsClosed:
    """D3: the field that decides the features is not free text.

    `merchant_category` drove `is_crypto` and `merchant_risk_level` (D1, D7-3),
    so whoever posted the payload chose which features fired. An unknown value was
    worse than a wrong one: it matched no set, scored both features 0.0, and
    produced a score indistinguishable from a genuinely safe merchant — with a
    counter and a log line nobody was reading. The edge now refuses it.
    """

    def _payload(self, category: object) -> dict:
        return {
            "amount": 500.00,
            "currency": "USD",
            "merchant_name": "Grocery Store",
            "merchant_category": category,
            "card_last4": "1234",
        }

    @pytest.mark.parametrize(
        "invented",
        [
            "zzyzx-plugh-frobnitz",
            "electronics",
            "groceries",
            "retail store",
            "Ecommerce",
        ],
    )
    async def test_an_unknown_category_is_a_422(
        self,
        test_client: AsyncClient,
        auth_headers: dict,
        invented: str,
    ) -> None:
        response = await test_client.post(
            "/api/v1/transactions",
            json=self._payload(invented),
            headers=auth_headers,
        )
        assert response.status_code == 422, response.text
        errors = response.json()["detail"]
        assert isinstance(errors, list)
        assert any(e["loc"][-1] == "merchant_category" for e in errors), errors

    async def test_the_rejection_names_the_vocabulary(
        self, test_client: AsyncClient, auth_headers: dict
    ) -> None:
        """A 422 that does not say what IS accepted is a support ticket.

        The message has to point at the constant, because the operator who has
        to fix the caller cannot read `src/core/ml_constants.py` from a JSON
        error body.
        """
        response = await test_client.post(
            "/api/v1/transactions",
            json=self._payload("zzyzx-plugh-frobnitz"),
            headers=auth_headers,
        )
        assert response.status_code == 422
        message = " ".join(e["msg"] for e in response.json()["detail"])
        assert "KNOWN_MERCHANT_CATEGORIES" in message, message
        assert "src/core/ml_constants.py" in message, message

    @pytest.mark.parametrize(
        "category",
        [
            "retail",
            "grocery",
            "cryptocurrency",
            # Alias spellings must still pass. Rejecting them would throw away
            # the D7-3 alias work, which exists precisely because real feeds send
            # them — and the accepted input has to match what a legitimate
            # producer sends.
            "cripto",
            "crypto-exchange",
            "Crypto-Exchange",
            "crypto exchange",
            "CRYPTO",
            "BTC",
            "  BITCOIN  ",
            # Blank and absent are an incomplete record, not an unknown
            # category: the column is nullable and the field is optional.
            "",
            "   ",
        ],
    )
    async def test_a_known_category_or_spellings_still_pass_validation(
        self, test_client: AsyncClient, auth_headers: dict, category: str
    ) -> None:
        """The schema is constructed directly.

        Not through the endpoint: the create handler needs a database session,
        a velocity store and three collaborators, so a schema-level question
        would be answered by a pile of mocks. `TransactionCreate` is the thing
        that decides, and asserting on it says exactly what it decides.
        """
        from src.schemas.transaction import TransactionCreate

        validated = TransactionCreate(
            amount=500.0,
            currency="USD",
            merchant_name="Grocery Store",
            merchant_category=category,
            card_last4="1234",
        )
        assert validated.merchant_category == category, (
            "the value is returned UNCHANGED, so the stored row is the string "
            "the client sent; both engines normalize it themselves"
        )

    async def test_an_absent_category_is_not_an_error(self) -> None:
        from src.schemas.transaction import TransactionCreate

        validated = TransactionCreate(
            amount=500.0,
            currency="USD",
            merchant_name="Grocery Store",
            card_last4="1234",
        )
        assert validated.merchant_category is None

    async def test_the_edge_is_not_the_only_line_of_defence(self) -> None:
        """D3 validated the boundary; the engine keeps its own observation.

        `FeatureEngine` is driven by batch and replay consumers that never pass
        through `TransactionCreate`, so deleting the counter and the warning would
        remove the only instrumentation those paths have — and it is the
        instrumentation that explains WHY D1 exists.
        """
        from src.core.counters import snapshot
        from src.services.feature_engine import FeatureEngine

        before = snapshot().get("unknown_merchant_category", 0)
        FeatureEngine().transform(
            {
                "amount": 500.0,
                "merchant_name": "Grocery Store",
                "merchant_category": "zzyzx-plugh-frobnitz",
                "timestamp": "2026-10-01T14:00:00+00:00",
            }
        )
        assert snapshot().get("unknown_merchant_category", 0) == before + 1


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

        # SHAP query: no attribution rows for this transaction → null
        shap_scalar = MagicMock()
        shap_scalar.all.return_value = []
        shap_result = MagicMock()
        shap_result.scalars.return_value = shap_scalar

        # Order matters: transaction lookup, batched score query, SHAP query
        mock_db.execute = AsyncMock(side_effect=[txn_result, score_result, shap_result])

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
        # No attribution rows → null (FRD-SHP-001)
        assert data["scoring"]["shap_contributions"] is None

    async def test_get_transaction_returns_shap_contributions_ordered(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """Detail should return shap_contributions ordered by rank via ONE query (FRD-SHP-001)."""
        txn = _make_mock_transaction()
        score = _make_mock_score(transaction_id=txn.id)

        txn_result = MagicMock()
        txn_result.scalar_one_or_none.return_value = txn

        score_scalar = MagicMock()
        score_scalar.all.return_value = [score]
        score_result = MagicMock()
        score_result.scalars.return_value = score_scalar

        shap_scalar = MagicMock()
        shap_scalar.all.return_value = [
            ShapAttribution(
                transaction_id=txn.id, feature="amount", contribution=0.80, rank=1
            ),
            ShapAttribution(
                transaction_id=txn.id,
                feature="tx_count_last_5min",
                contribution=0.45,
                rank=2,
            ),
            ShapAttribution(
                transaction_id=txn.id,
                feature="amount_vs_user_avg",
                contribution=0.30,
                rank=3,
            ),
            ShapAttribution(
                transaction_id=txn.id,
                feature="merchant_risk_level",
                contribution=-0.20,
                rank=4,
            ),
            ShapAttribution(
                transaction_id=txn.id,
                feature="amount_round_number",
                contribution=0.10,
                rank=5,
            ),
        ]
        shap_result = MagicMock()
        shap_result.scalars.return_value = shap_scalar

        # Order matters: transaction lookup, batched score query, SHAP query
        mock_db.execute = AsyncMock(side_effect=[txn_result, score_result, shap_result])

        response = await test_client.get(
            f"/api/v1/transactions/{txn.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        contributions = data["scoring"]["shap_contributions"]
        assert contributions == [
            {"feature": "amount", "contribution": 0.80},
            {"feature": "tx_count_last_5min", "contribution": 0.45},
            {"feature": "amount_vs_user_avg", "contribution": 0.30},
            {"feature": "merchant_risk_level", "contribution": -0.20},
            {"feature": "amount_round_number", "contribution": 0.10},
        ]
        # Exactly three executes: txn + scores + ONE shap query (single query contract)
        assert mock_db.execute.call_count == 3
        # The SHAP query must be ordered by rank
        shap_statement = mock_db.execute.call_args_list[2].args[0]
        shap_sql = str(shap_statement)
        assert "shap_attributions" in shap_sql
        assert "ORDER BY" in shap_sql
        assert "rank" in shap_sql

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
        # No score → the SHAP query is skipped (txn + scores only, no 3rd execute)
        assert mock_db.execute.call_count == 2

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

        # Mock the count query (now uses func.count() → scalar)
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

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
        assert data["total"] == 1
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

        # Count query (now func.count() → scalar)
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2

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

    async def test_date_filters_apply_to_total_count(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """R4: total must reflect date-filtered count, not the unfiltered count.

        Before the fix, count_query omitted date_from/date_to so total
        always returned the full table count regardless of filters.
        """
        txn = _make_mock_transaction()

        # The count query should return 1 (the filtered row), not 5 (all rows).
        # After the fix, the endpoint uses func.count() which returns a scalar.
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1  # func.count() result

        # Page query returns the one matching transaction
        mock_scalar_result = MagicMock()
        mock_scalar_result.all.return_value = [txn]
        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value = mock_scalar_result

        # Batched score query
        score_scalar = MagicMock()
        score_scalar.all.return_value = []
        score_result = MagicMock()
        score_result.scalars.return_value = score_scalar

        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            mock_count_result,
            mock_select_result,
            score_result,
        ]

        response = await test_client.get(
            "/api/v1/transactions?date_from=2024-01-01T00:00:00Z&date_to=2024-01-31T23:59:59Z",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1, (
            "total should reflect the date-filtered count, not the full table"
        )


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
        # D3: this said "groceries", which is NOT in
        # KNOWN_MERCHANT_CATEGORIES and is not an alias of "grocery" — an
        # unknown category scoring merchant_risk_level = 0.0 and is_crypto =
        # 0.0, and now a 422. "grocery" is the canonical spelling and produces
        # the same two features.
        "merchant_category": "grocery",
        "card_last4": "1234",
        "user_id": "00000000-0000-0000-0000-000000000001",
    }

    async def test_velocity_count_fires_high_velocity_rule(
        self,
        test_client: AsyncClient,
        mock_db: AsyncMock,
        mock_redis: AsyncMock,
        auth_headers: dict,
    ):
        """Seeded 5min count of 4 must fire high_velocity (>3, self-inclusive)."""
        mock_db.execute = AsyncMock(return_value=_empty_scalars_result())
        # record pipeline (ignored) then read pipeline with 4 txns in 5min / 1h
        mock_redis.pipeline.side_effect = [
            _velocity_pipe(1, True, 0),
            _velocity_pipe(0, 4, 4),
        ]

        response = await test_client.post(
            "/api/v1/transactions", json=self._PAYLOAD, headers=auth_headers
        )

        assert response.status_code == 201
        assert "high_velocity" in response.json()["fired_rules"]

    async def test_1h_count_is_distinct_from_5min_and_no_query_a(
        self,
        test_client: AsyncClient,
        mock_db: AsyncMock,
        mock_redis: AsyncMock,
        auth_headers: dict,
    ):
        """2 txns in 5min / 7 in 1h: the pipeline must be asked both windows
        (FD-VEL-002) and Query A is gone — only aggregate queries touch Postgres."""
        # 3 aggregate queries: DISTINCT cards, AVG(amount), SELECT amount
        mock_db.execute = AsyncMock(return_value=_empty_scalars_result())
        pipe_read = _velocity_pipe(0, 2, 7)
        mock_redis.pipeline.side_effect = [
            _velocity_pipe(1, True, 0),
            pipe_read,
        ]

        response = await test_client.post(
            "/api/v1/transactions", json=self._PAYLOAD, headers=auth_headers
        )

        assert response.status_code == 201
        assert "high_velocity" not in response.json()["fired_rules"]
        # Both velocity windows were counted in the read pipeline (real 1h, not the 5min dup)
        assert pipe_read.zcount.call_count == 2
        mins = [call.args[1] for call in pipe_read.zcount.call_args_list]
        assert mins[0] != mins[1]
        assert all(call.args[2] == "+inf" for call in pipe_read.zcount.call_args_list)
        # Exactly three Postgres queries (DISTINCT cards, AVG, SELECT amount) — no full-entity scan
        assert mock_db.execute.call_count == 3

    async def test_redis_down_falls_back_to_postgres(
        self,
        test_client: AsyncClient,
        mock_db: AsyncMock,
        mock_redis: AsyncMock,
        auth_headers: dict,
        caplog: pytest.LogCaptureFixture,
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
        # fallback query + 3 aggregate queries (DISTINCT cards, AVG, amounts)
        mock_db.execute = AsyncMock(
            side_effect=[pg_result, _empty_scalars_result(), _empty_scalars_result(), _empty_scalars_result()]
        )

        response = await test_client.post(
            "/api/v1/transactions", json=self._PAYLOAD, headers=auth_headers
        )

        assert response.status_code == 201
        assert mock_db.execute.call_count == 4  # _pg_counts + cards + avg + amounts
        assert any("redis" in r.message.lower() for r in caplog.records)


class TestCreateTransactionShapEnqueue:
    """POST /api/v1/transactions — fraud:shap publish behavior (FD-SHP-001, FD-STREAM-001)."""

    _PAYLOAD = {
        "amount": 500.00,
        "currency": "USD",
        "merchant_name": "Grocery Store",
        # D3: this said "groceries", which is NOT in
        # KNOWN_MERCHANT_CATEGORIES and is not an alias of "grocery" — an
        # unknown category scoring merchant_risk_level = 0.0 and is_crypto =
        # 0.0, and now a 422. "grocery" is the canonical spelling and produces
        # the same two features.
        "merchant_category": "grocery",
        "card_last4": "1234",
        "user_id": "00000000-0000-0000-0000-000000000001",
    }

    # The exact vector the (mocked) feature engine returns — the snapshot must
    # equal the vector actually fed into predict (FD-SHP-001: snapshot==scored vector)
    _KNOWN_VECTOR = np.array([500.0, 0.0, 0.0, 0.0, 0.0, 12.0, 0.0, 0.0, 0.0, 1.0])

    def _patch_scoring(
        self,
        monkeypatch: pytest.MonkeyPatch,
        classification: str,
    ) -> AsyncMock:
        """Force deterministic scoring: known features, known ml_score, forced class."""
        monkeypatch.setattr(
            transactions_api._feature_engine,
            "transform",
            lambda transaction, user_history=None: self._KNOWN_VECTOR,
        )
        monkeypatch.setattr(
            transactions_api._ml_service,
            "predict",
            lambda features: 80.0,
        )
        # The seam moved. `compute_scores` used to hand the verdict to
        # `EnsembleScorer.classify`; it now routes on the layer scores
        # themselves (`ScoringService._classify_routed`), so forcing a verdict
        # means forcing that decision rather than the ensemble's arithmetic.
        # Only the *mocking* changed — these tests are about which stream a
        # given classification produces, and every assertion below still says
        # that. Forcing the verdict through the ensemble's `classify` instead
        # would no longer work, because with ml 80 against threshold 70 the
        # routed policy is `fraud` on its own and no patch of the ensemble
        # could make it `review` or `legitimate`.
        monkeypatch.setattr(
            transactions_api._scoring_service,
            "_classify_routed",
            lambda **layer_scores: classification,
        )
        # A19: the endpoint no longer publishes to Redis directly; it stages a
        # row in the same transaction. The property under test is unchanged —
        # which stream, with which payload — so only the seam moves.
        enqueue_mock = MagicMock()
        monkeypatch.setattr(transactions_api, "enqueue_event", enqueue_mock)
        return enqueue_mock

    async def _post(self, test_client: AsyncClient, auth_headers: dict):
        return await test_client.post(
            "/api/v1/transactions",
            json=self._PAYLOAD,
            headers=auth_headers,
        )

    @pytest.mark.parametrize("classification", ["fraud", "review"])
    async def test_fraud_or_review_enqueues_shap_with_snapshot(
        self,
        classification: str,
        test_client: AsyncClient,
        mock_db: AsyncMock,
        auth_headers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Fraud/review must publish a shap_attribution event with the scored vector snapshot."""
        mock_db.execute = AsyncMock(return_value=_empty_scalars_result())
        staged_mock = self._patch_scoring(monkeypatch, classification)

        response = await self._post(test_client, auth_headers)

        assert response.status_code == 201
        shap_calls = [
            call for call in staged_mock.call_args_list if call.args[1] == "fraud:shap"
            ]
        assert len(shap_calls) == 1
        message = shap_calls[0].args[2]
        assert message["transaction_id"] == response.json()["transaction_id"]
        assert message["classification"] == classification
        # Snapshot equals the exact vector used at scoring time (FD-SHP-001)
        assert message["features"] == self._KNOWN_VECTOR.tolist()
        assert message["feature_names"] == FEATURE_NAMES
        assert isinstance(message["model_fingerprint"], str)

    async def test_legitimate_does_not_enqueue_shap(
        self,
        test_client: AsyncClient,
        mock_db: AsyncMock,
        auth_headers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Legitimate classification must NOT publish a shap_attribution event (FD-SHP-001)."""
        mock_db.execute = AsyncMock(return_value=_empty_scalars_result())
        staged_mock = self._patch_scoring(monkeypatch, "legitimate")

        response = await self._post(test_client, auth_headers)

        assert response.status_code == 201
        assert not any(
            call.args[1] == "fraud:shap" for call in staged_mock.call_args_list
        )

    async def test_scoring_never_touches_redis(
        self,
        test_client: AsyncClient,
        mock_db: AsyncMock,
        auth_headers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """A19: Redis being down cannot affect the request, by construction.

        This replaces `test_enqueue_failure_keeps_201`, which simulated a Redis
        outage and asserted the request still returned 201. That was a real
        guarantee, but it was *defensive*: it held because a try/except swallowed
        the failure, and the cost was three silently lost events per
        transaction.

        The outbox inverts it. The request path never opens a Redis connection,
        so there is no failure mode left to defend against — the guarantee is
        structural rather than a catch block. Publishing failures now happen in
        the relay, out of the request's way, and the event is still durable in
        the database.
        """
        mock_db.execute = AsyncMock(return_value=_empty_scalars_result())
        staged_mock = self._patch_scoring(monkeypatch, "fraud")

        # If the module still exposed publish_event, patching it would prove the
        # call site never reaches Redis. Under the outbox the stronger statement
        # is available and simpler: the symbol does not exist in the scoring
        # module at all, so there is nothing to call.
        assert not hasattr(transactions_api, "publish_event"), (
            "the scoring module must not publish to Redis directly; that is the "
            "outbox relay's job"
        )

        response = await self._post(test_client, auth_headers)

        assert response.status_code == 201
        # The event was staged instead, so it survives a Redis outage.
        assert any(
            call.args[1] == "fraud:shap" for call in staged_mock.call_args_list
        )
