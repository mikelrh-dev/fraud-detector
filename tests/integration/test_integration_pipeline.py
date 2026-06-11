"""End-to-end integration test: POST transaction → verify score → verify alert → verify audit chain.

Tests the full scoring pipeline and audit trail integration using mocked
database dependencies.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.dependencies import get_db
from src.schemas.alert import AlertActionRequest
from src.schemas.transaction import TransactionCreate


class TestFullScoringPipeline:
    """Full pipeline: transaction creation, scoring, alert, audit."""

    @pytest.mark.asyncio
    async def test_scoring_pipeline_with_audit_trail(
        self,
        test_client: AsyncClient,
        auth_headers: dict,
        mock_db: AsyncMock,
    ):
        """POST transaction → score → alert → audit entries created."""
        # We use the test_client fixture which already overrides get_db with mock_db.
        # The transaction API calls create_transaction which calls db.add + db.flush.
        # We need mock_db to handle execute calls for unique email/user checks.

        # Configure mocks for transaction creation and listing
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing tx found
        mock_result.all.return_value = []  # Empty list for queries
        mock_result.scalar.return_value = 0  # Count queries return 0
        mock_result.scalars.return_value.all.return_value = []

        def mock_execute_side_effect(*args, **kwargs):
            return mock_result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        # POST a transaction that will trigger fraud scoring
        payload = {
            "amount": 50000.0,
            "currency": "USD",
            "merchant_name": "Suspicious Electronics",
            "merchant_category": "electronics",
            "card_last4": "9999",
            "user_id": "00000000-0000-0000-0000-000000000001",
        }

        # When create_transaction adds a Transaction, capture it
        added_objects = []

        def mock_add(obj):
            added_objects.append(obj)

        mock_db.add = mock_add
        mock_db.flush = AsyncMock()

        response = await test_client.post(
            "/api/v1/transactions",
            headers=auth_headers,
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert "transaction_id" in data
        assert "rule_score" in data
        assert "ensemble_score" in data
        assert "classification" in data
        assert "fired_rules" in data

        # Verify audit entries were created
        audit_entries = [obj for obj in added_objects if type(obj).__name__ == "AuditEntry"]
        assert len(audit_entries) >= 1
        entry = audit_entries[0]
        assert entry.action_type == "transaction_scored"
        assert entry.sha256_checksum is not None

    @pytest.mark.asyncio
    async def test_analyst_action_creates_audit_entry(
        self,
        test_client: AsyncClient,
        auth_headers: dict,
        mock_db: AsyncMock,
    ):
        """Analyst action on an alert should create an audit trail entry."""
        # Mock: alert exists
        mock_alert = MagicMock()
        mock_alert.id = "11111111-1111-1111-1111-111111111111"
        mock_alert.transaction_id = "22222222-2222-2222-2222-222222222222"
        mock_alert.status = MagicMock()
        mock_alert.status.value = "open"
        mock_alert.score = 85.0
        mock_alert.threshold = 70.0
        mock_alert.classification = "fraud"
        mock_alert.reviewed_by = None
        mock_alert.reviewed_at = None
        mock_alert.created_at = MagicMock()

        # Configure execute to find the alert
        mock_find_result = MagicMock()
        mock_find_result.scalar_one_or_none.return_value = mock_alert
        mock_find_result.all.return_value = []
        mock_find_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(return_value=mock_find_result)

        # Track added objects
        added_objects = []

        def mock_add(obj):
            added_objects.append(obj)

        mock_db.add = mock_add
        mock_db.flush = AsyncMock()

        # Perform a review action
        response = await test_client.post(
            "/api/v1/alerts/11111111-1111-1111-1111-111111111111/review",
            headers=auth_headers,
            json={"action": "review", "reason": "Reviewed as legitimate"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reviewed"

        # Verify audit entry was created
        audit_entries = [obj for obj in added_objects if type(obj).__name__ == "AuditEntry"]
        assert len(audit_entries) >= 1
        entry = audit_entries[0]
        assert entry.action_type == "review"
        assert entry.user_id is not None
        assert entry.previous_status == "open"
        assert entry.new_status == "reviewed"

    @pytest.mark.asyncio
    async def test_false_positive_creates_audit_entry(
        self,
        test_client: AsyncClient,
        auth_headers: dict,
        mock_db: AsyncMock,
    ):
        """False positive marking should create an audit trail entry."""
        mock_alert = MagicMock()
        mock_alert.id = "33333333-3333-3333-3333-333333333333"
        mock_alert.transaction_id = "44444444-4444-4444-4444-444444444444"
        mock_alert.status = MagicMock()
        mock_alert.status.value = "open"
        mock_alert.score = 85.0
        mock_alert.threshold = 70.0
        mock_alert.classification = "fraud"
        mock_alert.reviewed_by = None
        mock_alert.reviewed_at = None
        mock_alert.created_at = MagicMock()

        mock_find_result = MagicMock()
        mock_find_result.scalar_one_or_none.return_value = mock_alert
        mock_find_result.all.return_value = []

        mock_db.execute = AsyncMock(return_value=mock_find_result)

        added_objects = []
        mock_db.add = lambda obj: added_objects.append(obj)
        mock_db.flush = AsyncMock()

        response = await test_client.post(
            "/api/v1/alerts/33333333-3333-3333-3333-333333333333/false-positive",
            headers=auth_headers,
            json={"action": "false_positive", "reason": "Legitimate transaction"},
        )

        assert response.status_code == 200

        audit_entries = [obj for obj in added_objects if type(obj).__name__ == "AuditEntry"]
        assert len(audit_entries) >= 1
        entry = audit_entries[0]
        assert entry.action_type == "false_positive"
        assert entry.previous_status == "open"
        assert entry.new_status == "resolved"

    @pytest.mark.asyncio
    async def test_revert_creates_audit_entry(
        self,
        test_client: AsyncClient,
        auth_headers: dict,
        mock_db: AsyncMock,
    ):
        """Revert action should create an audit trail entry."""
        mock_alert = MagicMock()
        mock_alert.id = "55555555-5555-5555-5555-555555555555"
        mock_alert.transaction_id = "66666666-6666-6666-6666-666666666666"
        mock_alert.status = MagicMock()
        mock_alert.status.value = "reviewed"
        mock_alert.score = 85.0
        mock_alert.threshold = 70.0
        mock_alert.classification = "fraud"
        mock_alert.reviewed_by = None
        mock_alert.reviewed_at = None
        mock_alert.created_at = MagicMock()

        mock_find_result = MagicMock()
        mock_find_result.scalar_one_or_none.return_value = mock_alert

        mock_db.execute = AsyncMock(return_value=mock_find_result)

        added_objects = []
        mock_db.add = lambda obj: added_objects.append(obj)
        mock_db.flush = AsyncMock()

        response = await test_client.post(
            "/api/v1/alerts/55555555-5555-5555-5555-555555555555/revert",
            headers=auth_headers,
            json={"action": "revert", "reason": "Needs further review"},
        )

        assert response.status_code == 200

        audit_entries = [obj for obj in added_objects if type(obj).__name__ == "AuditEntry"]
        assert len(audit_entries) >= 1
        entry = audit_entries[0]
        assert entry.action_type == "revert"
        assert entry.previous_status == "reviewed"
        assert entry.new_status == "open"

    @pytest.mark.asyncio
    async def test_scoring_pipeline_audit_trail_has_checksum(
        self,
        test_client: AsyncClient,
        auth_headers: dict,
        mock_db: AsyncMock,
    ):
        """Audit entries from scoring pipeline should have valid SHA-256 checksums."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        added_objects = []
        mock_db.add = lambda obj: added_objects.append(obj)
        mock_db.flush = AsyncMock()

        payload = {
            "amount": 100000.0,
            "currency": "USD",
            "merchant_name": "High Risk Store",
            "merchant_category": "retail",
            "card_last4": "0000",
            "user_id": "00000000-0000-0000-0000-000000000001",
        }

        response = await test_client.post(
            "/api/v1/transactions",
            headers=auth_headers,
            json=payload,
        )

        assert response.status_code == 201

        audit_entries = [obj for obj in added_objects if type(obj).__name__ == "AuditEntry"]
        assert len(audit_entries) >= 1
        entry = audit_entries[0]
        assert len(entry.sha256_checksum) == 64
        # Verify it's valid hex
        int(entry.sha256_checksum, 16)
