"""Transaction API integration tests — CRUD, scoring pipeline, soft delete, auth.

Uses the test client with mocked DB and Redis dependencies.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.models.transaction import Transaction, TransactionStatus
from src.services.transaction import create_transaction

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


class TestCreateTransaction:
    """POST /api/v1/transactions."""

    async def test_create_transaction_returns_score(self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict):
        """Creating a valid transaction should return 201 with scoring breakdown."""
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
        """Existing transaction should return 200 with details."""
        txn = _make_mock_transaction()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = txn
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await test_client.get(
            f"/api/v1/transactions/{txn.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["merchant_name"] == "Test Store"
        assert data["currency"] == "USD"

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
        """List should return paginated results."""
        txn = _make_mock_transaction()

        # Mock the result for list query (scalars().all())
        mock_scalar_result = MagicMock()
        mock_scalar_result.all.return_value = [txn]

        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value = mock_scalar_result

        # Mock the count query
        mock_count_result = MagicMock()
        mock_count_result.all.return_value = [(txn.id,)]

        mock_db.execute = AsyncMock()
        # First call returns count, second returns list
        mock_db.execute.side_effect = [mock_count_result, mock_select_result]

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
