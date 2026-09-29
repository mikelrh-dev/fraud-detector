"""Tests for the transaction service (CRUD with soft delete)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fraud_score import FraudScore
from src.models.transaction import Transaction, TransactionStatus
from src.services.transaction import (
    create_transaction,
    delete_transaction,
    get_scores_for_transactions,
    get_transaction,
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


class TestGetScoresForTransactions:
    """get_scores_for_transactions batch helper tests."""

    def _make_score(self, transaction_id, created_at):
        score = MagicMock(spec=FraudScore)
        score.transaction_id = transaction_id
        score.created_at = created_at
        return score

    async def test_empty_ids_returns_empty_without_sql(self, mock_db):
        """Empty id list should return {} and never touch the DB."""
        mock_db.execute = AsyncMock()

        result = await get_scores_for_transactions(mock_db, [])

        assert result == {}
        mock_db.execute.assert_not_called()

    async def test_batch_returns_all_scores_from_single_query(self, mock_db):
        """A batch of ids should return a score per id from one query."""
        id_a, id_b = uuid4(), uuid4()
        now = datetime.now(tz=timezone.utc)
        score_a = self._make_score(id_a, now)
        score_b = self._make_score(id_b, now - timedelta(minutes=1))

        mock_scalar_result = MagicMock()
        mock_scalar_result.all.return_value = [score_a, score_b]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalar_result
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_scores_for_transactions(mock_db, [id_a, id_b])

        assert result == {id_a: score_a, id_b: score_b}
        assert mock_db.execute.call_count == 1

        # The query must use a single IN clause over the batch
        query_str = str(mock_db.execute.call_args[0][0])
        assert "fraud_scores" in query_str
        assert "IN" in query_str
        assert "ORDER BY" in query_str

    async def test_duplicate_transaction_keeps_newest(self, mock_db):
        """When a transaction has multiple score rows, the newest wins."""
        txn_id = uuid4()
        now = datetime.now(tz=timezone.utc)
        newer = self._make_score(txn_id, now)
        older = self._make_score(txn_id, now - timedelta(hours=2))

        # DB returns newest first (ORDER BY created_at DESC)
        mock_scalar_result = MagicMock()
        mock_scalar_result.all.return_value = [newer, older]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalar_result
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_scores_for_transactions(mock_db, [txn_id])

        assert result == {txn_id: newer}
