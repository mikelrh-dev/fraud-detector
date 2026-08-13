"""ShapAttribution ORM model — persists top-k SHAP feature contributions."""

import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import BaseModel


class ShapAttribution(BaseModel):
    """Feature contribution computed by SHAP for a scored transaction.

    One row per feature (rank 1..5 ordered by absolute contribution).
    Rows are replaced on re-run (delete-then-insert), never duplicated.
    """

    __tablename__ = "shap_attributions"
    __table_args__ = (
        Index(
            "ix_shap_attributions_transaction_rank",
            "transaction_id",
            "rank",
        ),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature: Mapped[str] = mapped_column(String(100), nullable=False)
    contribution: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
