"""Tests for the transaction service (CRUD with soft delete)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.transaction import Transaction, TransactionStatus
from src.services.transaction import (
    create_transaction,
    delete_transaction,
    get_transaction,
    list_transactions,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db():
    """Mock async database session."""
    db = AsyncMock(spec=AsyncSession)
    return db


class TestTransactionService:
    """Transaction CRUD service tests."""

    async def test_create_transaction(self, mock_db):
        """Creating a transaction should set pending status and timestamps."""
        mock_db.execute = AsyncMock(return_value=MagicMock())

        result = await create_transaction(
            db=mock_db,
            amount=1500.00,
            currency="USD",
            merchant_name="Amazon",
            merchant_category="ecommerce",
            card_last4="1234",
            user_id=uuid4(),
        )

        assert isinstance(result, Transaction)
        assert result.amount == 1500.00
        assert result.currency == "USD"
        assert result.merchant_name == "Amazon"
        assert result.status == TransactionStatus.PENDING
        assert result.deleted_at is None
        assert mock_db.add.called
        assert mock_db.flush.called

    async def test_get_transaction_found(self, mock_db):
        """Getting an existing transaction should return it."""
        transaction = MagicMock(spec=Transaction)
        transaction.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = transaction
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_transaction(mock_db, transaction.id)
        assert result is transaction

    async def test_get_transaction_not_found(self, mock_db):
        """Getting a non-existent transaction should return None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_transaction(mock_db, uuid4())
        assert result is None

    async def test_list_transactions_excludes_deleted(self, mock_db):
        """Listing transactions should exclude soft-deleted records."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        results = await list_transactions(mock_db)
        assert isinstance(results, list)

        # Verify the query includes deleted_at filter
        call_args = mock_db.execute.call_args[0][0]
        assert "deleted_at" in str(call_args)

    async def test_soft_delete_transaction(self, mock_db):
        """Soft deleting should set deleted_at timestamp."""
        transaction = MagicMock(spec=Transaction)
        transaction.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = transaction
        mock_db.execute = AsyncMock(return_value=mock_result)

        await delete_transaction(mock_db, uuid4())
        assert transaction.deleted_at is not None
        assert mock_db.flush.called
