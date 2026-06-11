"""Transaction service — CRUD operations with soft delete."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.transaction import Transaction, TransactionStatus


async def create_transaction(
    db: AsyncSession,
    amount: float,
    currency: str,
    merchant_name: str,
    merchant_category: str | None,
    card_last4: str,
    user_id: UUID,
) -> Transaction:
    """Create a new transaction with 'pending' status."""
    transaction = Transaction(
        id=uuid4(),
        amount=amount,
        currency=currency,
        merchant_name=merchant_name,
        merchant_category=merchant_category,
        card_last4=card_last4,
        status=TransactionStatus.PENDING,
        user_id=user_id,
    )
    db.add(transaction)
    await db.flush()
    return transaction


async def get_transaction(db: AsyncSession, transaction_id: UUID) -> Transaction | None:
    """Retrieve a transaction by ID (includes soft-deleted)."""
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    return result.scalar_one_or_none()


async def list_transactions(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[Transaction]:
    """List transactions excluding soft-deleted ones."""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.deleted_at.is_(None))
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def delete_transaction(db: AsyncSession, transaction_id: UUID) -> Transaction | None:
    """Soft-delete a transaction by setting its deleted_at timestamp."""
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    transaction = result.scalar_one_or_none()
    if transaction is not None:
        transaction.deleted_at = datetime.now(tz=timezone.utc)
        await db.flush()
    return transaction
