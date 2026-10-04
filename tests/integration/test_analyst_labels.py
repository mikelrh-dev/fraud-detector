"""Both analyst verdicts are recorded, and neither is invented.

WHAT THIS FILE IS FOR
--------------------
`AlertStatus.resolved` was reachable from exactly one endpoint. That is not a
missing feature, it is a missing distinction: "the analyst looked and this was
wrong" and "the analyst looked and this was right" both reduced to the same
status, so the database could only ever teach a model what a false positive
looks like. A confirmed fraud had nowhere to go.

These tests pin the two verdict paths and, just as importantly, the two paths
that are NOT verdicts.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
Nothing about which transactions get flagged, what score means fraud, or what
the review band covers. Those are the routed classification policy
(`tests/test_routed_classification.py`) and the score persistence
(`tests/integration/test_review_band_alerts.py`), both owned elsewhere. Stubbing
the scorer is not the "test the mock" anti-pattern here for the same reason it
is not one there: these tests are about the mapping from an analyst action to a
persisted row, and the score that put the alert in the queue is not what
changed.

THE SCORER IS NOT INVOLVED AT ALL
---------------------------------
`review` is asserted NOT to set a label. That is a real decision and the one
most likely to be undone by a well-meaning change: "reviewed" reads like an
outcome, and treating it as one would put unjudged rows into every labelled
count. An analyst opening an alert and an analyst judging an alert are
different acts, and only the second produces a label.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.models.fraud_alert import AlertStatus

#: The user the shared `auth_headers` fixture authenticates as.
OWNER_ID = "00000000-0000-0000-0000-000000000001"
STRANGER_ID = "99999999-9999-9999-9999-999999999999"

ALERT_ID = "33333333-3333-3333-3333-333333333333"
TXN_ID = "44444444-4444-4444-4444-444444444444"


def _alert(status: AlertStatus = AlertStatus.OPEN):
    """An alert row as the endpoint loads it.

    `status` is a real `AlertStatus` member rather than the plain string the
    older pipeline tests use, because the endpoints read `.value` off it to
    record `previous_status` and a `MagicMock` would put a mock repr into the
    audit trail.
    """
    alert = MagicMock()
    alert.id = ALERT_ID
    alert.transaction_id = TXN_ID
    alert.status = status
    alert.score = 85.0
    alert.threshold = 70.0
    alert.classification = "fraud"
    alert.reviewed_by = None
    alert.reviewed_at = None
    alert.created_at = MagicMock()
    alert.analyst_label = None
    return alert


def _seed_owned(mock_db: AsyncMock, alert, owner: str = OWNER_ID) -> list:
    """Make `mock_db` serve `alert`, then its transaction owned by `owner`.

    Returns the list that collects `session.add` calls, which is where the
    audit entry is read off -- the entry is written and never re-read on this
    path, so the write call IS the behaviour.
    """
    txn = MagicMock()
    txn.user_id = uuid.UUID(owner)

    alert_result = MagicMock()
    alert_result.scalar_one_or_none.return_value = alert
    txn_result = MagicMock()
    txn_result.scalar_one_or_none.return_value = txn

    mock_db.execute = AsyncMock(side_effect=[alert_result, txn_result])
    mock_db.flush = AsyncMock()

    added: list = []
    mock_db.add = lambda obj: added.append(obj)
    return added


def _audit_entries(added: list) -> list:
    return [obj for obj in added if type(obj).__name__ == "AuditEntry"]


@pytest.mark.asyncio
class TestFalsePositiveRecordsItsVerdict:
    """The endpoint that already existed now records what it decided."""

    async def test_false_positive_sets_the_label_and_resolves(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        alert = _alert()
        _seed_owned(mock_db, alert)

        response = await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/false-positive",
            headers=auth_headers,
            json={"action": "false_positive", "reason": "Viaje legitimo"},
        )

        assert response.status_code == 200, response.text
        assert alert.status == AlertStatus.RESOLVED
        assert alert.analyst_label == "false_positive", (
            f"false-positive resolved the alert and stored analyst_label="
            f"{alert.analyst_label!r}. A false positive is a judgement, and a "
            f"judgement nothing records is not a judgement."
        )

    async def test_false_positive_reports_the_label_back(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The response shape is unchanged, deliberately.

        `analyst_label` is NOT on `AlertResponse` in this unit, and that is a
        decision rather than an omission -- see the block comment on the
        schema. Briefly: the field would have to be read off the alert object,
        and the `MagicMock` alerts in
        `tests/integration/test_integration_pipeline.py` do not carry it, so
        Pydantic rejects the auto-created mock attribute and fixing that means
        editing three existing tests.

        This test exists so the choice is pinned rather than drifted into. If a
        later unit puts the verdict on the wire, this is the assertion that
        should be the one that changes, and changing it is a deliberate act
        rather than something that happens because a new field was added
        everywhere else.
        """
        alert = _alert()
        _seed_owned(mock_db, alert)

        response = await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/false-positive",
            headers=auth_headers,
            json={"action": "false_positive"},
        )

        assert response.status_code == 200, response.text
        assert "analyst_label" not in response.json(), (
            "AlertResponse now carries analyst_label. That is a real change to "
            "the wire contract and belongs in its own unit, with the alert-queue "
            "rendering that makes it useful to an analyst."
        )


@pytest.mark.asyncio
class TestConfirmFraudMirrorsFalsePositive:
    """Same shape, opposite verdict. That symmetry is the whole point."""

    async def test_confirm_fraud_labels_and_resolves(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        alert = _alert()
        _seed_owned(mock_db, alert)

        response = await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/confirm-fraud",
            headers=auth_headers,
            json={"action": "confirm_fraud", "reason": "Cargo no reconocido"},
        )

        assert response.status_code == 200, response.text
        assert alert.status == AlertStatus.RESOLVED, (
            "a confirmed fraud resolves the alert exactly as a false positive "
            "does; the verdict lives in analyst_label, not in a fourth status"
        )
        assert alert.analyst_label == "confirmed_fraud"

    async def test_confirm_fraud_stamps_reviewer_and_time(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """Same attribution fields as false-positive. The reviewer of a
        confirmed fraud is as accountable as the reviewer of a false positive.
        """
        alert = _alert()
        _seed_owned(mock_db, alert)

        await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/confirm-fraud",
            headers=auth_headers,
            json={"action": "confirm_fraud"},
        )

        assert str(alert.reviewed_by) == OWNER_ID, (
            "a confirmed fraud is recorded with no reviewer, so the label "
            "cannot be attributed to the analyst who made it"
        )
        assert alert.reviewed_at is not None

    async def test_confirm_fraud_writes_an_audit_entry(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The audit trail records the verdict, not just the status change.

        An audit entry reading `new_status=resolved` cannot be told apart from
        a false-positive entry, which is the ambiguity this endpoint exists to
        close. `action_type` is what separates them.
        """
        alert = _alert()
        added = _seed_owned(mock_db, alert)

        await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/confirm-fraud",
            headers=auth_headers,
            json={"action": "confirm_fraud", "reason": "Patron claro"},
        )

        entries = _audit_entries(added)
        assert len(entries) == 1, f"expected 1 audit entry, got {len(entries)}"
        entry = entries[0]
        assert entry.action_type == "confirm_fraud"
        assert entry.previous_status == "open"
        assert entry.new_status == "resolved"
        assert entry.details["reason"] == "Patron claro"

    async def test_confirm_fraud_requires_ownership(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """Another analyst's transaction is not confirmable by this analyst.

        This is the check `false-positive` already performs; the new endpoint
        has to perform it too, and it is asserted here because an endpoint
        added by copy-paste is exactly where a dropped guard hides.
        """
        alert = _alert()
        _seed_owned(mock_db, alert, owner=STRANGER_ID)

        response = await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/confirm-fraud",
            headers=auth_headers,
            json={"action": "confirm_fraud"},
        )

        assert response.status_code == 403, response.text
        assert alert.analyst_label is None, (
            "a rejected request still labelled the alert"
        )

    async def test_confirm_fraud_404s_on_an_unknown_alert(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """404 for a missing alert -- and the body says which 404 this is.

        The status alone is not enough to be worth asserting: FastAPI answers an
        UNREGISTERED route with 404 as well, so a bare status check passes
        against a route that does not exist. The detail is what distinguishes
        "no such alert" from "no such endpoint", and this test would otherwise
        have gone green before the endpoint was written.
        """
        missing = MagicMock()
        missing.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=missing)
        mock_db.flush = AsyncMock()

        response = await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/confirm-fraud",
            headers=auth_headers,
            json={"action": "confirm_fraud"},
        )

        assert response.status_code == 404, response.text
        assert response.json()["detail"] == "Alert not found", (
            f"404 body is {response.json()!r}. FastAPI's not-found for an "
            f"unregistered route is 'Not Found', so this detail is what proves "
            f"the route exists and the alert genuinely does not."
        )

    async def test_confirm_fraud_reason_is_optional(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """`reason` stays optional, as it is on the other two endpoints.

        A required reason would be defensible policy, but it is a policy change
        and this is plumbing. Making it mandatory here while `review` and
        `false-positive` accept a missing reason would be the worse outcome.
        """
        alert = _alert()
        added = _seed_owned(mock_db, alert)

        response = await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/confirm-fraud",
            headers=auth_headers,
            json={"action": "confirm_fraud"},
        )

        assert response.status_code == 200, response.text
        assert _audit_entries(added)[0].details["reason"] is None

    async def test_the_action_field_accepts_confirm_fraud(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """`AlertActionRequest.action` accepts the new verb.

        The pattern on that field is `^(review|false_positive|revert)$`. Left
        alone, every request to the new endpoint is a 422 at the body parser,
        which reads as a broken route rather than a missing enum member.
        """
        alert = _alert()
        _seed_owned(mock_db, alert)

        response = await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/confirm-fraud",
            headers=auth_headers,
            json={"action": "confirm_fraud"},
        )

        assert response.status_code == 200, response.text


@pytest.mark.asyncio
class TestTheNonVerdictPaths:
    """`review` and `revert` are not verdicts, and must not be recorded as one."""

    async def test_review_does_not_set_a_label(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """Looking at an alert is not judging it.

        `review` marks the alert as handled so it leaves the queue. It records
        no opinion about whether the transaction was fraud, and writing one
        would manufacture ground truth for every alert an analyst merely opened.
        """
        alert = _alert()
        _seed_owned(mock_db, alert)

        response = await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/review",
            headers=auth_headers,
            json={"action": "review"},
        )

        assert response.status_code == 200, response.text
        assert alert.status == AlertStatus.REVIEWED
        assert alert.analyst_label is None, (
            "review labelled the alert. 'Reviewed' is a workflow state; "
            "treating it as a verdict puts unjudged rows into every labelled "
            "count and quietly poisons the exported corpus."
        )

    async def test_revert_does_not_clear_an_existing_label(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """PINS A KNOWN AMBIGUITY rather than resolving it.

        `revert` reopens the alert for re-review and leaves `analyst_label`
        alone. So an alert that was confirmed and then reverted still carries
        `confirmed_fraud` while its status reads `open`.

        That is deliberate here, and it is a real defect to decide on later.
        The case for leaving it: clearing the label destroys the analyst's
        verdict, which is the one thing on this row that cannot be recomputed --
        reopen-and-rejudge is not the same event as judge. The case against: a
        label on an `open` alert is misleading to the exporter and to any future
        consumer that keys on the pair.

        Whichever way it is decided, it cannot be decided by accident, so the
        current behaviour is pinned here. See `docs/plans/` for the follow-up.
        """
        alert = _alert(status=AlertStatus.RESOLVED)
        alert.analyst_label = "confirmed_fraud"
        _seed_owned(mock_db, alert)

        response = await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/revert",
            headers=auth_headers,
            json={"action": "revert"},
        )

        assert response.status_code == 200, response.text
        assert alert.status == AlertStatus.OPEN
        assert alert.analyst_label == "confirmed_fraud", (
            "revert cleared the label. If that was deliberate it is a policy "
            "decision that belongs in its own change with its own reasoning, "
            "not as a side effect of reopening an alert."
        )

    async def test_an_unlabelled_alert_reports_null(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The null-unjudged case is NULL, never an empty string.

        An empty string would be the quiet version of the same bug the column
        exists to prevent: a consumer testing `if label:` would treat "" as
        unlabelled and one testing `if label is not None` would not, and the
        exporter would export a row whose verdict it cannot read.
        """
        alert = _alert()
        _seed_owned(mock_db, alert)

        response = await test_client.post(
            f"/api/v1/alerts/{ALERT_ID}/review",
            headers=auth_headers,
            json={"action": "review"},
        )

        assert response.status_code == 200, response.text
        assert alert.analyst_label is None, (
            f"review left analyst_label={alert.analyst_label!r}; the "
            f"unjudged case must be None, not a falsy placeholder"
        )
