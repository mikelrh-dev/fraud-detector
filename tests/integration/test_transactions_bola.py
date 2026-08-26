"""BOLA (object-level authorization) tests — R1-003 (audit wave 2).

An authenticated analyst must only access their own transactions; admins
may access everything. Foreign objects are reported as 404 to avoid
leaking existence.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

OTHER_USER_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
FOREIGN_TXN_ID = uuid.UUID("88888888-8888-8888-8888-888888888888")


def _db_result(rows=None, scalar=None):
    """Build a mock SQLAlchemy result."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = rows or []
    result.scalar_one_or_none.return_value = scalar
    return result


def _foreign_transaction() -> MagicMock:
    txn = MagicMock()
    txn.id = FOREIGN_TXN_ID
    txn.user_id = OTHER_USER_ID
    txn.amount = Decimal("10.00")
    txn.currency = "USD"
    txn.merchant_name = "Foreign Merchant"
    txn.merchant_category = "grocery"
    txn.card_last4 = "4242"
    status = MagicMock()
    status.value = "completed"
    txn.status = status
    txn.created_at = datetime.now(tz=timezone.utc)
    txn.updated_at = datetime.now(tz=timezone.utc)
    return txn


class TestListTransactionsOwnership:
    """GET /transactions must scope non-admins to their own data."""

    async def test_analyst_cannot_list_other_user_transactions(
        self, test_client: AsyncClient, auth_headers: dict
    ):
        response = await test_client.get(
            "/api/v1/transactions",
            params={"user_id": str(OTHER_USER_ID)},
            headers=auth_headers,
        )
        assert response.status_code == 403

    async def test_admin_can_list_any_user_transactions(
        self, test_client: AsyncClient, admin_headers: dict, mock_db
    ):
        mock_db.execute = AsyncMock(
            side_effect=[_db_result(rows=[]), _db_result(rows=[])]
        )
        response = await test_client.get(
            "/api/v1/transactions",
            params={"user_id": str(OTHER_USER_ID)},
            headers=admin_headers,
        )
        assert response.status_code == 200


class TestTransactionDetailOwnership:
    """GET /transactions/{id} must hide foreign transactions from analysts."""

    async def test_analyst_gets_404_for_foreign_transaction(
        self, test_client: AsyncClient, auth_headers: dict, mock_db
    ):
        mock_db.execute = AsyncMock(
            side_effect=[_db_result(scalar=_foreign_transaction()), _db_result(rows=[])]
        )
        response = await test_client.get(
            f"/api/v1/transactions/{FOREIGN_TXN_ID}", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_admin_can_read_any_transaction(
        self, test_client: AsyncClient, admin_headers: dict, mock_db
    ):
        mock_db.execute = AsyncMock(
            side_effect=[_db_result(scalar=_foreign_transaction()), _db_result(rows=[])]
        )
        response = await test_client.get(
            f"/api/v1/transactions/{FOREIGN_TXN_ID}", headers=admin_headers
        )
        assert response.status_code == 200


class TestEmbeddingAnalysisOwnership:
    """GET /transactions/{id}/embedding must check transaction ownership."""

    async def test_analyst_gets_404_for_foreign_embedding(
        self, test_client: AsyncClient, auth_headers: dict, mock_db
    ):
        mock_db.execute = AsyncMock(
            side_effect=[_db_result(scalar=_foreign_transaction())]
        )
        response = await test_client.get(
            f"/api/v1/transactions/{FOREIGN_TXN_ID}/embedding", headers=auth_headers
        )
        assert response.status_code == 404


class TestGraphFeaturesOwnership:
    """GET /transactions/{user_id}/graph-features must be owner-or-admin."""

    async def test_analyst_cannot_view_other_user_graph_features(
        self, test_client: AsyncClient, auth_headers: dict
    ):
        response = await test_client.get(
            f"/api/v1/transactions/{OTHER_USER_ID}/graph-features",
            headers=auth_headers,
        )
        assert response.status_code == 403

    async def test_analyst_can_view_own_graph_features(
        self, test_client: AsyncClient, auth_headers: dict
    ):
        own_id = "00000000-0000-0000-0000-000000000001"
        with patch("src.api.v1.transactions._graph_service") as graph_service:
            # get_graph_features is now sync (called via asyncio.to_thread)
            graph_service.get_graph_features = MagicMock(
                return_value={"is_near_fraud": False}
            )
            response = await test_client.get(
                f"/api/v1/transactions/{own_id}/graph-features",
                headers=auth_headers,
            )
        assert response.status_code == 200
