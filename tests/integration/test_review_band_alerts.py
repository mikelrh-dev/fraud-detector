"""Every transaction an analyst must look at gets an alert row.

WHAT THIS FILE IS FOR
--------------------
The alert was created only when `classification == "fraud"`. That made the whole
review band invisible: the routed policy sends a grey-zone transaction to
`review`, the endpoint correctly answered `FLAGGED` with 3DS/SMS friction and
staged its SHAP attribution, and then wrote NO alert row. An analyst had no way
to find those transactions except by filtering the transaction list by status
and reading the score off each row — the alert queue, which is the screen built
for this job, stayed empty while the queue filled up.

The gate is now "not legitimate". The alert stores whatever classification the
scoring service actually produced, so a `review` row is distinguishable from a
`fraud` row in the queue and by every consumer that reads the column.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
This file does not decide WHICH transactions are `review`. That is the routed
classification policy, owned by `tests/test_routed_classification.py`, and the
scoring service is stubbed here precisely so these cases cannot start failing
when that policy moves. What is under test is the mapping from a verdict to a
persisted alert row — the gate — and nothing else about the score.

Stubbing the scorer is not the "test the mock" anti-pattern here: a `review`
verdict produced by a real payload depends on the timestamp, the amount tier,
the velocity store and the model artifact, none of which are what broke. Driving
the gate from a known verdict is what makes the failure legible.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from httpx import AsyncClient

from src.models.fraud_alert import AlertStatus, FraudAlert
from src.models.fraud_score import FraudScore
from src.services.scoring_service import ScoringResult

PAYLOAD = {
    "amount": 5000.00,
    "currency": "USD",
    "merchant_name": "Electronics Store",
    "merchant_category": "retail",
    "card_last4": "5678",
}

#: A verdict plus the numbers the endpoint copies onto the alert row.
CASES = {
    "legitimate": {"classification": "legitimate", "ensemble_score": 12.0, "threshold": 70.0},
    "review": {"classification": "review", "ensemble_score": 58.0, "threshold": 70.0},
    "fraud": {"classification": "fraud", "ensemble_score": 95.0, "threshold": 70.0},
}


def _stubbed_scorer(**verdict: object) -> AsyncMock:
    """A mock whose `compute_scores` returns a real `ScoringResult` for `verdict`.

    The real `ScoringResult` is used rather than a hand-built object so a field
    added to the dataclass surfaces here as a missing-attribute error instead of
    a silently wrong default. It is passed as `new=` because `patch`'s kwarg form
    builds its OWN mock and would return that instead of this one.
    """
    result = ScoringResult(
        rule_score=58.0,
        fired_rules=["high_amount"],
        features=np.zeros(10),
        ml_score=40.0,
        threshold=float(verdict["threshold"]),  # type: ignore[arg-type]
        ensemble_score=float(verdict["ensemble_score"]),  # type: ignore[arg-type]
        classification=str(verdict["classification"]),
        layers_used=("rule", "ml", "context"),
    )
    return AsyncMock(return_value=result)


def _empty_context_queries(mock_db: AsyncMock) -> None:
    """The step-2.5 context aggregates must answer empty, not a coroutine.

    `AsyncMock(spec=AsyncSession)` makes `.scalars()` return a coroutine, which
    the endpoint's except-handler reports as "Failed to create transaction" — a
    persistence bug that is really a mock gap.
    """
    mock_scalars = MagicMock()
    mock_scalars.all = MagicMock(return_value=[])
    mock_scalars.one = MagicMock(return_value=None)

    result = MagicMock()
    result.scalars = MagicMock(return_value=mock_scalars)
    result.scalar = MagicMock(return_value=None)
    result.scalar_one_or_none = MagicMock(return_value=None)

    mock_db.execute = AsyncMock(return_value=result)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()


def _added(mock_db: AsyncMock, model: type) -> list:
    """Every instance of `model` handed to `session.add`, in order.

    Read off `add` rather than off a query: the alert is written with the
    session and never re-read on this path, so the write call IS the behaviour.
    """
    return [
        call.args[0]
        for call in mock_db.add.call_args_list
        if call.args and isinstance(call.args[0], model)
    ]


async def _post(
    test_client: AsyncClient,
    mock_db: AsyncMock,
    auth_headers: dict,
    classification: str,
) -> dict:
    """POST one transaction whose scoring verdict is pinned to `classification`.

    Every patch is active for the duration of the request. A `with` block that
    closes before the call would leave the real scorer in place and silently
    measure nothing.
    """
    _empty_context_queries(mock_db)

    with (
        patch(
            "src.api.v1.transactions._scoring_service.compute_scores",
            new=_stubbed_scorer(**CASES[classification]),
        ),
        patch("src.api.v1.transactions.enqueue_event"),
        patch("src.api.v1.transactions._graph_service.add_transaction_persisted",
              AsyncMock()),
    ):
        response = await test_client.post(
            "/api/v1/transactions", json=PAYLOAD, headers=auth_headers
        )

    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
class TestTheAlertGate:
    """One row per non-legitimate transaction, carrying the real verdict."""

    async def test_review_creates_an_open_alert_classified_review(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The regression: the review band produced no row at all.

        `58.0` against a `70.0` threshold is squarely inside the review band —
        not fraud, not legitimate — so under the old `== "fraud"` gate this
        transaction got a `FLAGGED` status, 3DS friction and a staged SHAP
        event, and nothing an analyst could open.
        """
        data = await _post(test_client, mock_db, auth_headers, "review")

        assert data["classification"] == "review"
        alerts = _added(mock_db, FraudAlert)
        assert len(alerts) == 1, (
            f"a review-band transaction created {len(alerts)} alert rows, "
            f"expected 1. The grey zone is what the alert queue exists to "
            f"surface, and it is the band that was invisible."
        )

        alert = alerts[0]
        assert alert.status == AlertStatus.OPEN, (
            f"a brand-new alert is {alert.status!r}; an analyst must be able to "
            f"filter the queue by status=open to find it."
        )
        assert alert.classification == "review", (
            f"the alert stores {alert.classification!r}. The row has to carry "
            f"the verdict the scorer produced, or a review is indistinguishable "
            f"from a block in the queue."
        )
        assert alert.score == pytest.approx(58.0)
        assert alert.threshold == pytest.approx(70.0)
        assert str(alert.transaction_id) == data["transaction_id"], (
            "the alert points at a different transaction than the one scored"
        )

    async def test_fraud_still_creates_an_open_alert_classified_fraud(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The fraud path is unchanged — this is the control for the case above.

        A gate widened from one verdict to two has to be shown not to have
        altered the verdict it already handled.
        """
        data = await _post(test_client, mock_db, auth_headers, "fraud")

        assert data["classification"] == "fraud"
        alerts = _added(mock_db, FraudAlert)
        assert len(alerts) == 1
        assert alerts[0].classification == "fraud"
        assert alerts[0].status == AlertStatus.OPEN
        assert alerts[0].score == pytest.approx(95.0)

    async def test_legitimate_creates_no_alert(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The gate is "not legitimate", not "always".

        This is the case that keeps the widening honest: without it, a gate that
        simply always wrote a row would pass the two tests above.
        """
        data = await _post(test_client, mock_db, auth_headers, "legitimate")

        assert data["classification"] == "legitimate"
        assert _added(mock_db, FraudAlert) == [], (
            "a legitimate transaction created an alert row; the alert queue "
            "would fill with routine purchases and stop being a queue"
        )

    @pytest.mark.parametrize("classification", ["legitimate", "review", "fraud"])
    async def test_every_verdict_still_persists_its_score(
        self,
        test_client: AsyncClient,
        mock_db: AsyncMock,
        auth_headers: dict,
        classification: str,
    ):
        """Score persistence is untouched by the gate.

        The gate sits between the score write and the status map. Asserting the
        score row for all three verdicts is what proves the gate was widened
        rather than the surrounding persistence rearranged.
        """
        data = await _post(test_client, mock_db, auth_headers, classification)

        scores = _added(mock_db, FraudScore)
        assert len(scores) == 1, (
            f"verdict {classification!r} persisted {len(scores)} score rows"
        )
        assert scores[0].classification == classification
        assert data["classification"] == classification