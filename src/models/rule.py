"""RuleMetadata ORM model — stores rule definitions."""

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import BaseModel


class RuleMetadata(BaseModel):
    """Metadata about a fraud detection rule."""

    __tablename__ = "rule_metadata"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
