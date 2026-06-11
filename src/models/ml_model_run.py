"""MLModelRun ORM model — tracks ML model training runs and performance."""

import enum

from sqlalchemy import Boolean, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import BaseModel


class MLModelStatus(str, enum.Enum):
    """ML model run status."""

    TRAINING = "training"
    READY = "ready"
    FAILED = "failed"


class MLModelRun(BaseModel):
    """Record of an ML model training run with performance metrics."""

    __tablename__ = "ml_model_runs"

    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=True)
    status: Mapped[MLModelStatus] = mapped_column(
        String(20),
        default=MLModelStatus.TRAINING,
        nullable=False,
    )
    drift_detected: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
