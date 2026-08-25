"""Tests for the Redis Streams publisher (FD-STREAM-001).

Covers the current ``publish_event`` / ``ensure_consumer_group`` / ``close``
API: JSON-encoded payloads under a ``data`` field, bounded stream growth,
timestamp stamping, and error semantics.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.stream_publisher import close, ensure_consumer_group, publish_event


def _mock_client() -> AsyncMock:
    client = AsyncMock()
    client.xadd.return_value = b"1700000000000-0"
    return client


@pytest.mark.asyncio
async def test_publish_event_xadds_json_payload_to_stream():
    """Payload is JSON-encoded under 'data' and addressed to the given stream."""
    client = _mock_client()
    payload = {"transaction_id": "abc", "score_breakdown": {"rule_score": 60.0}}

    with patch("src.core.stream_publisher.get_stream_client", return_value=client):
        message_id = await publish_event("fraud:llm", payload)

    assert message_id == "1700000000000-0"
    client.xadd.assert_awaited_once()
    args, kwargs = client.xadd.await_args
    stream, fields = args[0], args[1]
    assert stream == "fraud:llm"
    sent = json.loads(fields["data"])
    assert sent["transaction_id"] == "abc"
    assert "published_at" in sent  # stamped by the publisher


@pytest.mark.asyncio
async def test_publish_event_bounds_stream_growth():
    """XADD must cap the stream (~100K entries, approximate trim)."""
    client = _mock_client()

    with patch("src.core.stream_publisher.get_stream_client", return_value=client):
        await publish_event("fraud:shap", {"ok": True})

    _, kwargs = client.xadd.await_args
    assert kwargs["maxlen"] == 100000
    assert kwargs["approximate"] is True


@pytest.mark.asyncio
async def test_publish_event_propagates_redis_failures():
    """A Redis failure must raise, never silently drop the event."""
    client = AsyncMock()
    client.xadd.side_effect = ConnectionError("redis down")

    with patch(
        "src.core.stream_publisher.get_stream_client", return_value=client
    ), pytest.raises(ConnectionError):
        await publish_event("fraud:embeddings", {"x": 1})

@pytest.mark.asyncio
async def test_ensure_consumer_group_creates_group():
    """Group creation is attempted with mkstream from the beginning."""
    client = AsyncMock()

    with patch("src.core.stream_publisher.get_stream_client", return_value=client):
        await ensure_consumer_group("fraud:shap", "shap-workers")

    client.xgroup_create.assert_awaited_once_with(
        "fraud:shap", "shap-workers", id="0", mkstream=True
    )


@pytest.mark.asyncio
async def test_ensure_consumer_group_tolerates_busygroup():
    """An existing group (BUSYGROUP) is fine and not re-raised."""
    import redis

    client = AsyncMock()
    client.xgroup_create.side_effect = redis.ResponseError(
        "BUSYGROUP Consumer Group name already exists"
    )

    with patch("src.core.stream_publisher.get_stream_client", return_value=client):
        await ensure_consumer_group("fraud:shap", "shap-workers")  # must not raise


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_close_closes_shared_client():
    """close() must tear down the shared connection."""
    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    with patch("src.core.stream_publisher._redis", mock_client):
        await close()

    mock_client.close.assert_awaited_once()
