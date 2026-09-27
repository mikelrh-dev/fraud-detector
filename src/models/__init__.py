"""Model exports — all ORM models for the fraud detection system."""

from src.models.audit_entry import AuditEntry
from src.models.base import BaseModel

# DriftReferenceData must stay exported: alembic/env.py and the migration
# tests import from this package, and an unregistered model never reaches
# Base.metadata, so autogenerate emits drop_table for it.
from src.models.drift_reference import DriftReferenceData
from src.models.fraud_alert import FraudAlert
from src.models.fraud_score import FraudScore
from src.models.llm_report import LLMReport
from src.models.ml_model_run import MLModelRun
from src.models.rule import RuleMetadata
from src.models.shap_attribution import ShapAttribution
from src.models.transaction import Transaction
from src.models.user import User

__all__ = [
    "AuditEntry",
    "BaseModel",
    "DriftReferenceData",
    "FraudAlert",
    "FraudScore",
    "LLMReport",
    "MLModelRun",
    "RuleMetadata",
    "ShapAttribution",
    "Transaction",
    "User",
]
