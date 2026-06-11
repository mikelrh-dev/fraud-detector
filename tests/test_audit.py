"""Audit service tests — checksum consistency, immutability, querying, export.

Tests for the audit trail service that records every scoring and analyst action
with SHA-256 checksums for integrity verification.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from src.services.audit import AuditService


class TestChecksumComputation:
    """SHA-256 checksum computation — consistency and determinism."""

    def test_compute_checksum_returns_hex_string(self):
        """_compute_checksum should return a 64-char hex string."""
        service = AuditService()
        data = {"action_type": "test", "transaction_id": "abc-123"}
        checksum = service._compute_checksum(data)
        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA-256 hex length
        int(checksum, 16)  # Should be valid hex

    def test_same_input_same_checksum(self):
        """Same input data should always produce the same checksum."""
        service = AuditService()
        data = {"action_type": "transaction_scored", "score": 85.5, "rules": ["high_amount"]}
        c1 = service._compute_checksum(data)
        c2 = service._compute_checksum(data)
        assert c1 == c2

    def test_different_input_different_checksum(self):
        """Different input data should produce different checksums."""
        service = AuditService()
        c1 = service._compute_checksum({"action_type": "transaction_scored"})
        c2 = service._compute_checksum({"action_type": "report_generated"})
        assert c1 != c2

    def test_checksum_changes_with_details(self):
        """Adding details should change the checksum."""
        service = AuditService()
        base = {"action_type": "transaction_scored"}
        with_details = {"action_type": "transaction_scored", "details": {"score": 85}}
        assert service._compute_checksum(base) != service._compute_checksum(with_details)

    def test_checksum_deterministic_key_order(self):
        """Checksum should be deterministic regardless of key order."""
        service = AuditService()
        data1 = {"action_type": "test", "score": 50, "rules": ["a", "b"]}
        data2 = {"rules": ["a", "b"], "score": 50, "action_type": "test"}
        assert service._compute_checksum(data1) == service._compute_checksum(data2)

    def test_checksum_with_none_values(self):
        """None values should be handled consistently."""
        service = AuditService()
        data = {"action_type": "test", "transaction_id": None, "details": None}
        checksum = service._compute_checksum(data)
        assert len(checksum) == 64

    def test_checksum_with_complex_nested_data(self):
        """Nested dicts and lists should produce consistent checksums."""
        service = AuditService()
        data = {
            "action_type": "transaction_scored",
            "details": {
                "rule_score": 60,
                "ml_score": 80,
                "ensemble_score": 72,
                "fired_rules": ["high_amount", "high_velocity"],
                "classification": "fraud",
                "threshold": 70,
            },
        }
        checksum = service._compute_checksum(data)
        assert len(checksum) == 64


class TestCreateEntry:
    """Audit entry creation — persistence and checksum generation."""

    @pytest.mark.asyncio
    async def test_create_entry_adds_to_db(self):
        """create_entry should add an AuditEntry and flush."""
        service = AuditService()
        mock_db = AsyncMock()

        class FakeEntry:
            def __init__(self):
                self.id = "entry-uuid"
                self.created_at = datetime.now(tz=timezone.utc)
                self.action_type = None
                self.transaction_id = None
                self.user_id = None
                self.previous_status = None
                self.new_status = None
                self.details = None
                self.sha256_checksum = None

        entry = await service.create_entry(
            db=mock_db,
            action_type="transaction_scored",
            transaction_id="tx-uuid-123",
            user_id="user-uuid-456",
            details={"score": 85},
            _entry_instance=FakeEntry(),
        )

        assert entry.action_type == "transaction_scored"
        assert entry.transaction_id == "tx-uuid-123"
        assert entry.user_id == "user-uuid-456"
        assert entry.details == {"score": 85}
        assert entry.sha256_checksum is not None
        assert len(entry.sha256_checksum) == 64
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_entry_with_previous_and_new_status(self):
        """create_entry should record status transitions."""
        service = AuditService()
        mock_db = AsyncMock()

        class FakeEntry:
            def __init__(self):
                self.id = "entry-uuid-2"
                self.created_at = datetime.now(tz=timezone.utc)
                self.action_type = None
                self.transaction_id = None
                self.user_id = None
                self.previous_status = None
                self.new_status = None
                self.details = None
                self.sha256_checksum = None

        entry = await service.create_entry(
            db=mock_db,
            action_type="review",
            transaction_id="tx-uuid",
            user_id="analyst-uuid",
            previous_status="open",
            new_status="reviewed",
            details={"reason": "Reviewed manually"},
            _entry_instance=FakeEntry(),
        )

        assert entry.previous_status == "open"
        assert entry.new_status == "reviewed"
        assert entry.action_type == "review"

    @pytest.mark.asyncio
    async def test_create_entry_checksum_verifiable(self):
        """The checksum should be verifiable against the entry data."""
        service = AuditService()
        mock_db = AsyncMock()

        class FakeEntry:
            def __init__(self):
                self.id = "entry-uuid-3"
                self.created_at = datetime.now(tz=timezone.utc)
                self.action_type = None
                self.transaction_id = None
                self.user_id = None
                self.previous_status = None
                self.new_status = None
                self.details = None
                self.sha256_checksum = None

        entry = await service.create_entry(
            db=mock_db,
            action_type="report_generated",
            transaction_id="tx-uuid",
            details={"model": "llama3.2:3b", "generation_time_ms": 1500},
            _entry_instance=FakeEntry(),
        )

        # Recompute checksum from the entry data to verify
        entry_data = service._build_entry_data(
            action_type="report_generated",
            transaction_id="tx-uuid",
            user_id=None,
            previous_status=None,
            new_status=None,
            details={"model": "llama3.2:3b", "generation_time_ms": 1500},
        )
        expected_checksum = service._compute_checksum(entry_data)
        assert entry.sha256_checksum == expected_checksum


class TestQueryByTransaction:
    """Query audit entries by transaction ID."""

    @pytest.mark.asyncio
    async def test_get_entries_for_transaction(self):
        """get_entries_for_transaction should return filtered entries."""
        service = AuditService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_entry_1 = MagicMock()
        mock_entry_1.action_type = "transaction_scored"
        mock_entry_2 = MagicMock()
        mock_entry_2.action_type = "report_generated"
        mock_result.scalars.return_value.all.return_value = [mock_entry_1, mock_entry_2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        entries = await service.get_entries_for_transaction(
            db=mock_db,
            transaction_id="tx-uuid-123",
        )

        assert len(entries) == 2
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_entries_for_transaction_empty(self):
        """No entries should return empty list."""
        service = AuditService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        entries = await service.get_entries_for_transaction(
            db=mock_db,
            transaction_id="nonexistent-uuid",
        )

        assert entries == []


class TestQueryByAnalyst:
    """Query audit entries by analyst user ID."""

    @pytest.mark.asyncio
    async def test_get_entries_for_analyst(self):
        """get_entries_for_analyst should return analyst's action entries."""
        service = AuditService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_entry = MagicMock()
        mock_entry.action_type = "false_positive"
        mock_entry.user_id = "analyst-uuid"
        mock_result.scalars.return_value.all.return_value = [mock_entry]
        mock_db.execute = AsyncMock(return_value=mock_result)

        entries = await service.get_entries_for_analyst(
            db=mock_db,
            user_id="analyst-uuid",
        )

        assert len(entries) == 1
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_entries_for_analyst_empty(self):
        """No entries for an analyst should return empty list."""
        service = AuditService()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        entries = await service.get_entries_for_analyst(
            db=mock_db,
            user_id="analyst-with-no-actions",
        )

        assert entries == []


class TestExport:
    """Audit trail export — date range filtering."""

    @pytest.mark.asyncio
    async def test_export_returns_entries_in_date_range(self):
        """export should return entries filtered by date range."""
        service = AuditService()
        mock_db = AsyncMock()

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 12, 31, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_entry = MagicMock()
        mock_entry.created_at = datetime(2024, 6, 15, tzinfo=timezone.utc)
        mock_result.scalars.return_value.all.return_value = [mock_entry]
        mock_db.execute = AsyncMock(return_value=mock_result)

        entries = await service.export(
            db=mock_db,
            start_date=start,
            end_date=end,
        )

        assert len(entries) == 1

    @pytest.mark.asyncio
    async def test_export_empty_range(self):
        """No entries in date range should return empty list."""
        service = AuditService()
        mock_db = AsyncMock()

        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        end = datetime(2023, 1, 2, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        entries = await service.export(
            db=mock_db,
            start_date=start,
            end_date=end,
        )

        assert entries == []
