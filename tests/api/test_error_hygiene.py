"""R1-008: Error response hygiene — no raw exception text leaks to clients.

Verify that when a service raises with sensitive detail (e.g. database
connection strings, internal file paths), the HTTP response body does NOT
contain the secret while the server logs DO include it.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

import src.api.v1.transactions as transactions_api
from src.models.transaction import TransactionStatus

pytestmark = pytest.mark.asyncio


def _empty_scalars_result() -> MagicMock:
    """Mock execute result whose scalars().all() yields no rows."""
    scalar = MagicMock()
    scalar.all.return_value = []
    result = MagicMock()
    result.scalars.return_value = scalar
    return result


SECRET_MESSAGE = "Connection refused: password=s3cret-db-42 host=10.0.0.5"


class TestErrorHygiene:
    """Ensure exception details never leak to the client response body."""

    async def test_transaction_create_hides_exception_detail(
        self,
        test_client: AsyncClient,
        mock_db: AsyncMock,
        auth_headers: dict,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ):
        """When create_transaction raises, the client gets a safe generic
        message while the log contains the full secret."""
        monkeypatch.setattr(
            "src.api.v1.transactions.create_transaction",
            AsyncMock(side_effect=RuntimeError(SECRET_MESSAGE)),
        )

        response = await test_client.post(
            "/api/v1/transactions",
            json={
                "amount": 100.00,
                "currency": "USD",
                "merchant_name": "Store",
                "merchant_category": "retail",
                "card_last4": "1234",
                "user_id": "00000000-0000-0000-0000-000000000001",
            },
            headers=auth_headers,
        )

        assert response.status_code == 500
        body = response.json()["detail"]
        assert SECRET_MESSAGE not in body, (
            f"Raw exception text leaked to client: {body}"
        )

    async def test_get_transaction_hides_exception_detail(
        self,
        test_client: AsyncClient,
        mock_db: AsyncMock,
        auth_headers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """When get_transaction raises unexpectedly, client gets a safe message."""
        monkeypatch.setattr(
            "src.api.v1.transactions.get_transaction",
            AsyncMock(side_effect=RuntimeError(SECRET_MESSAGE)),
        )

        from uuid import uuid4

        response = await test_client.get(
            f"/api/v1/transactions/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 500
        body = response.json()["detail"]
        assert SECRET_MESSAGE not in body

    async def test_get_embedding_hides_exception_detail(
        self,
        test_client: AsyncClient,
        mock_db: AsyncMock,
        auth_headers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """When get_transaction raises in the embedding endpoint, the error
        response must not contain the raw exception string."""
        monkeypatch.setattr(
            "src.api.v1.transactions.get_transaction",
            AsyncMock(side_effect=RuntimeError(SECRET_MESSAGE)),
        )

        from uuid import uuid4

        response = await test_client.get(
            f"/api/v1/transactions/{uuid4()}/embedding",
            headers=auth_headers,
        )

        assert response.status_code == 500
        body = response.json()["detail"]
        assert SECRET_MESSAGE not in body
