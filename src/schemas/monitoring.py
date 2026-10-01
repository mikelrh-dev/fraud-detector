"""Pydantic schemas for model monitoring and dashboard endpoints."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ModelStatus(str, Enum):
    """The single vocabulary for "is the ML model loaded?".

    There were three of these in flight at once and nothing enforced any of
    them: the dashboard endpoint answered the literal ``"operational"``
    without asking anything, the schema default was ``"unknown"`` (a state no
    producer ever emitted), and the frontend's mock handler said ``"active"``.
    A panel could therefore report a working model in the same breath as
    ``/health/ready`` reporting ``not_loaded``.

    One enum, two members, both of which something actually produces:
    ``api.v1.transactions.ml_model_status`` derives them from
    ``MLModelService.is_available``, and both ``/health/ready`` and
    ``/monitoring/dashboard`` return that function's result. The two
    endpoints read one source, so they cannot disagree.

    Note there is no ``UNKNOWN``. "Nobody asked" is not a state of a model,
    and publishing it is how a dashboard ends up claiming things nobody
    measured.

    Subclasses `str` rather than using `enum.StrEnum` because this project
    targets Python 3.10 (see `python_version` in pyproject.toml) and
    `StrEnum` landed in 3.11. The mixin is the documented 3.10 spelling and
    serialises identically — JSON encodes the member, not the enum object.
    """

    OK = "ok"
    NOT_LOADED = "not_loaded"


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

    #: Whether the ML model is loaded, derived — never asserted. See
    #: ``ModelStatus``. Defaults to ``NOT_LOADED`` because that is the only
    #: answer that cannot overclaim: a caller who forgets to pass the derived
    #: value gets a dashboard reporting the model as absent, which an operator
    #: investigates, rather than one reporting it as fine, which they do not.
    model_status: ModelStatus = ModelStatus.NOT_LOADED


class ReferenceDataRequest(BaseModel):
    """Payload for uploading reference data for drift comparison."""

    data: list[float]
    description: str | None = None
