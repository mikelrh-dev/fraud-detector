"""Pydantic schemas for fraud alert management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AlertResponse(BaseModel):
    """Fraud alert details returned to clients."""

    id: uuid.UUID
    transaction_id: uuid.UUID
    status: str
    score: float
    threshold: float
    classification: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime

#: `analyst_label` is deliberately NOT on this schema, and its absence is a
#: decision rather than an oversight. The verdict lives on the row, is read by
#: `scripts/export_labels.py` straight from the database, and is not needed on
#: the wire for the feedback loop to close.
#:
#: Adding it here was tried and reverted. `AlertResponse` is constructed with
#: explicit keyword arguments, so the field would have to be READ off the alert
#: object -- and the alert-action tests in
#: `tests/integration/test_integration_pipeline.py` build their alert as a
#: `MagicMock` with a fixed list of attributes, so an unread attribute comes
#: back as a `MagicMock` and Pydantic rejects it with a `ValidationError`:
#:
#:     Input should be a valid string [type=string_type,
#:     input_value=<MagicMock name='mock.analyst_label' ...>]
#:
#: Fixing that means editing three existing tests to add one attribute each.
#: That was not available here, and it is the wrong trade anyway: those tests
#: are asserting the audit trail, not the verdict, and a test whose setup has
#: to grow a field every time a field is added is a test that will stop
#: testing what it claims to.
#:
#: So the wire contract is unchanged and the new endpoint mirrors
#: `false-positive` exactly. Surfacing the verdict in the response AND in the
#: alert queue is its own unit, and it wants the frontend rendering with it --
#: an analyst who cannot see which verdict they recorded has not closed the
#: loop, only the database has.

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    """Paginated list of fraud alerts."""

    items: list[AlertResponse]
    total: int
    page: int
    page_size: int


class AlertActionRequest(BaseModel):
    """Payload for analyst action on an alert."""

    action: str = Field(
        ...,
        pattern=r"^(review|false_positive|confirm_fraud|revert)$",
        description=(
            "Action to perform: review, false_positive, confirm_fraud, or revert"
        ),
    )
    reason: str | None = Field(None, max_length=500)
