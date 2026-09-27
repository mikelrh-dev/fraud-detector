"""DriftReferenceData ORM model — stores drift reference baseline data."""

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import BaseModel


class DriftReferenceData(BaseModel):
    """Reference baseline dataset for drift comparison.

    Stores the reference data used by the drift detection service.
    Persisted in the database so it survives Redis flushes and service restarts.
    """

    __tablename__ = "drift_reference_data"

    columns: Mapped[list] = mapped_column(JSON, nullable=False)
    data: Mapped[list] = mapped_column(JSON, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="v1")
