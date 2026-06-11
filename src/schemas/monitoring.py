"""Pydantic schemas for model monitoring and dashboard endpoints."""

from datetime import datetime

from pydantic import BaseModel


class FeatureDriftResponse(BaseModel):
    """Per-feature drift details in a drift report."""

    feature: str
    psi: float
    reference_mean: float
    current_mean: float


class PredictionDriftResponse(BaseModel):
    """Prediction drift details — mean shift between reference and current."""

    reference_mean: float
    current_mean: float
    shift: float


class DriftReportResponse(BaseModel):
    """Full drift report returned by GET /monitoring/drift."""

    model_version: str = "latest"
    drift_detected: bool
    drift_score: float
    feature_drifts: list[FeatureDriftResponse]
    prediction_drift: PredictionDriftResponse | None = None
    evaluated_at: datetime


class ModelMetricsResponse(BaseModel):
    """Performance metrics for a model run."""

    precision: float
    recall: float
    f1: float
    auc_roc: float
    timestamp: str


class ModelRunResponse(BaseModel):
    """A single model run record with metrics and status."""

    id: str
    model_version: str
    metrics: ModelMetricsResponse | dict | None = None
    drift_detected: bool
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardMetricsResponse(BaseModel):
    """Dashboard summary — aggregate metrics for the monitoring dashboard."""

    total_transactions: int = 0
    fraud_percentage: float = 0.0
    avg_score: float = 0.0
    active_alerts: int = 0
    model_status: str = "unknown"


class ReferenceDataRequest(BaseModel):
    """Payload for uploading reference data for drift comparison."""

    data: list[float]
    description: str | None = None
