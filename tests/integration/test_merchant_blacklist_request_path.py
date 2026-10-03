"""The request path must read the merchant blacklist from settings.

The other half of ML-01, audit 2026-09-29. `api/v1/transactions.py` used to
inline three merchant strings into the `context` dict it hands the rule
engine. Moving them to `src/core/config.py` fixes the "no configuration path"
part and nothing else, on its own: a settings field that no caller reads is
the same defect wearing a different hat, and this repo has just found two of
those (TST-01, TST-02).

So these tests drive a real POST and capture the context the endpoint
actually built. A literal left behind in the request path fails
`test_endpoint_follows_an_overridden_list` even though it would satisfy
`test_endpoint_passes_the_configured_list_to_the_rule_engine`.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

import src.api.v1.transactions as transactions_api
from src.core.config import settings

pytestmark = pytest.mark.asyncio

VALID_PAYLOAD = {
    "amount": 500.00,
    "currency": "USD",
    "merchant_name": "Grocery Store",
    # D3: this said "groceries", which is NOT in KNOWN_MERCHANT_CATEGORIES and
    # is not an alias of "grocery" either — an unknown category scoring
    # merchant_risk_level = 0.0 and is_crypto = 0.0, and now a 422. "grocery" is
    # the canonical spelling and produces the same two features, so the rule
    # under test is unchanged. If "groceries" is a spelling real clients send,
    # the fix is one entry in CATEGORY_ALIASES — not a hand-edited fixture.
    "merchant_category": "grocery",
    "card_last4": "1234",
}

PREVIOUS_LITERALS = [
    "crypto exchange pro",
    "online gambling",
    "money transfer now",
]


async def _capture_context(
    test_client: AsyncClient,
    mock_db: AsyncMock,
    auth_headers: dict,
) -> dict[str, Any]:
    """POST a transaction and return the context the endpoint handed the scorer.

    Wraps the real `compute_scores` rather than replacing it, so the request
    still completes normally and the endpoint genuinely runs.
    """
    captured: dict[str, Any] = {}
    real_compute = transactions_api._scoring_service.compute_scores

    async def _spy(tx_data, context, user_history):
        captured.update(context)
        return await real_compute(tx_data, context, user_history)

    mock_db.execute = AsyncMock(return_value=MagicMock())
    transactions_api._scoring_service.compute_scores = _spy
    try:
        response = await test_client.post(
            "/api/v1/transactions",
            json=VALID_PAYLOAD,
            headers=auth_headers,
        )
    finally:
        transactions_api._scoring_service.compute_scores = real_compute

    assert response.status_code == 201
    assert captured, "the scoring service was never called"
    return captured


class TestRequestPathReadsTheSetting:
    async def test_endpoint_passes_the_configured_list(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The context carries the three merchants that were inlined here."""
        captured = await _capture_context(test_client, mock_db, auth_headers)
        assert captured["merchant_blacklist"] == PREVIOUS_LITERALS

    async def test_endpoint_follows_an_overridden_list(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """Change the setting and the request path changes with it.

        This is the test that makes the first one mean something. Both pass
        while the endpoint holds a literal; only this one goes red.
        """
        original = settings.merchant_blacklist
        settings.merchant_blacklist = ["a merchant only the operator knows"]
        try:
            captured = await _capture_context(test_client, mock_db, auth_headers)
        finally:
            settings.merchant_blacklist = original

        assert captured["merchant_blacklist"] == [
            "a merchant only the operator knows"
        ]
