"""Tests for all ORM models."""

from sqlalchemy.orm.properties import MappedColumn

from src.core.database import Base
from src.models.base import BaseModel
from src.models.user import User
from src.models.transaction import Transaction
from src.models.fraud_score import FraudScore
from src.models.fraud_alert import FraudAlert
from src.models.rule import RuleMetadata
from src.models.llm_report import LLMReport
from src.models.ml_model_run import MLModelRun
from src.models.audit_entry import AuditEntry


# ── Base Model ───────────────────────────────────────────────────────────────

def test_base_model_is_abstract():
    """BaseModel should be abstract (not mapped to a table directly)."""
    assert BaseModel.__abstract__ is True
    assert issubclass(BaseModel, Base)


def test_base_model_has_expected_columns():
    """BaseModel should declare id, created_at, updated_at, deleted_at columns."""
    for col in ("id", "created_at", "updated_at", "deleted_at"):
        assert col in BaseModel.__annotations__


def test_base_model_columns_exist_as_attributes():
    """Each column should be accessible as a MappedColumn descriptor."""
    for col_name in ("id", "created_at", "updated_at", "deleted_at"):
        attr = getattr(BaseModel, col_name)
        assert isinstance(attr, MappedColumn), f"{col_name} is not a MappedColumn"


def test_deleted_at_type_allows_none():
    """deleted_at type annotation should be Mapped[datetime | None] for soft delete."""
    annotation = BaseModel.__annotations__["deleted_at"]
    assert "None" in str(annotation)


# ── User Model ───────────────────────────────────────────────────────────────

def test_user_model():
    """User model should have expected columns."""
    assert issubclass(User, BaseModel)
    assert User.__tablename__ == "users"
    for col in ("username", "email", "hashed_password", "role", "is_active"):
        assert col in User.__annotations__


# ── Transaction Model ────────────────────────────────────────────────────────

def test_transaction_model():
    """Transaction model should have expected columns."""
    assert issubclass(Transaction, BaseModel)
    assert Transaction.__tablename__ == "transactions"
    for col in ("amount", "currency", "merchant_name", "merchant_category",
                "card_last4", "status", "user_id"):
        assert col in Transaction.__annotations__


def test_transaction_has_soft_delete():
    """Transaction should inherit soft delete from BaseModel."""
    assert hasattr(Transaction, "deleted_at")


# ── FraudScore Model ─────────────────────────────────────────────────────────

def test_fraud_score_model():
    """FraudScore model should have expected columns."""
    assert issubclass(FraudScore, BaseModel)
    assert FraudScore.__tablename__ == "fraud_scores"
    for col in ("transaction_id", "rule_score", "ml_score",
                "ensemble_score", "threshold", "classification"):
        assert col in FraudScore.__annotations__


# ── FraudAlert Model ─────────────────────────────────────────────────────────

def test_fraud_alert_model():
    """FraudAlert model should have expected columns."""
    assert issubclass(FraudAlert, BaseModel)
    assert FraudAlert.__tablename__ == "fraud_alerts"
    for col in ("transaction_id", "status", "score", "threshold",
                "classification", "reviewed_by", "reviewed_at"):
        assert col in FraudAlert.__annotations__


# ── RuleMetadata Model ───────────────────────────────────────────────────────

def test_rule_metadata_model():
    """RuleMetadata model should have expected columns."""
    assert issubclass(RuleMetadata, BaseModel)
    assert RuleMetadata.__tablename__ == "rule_metadata"
    for col in ("name", "weight", "description", "is_active"):
        assert col in RuleMetadata.__annotations__


# ── LLMReport Model ──────────────────────────────────────────────────────────

def test_llm_report_model():
    """LLMReport model should have expected columns."""
    assert issubclass(LLMReport, BaseModel)
    assert LLMReport.__tablename__ == "llm_reports"
    for col in ("transaction_id", "report_text", "model_name",
                "status", "generation_time_ms", "retry_count"):
        assert col in LLMReport.__annotations__


# ── MLModelRun Model ─────────────────────────────────────────────────────────

def test_ml_model_run_model():
    """MLModelRun model should have expected columns."""
    assert issubclass(MLModelRun, BaseModel)
    assert MLModelRun.__tablename__ == "ml_model_runs"
    for col in ("model_version", "metrics", "status",
                "drift_detected"):
        assert col in MLModelRun.__annotations__


# ── AuditEntry Model ─────────────────────────────────────────────────────────

def test_audit_entry_model():
    """AuditEntry model should have expected columns (immutable, no updated_at)."""
    assert issubclass(AuditEntry, Base)
    assert AuditEntry.__tablename__ == "audit_entries"
    for col in ("transaction_id", "user_id", "action_type",
                "previous_status", "new_status", "details",
                "sha256_checksum"):
        assert col in AuditEntry.__annotations__


def test_audit_entry_has_no_updated_at():
    """AuditEntry is immutable — should not have updated_at column."""
    assert "updated_at" not in AuditEntry.__annotations__


# ── Module Exports ───────────────────────────────────────────────────────────

def test_models_init_exports_all():
    """src/models/__init__.py should export all model classes."""
    import src.models as m

    assert hasattr(m, "User")
    assert hasattr(m, "Transaction")
    assert hasattr(m, "FraudScore")
    assert hasattr(m, "FraudAlert")
    assert hasattr(m, "RuleMetadata")
    assert hasattr(m, "LLMReport")
    assert hasattr(m, "MLModelRun")
    assert hasattr(m, "AuditEntry")
    assert hasattr(m, "BaseModel")
