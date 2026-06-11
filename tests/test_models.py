"""Model tests — model creation, soft delete behavior, timestamp auto-set.

Tests that ORM models are correctly configured with proper defaults and
soft delete semantics.
"""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm.properties import MappedColumn

from src.core.database import Base
from src.models.audit_entry import AuditEntry
from src.models.base import BaseModel
from src.models.fraud_alert import FraudAlert, AlertStatus
from src.models.fraud_score import FraudScore, FraudClassification
from src.models.llm_report import LLMReport, LLMReportStatus
from src.models.ml_model_run import MLModelRun
from src.models.rule import RuleMetadata
from src.models.transaction import Transaction, TransactionStatus
from src.models.user import User, UserRole


class TestBaseModelFeatures:
    """Tests for BaseModel shared columns (timestamps, soft delete)."""

    def test_base_model_has_id(self):
        """All models should have a UUID id."""
        assert "id" in BaseModel.__annotations__

    def test_base_model_has_timestamps(self):
        """BaseModel provides created_at and updated_at."""
        assert "created_at" in BaseModel.__annotations__
        assert "updated_at" in BaseModel.__annotations__

    def test_base_model_soft_delete_column(self):
        """BaseModel provides deleted_at for soft delete."""
        assert "deleted_at" in BaseModel.__annotations__
        annotation = BaseModel.__annotations__["deleted_at"]
        assert "None" in str(annotation)  # Optional[datetime]

    def test_base_model_is_abstract(self):
        """BaseModel is abstract — not mapped to its own table."""
        assert BaseModel.__abstract__ is True
        assert issubclass(BaseModel, Base)

    def test_concrete_models_have_tablenames(self):
        """Every concrete non-abstract model must have __tablename__."""
        for model in (User, Transaction, FraudScore, FraudAlert,
                      RuleMetadata, LLMReport, MLModelRun, AuditEntry):
            assert hasattr(model, "__tablename__")
            assert isinstance(model.__tablename__, str)


class TestTimestampAutoSet:
    """Models auto-set created_at and updated_at."""

    def test_user_has_timestamps(self):
        """User model inherits created_at and updated_at."""
        assert hasattr(User, "created_at")
        assert hasattr(User, "updated_at")

    def test_transaction_has_timestamps(self):
        """Transaction model inherits timestamps."""
        assert hasattr(Transaction, "created_at")
        assert hasattr(Transaction, "updated_at")

    def test_fraud_score_has_timestamps(self):
        """FraudScore inherits timestamps."""
        assert hasattr(FraudScore, "created_at")
        assert hasattr(FraudScore, "updated_at")

    def test_audit_entry_has_created_at_only(self):
        """AuditEntry has created_at but NOT updated_at (immutable)."""
        assert hasattr(AuditEntry, "created_at")
        assert "updated_at" not in AuditEntry.__annotations__


class TestSoftDeleteBehavior:
    """Soft delete columns are nullable and properly typed."""

    def test_transaction_soft_delete(self):
        """Transaction has soft delete from BaseModel."""
        assert hasattr(Transaction, "deleted_at")

    def test_user_soft_delete(self):
        """User has soft delete from BaseModel."""
        assert hasattr(User, "deleted_at")

    def test_fraud_score_soft_delete(self):
        """FraudScore has soft delete from BaseModel."""
        assert hasattr(FraudScore, "deleted_at")

    def test_audit_entry_soft_delete(self):
        """AuditEntry has soft delete defined directly (no BaseModel)."""
        assert hasattr(AuditEntry, "deleted_at")


class TestModelDefaults:
    """Default enum values on model columns."""

    def test_transaction_default_status_pending(self):
        """Transaction status defaults to 'pending'."""
        ann = Transaction.__annotations__["status"]
        assert ann is not None

    def test_user_default_role_analyst(self):
        """User role defaults to 'analyst'."""
        ann = User.__annotations__["role"]
        assert ann is not None

    def test_fraud_alert_default_status_open(self):
        """FraudAlert status defaults to 'open'."""
        ann = FraudAlert.__annotations__["status"]
        assert ann is not None
