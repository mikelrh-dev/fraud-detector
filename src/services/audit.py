"""Audit service — immutable audit trail with SHA-256 checksums.

Records every scoring event, LLM report generation, and analyst action
in an append-only audit trail with integrity verification via checksums.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from src.models.audit_entry import AuditEntry

logger = logging.getLogger(__name__)


class AuditService:
    """Creates and queries immutable audit trail entries.

    Each entry includes a SHA-256 checksum of its content for tamper
    detection. Entries are append-only — they are never modified.
    """

    async def create_entry(
        self,
        db: Any,
        action_type: str,
        transaction_id: Any = None,
        user_id: Any = None,
        previous_status: str | None = None,
        new_status: str | None = None,
        details: dict[str, Any] | None = None,
        _entry_instance: Any = None,
    ) -> Any:
        """Create a new audit trail entry with SHA-256 checksum.

        Args:
            db: Async database session.
            action_type: Type of action (e.g. 'transaction_scored',
                'report_generated', 'review', 'false_positive').
            transaction_id: Optional transaction UUID.
            user_id: Optional user UUID who performed the action.
            previous_status: Optional previous status value.
            new_status: Optional new status value.
            details: Optional dict with additional context.
            _entry_instance: Optional injected instance for testing.

        Returns:
            The created AuditEntry instance.
        """
        entry_data = self._build_entry_data(
            action_type=action_type,
            transaction_id=str(transaction_id) if transaction_id else None,
            user_id=str(user_id) if user_id else None,
            previous_status=previous_status,
            new_status=new_status,
            details=details,
        )
        checksum = self._compute_checksum(entry_data)

        entry = _entry_instance or AuditEntry(
            action_type=action_type,
            transaction_id=transaction_id,
            user_id=user_id,
            previous_status=previous_status,
            new_status=new_status,
            details=details,
            sha256_checksum=checksum,
        )
        if _entry_instance is not None:
            entry.action_type = action_type
            entry.transaction_id = transaction_id
            entry.user_id = user_id
            entry.previous_status = previous_status
            entry.new_status = new_status
            entry.details = details
            entry.sha256_checksum = checksum

        db.add(entry)
        await db.flush()
        return entry

    def _build_entry_data(
        self,
        action_type: str,
        transaction_id: str | None = None,
        user_id: str | None = None,
        previous_status: str | None = None,
        new_status: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the canonical dict for checksum computation.

        Returns a dict with sorted keys for deterministic checksums.
        """
        data: dict[str, Any] = {
            "action_type": action_type,
        }
        if transaction_id is not None:
            data["transaction_id"] = transaction_id
        if user_id is not None:
            data["user_id"] = user_id
        if previous_status is not None:
            data["previous_status"] = previous_status
        if new_status is not None:
            data["new_status"] = new_status
        if details is not None:
            data["details"] = details
        return data

    def _compute_checksum(self, entry_data: dict[str, Any]) -> str:
        """Compute a SHA-256 checksum of the entry data.

        The data is serialized as sorted JSON for deterministic output
        regardless of key ordering.

        Args:
            entry_data: Dict containing the entry content to checksum.

        Returns:
            SHA-256 hex digest string (64 characters).
        """
        serialized = json.dumps(entry_data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def get_entries_for_transaction(
        self,
        db: Any,
        transaction_id: Any,
    ) -> list[Any]:
        """Retrieve all audit entries for a specific transaction.

        Args:
            db: Async database session.
            transaction_id: Transaction UUID to filter by.

        Returns:
            List of AuditEntry instances in chronological order.
        """
        result = await db.execute(
            select(AuditEntry)
            .where(AuditEntry.transaction_id == transaction_id)
            .order_by(AuditEntry.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_entries_for_analyst(
        self,
        db: Any,
        user_id: Any,
    ) -> list[Any]:
        """Retrieve all audit entries for a specific analyst.

        Args:
            db: Async database session.
            user_id: User UUID to filter by.

        Returns:
            List of AuditEntry instances in chronological order.
        """
        result = await db.execute(
            select(AuditEntry)
            .where(AuditEntry.user_id == user_id)
            .order_by(AuditEntry.created_at.asc())
        )
        return list(result.scalars().all())

    async def export(
        self,
        db: Any,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Any]:
        """Export audit entries within a date range.

        Args:
            db: Async database session.
            start_date: Start of date range (inclusive).
            end_date: End of date range (inclusive).

        Returns:
            List of AuditEntry instances in the date range.
        """
        result = await db.execute(
            select(AuditEntry)
            .where(AuditEntry.created_at >= start_date)
            .where(AuditEntry.created_at <= end_date)
            .order_by(AuditEntry.created_at.asc())
        )
        return list(result.scalars().all())
