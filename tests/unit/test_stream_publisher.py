"""Tests for the Redis Streams publisher (FD-STREAM-001)."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.stream_publisher import (
    EVENT_STREAM_MAP,
    decode_message,
    publish_transaction_event,
)


def _now() -> datetime:
    return datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_publish_maps_llm_event_to_fraud_llm_stream():
    """llm_report must be appended to the fraud:llm stream (FD-STREAM-001)."""
    mock_redis = AsyncMock()
    payload = {"transaction_id": "abc", "score_breakdown": {"rule_score": 60.0}}

    with (
        patch("src.core.stream_publisher.get_redis", return_value=mock_redis),
        patch("src.core.stream_publisher._utc_now", side_effect=_now),
    ):
        await publish_transaction_event("llm_report", payload)

    mock_redis.xadd.assert_awaited_once()
    stream, fields = mock_redis.xadd.await_args.args
    assert stream == "fraud:llm"
    assert fields["event_type"] == "llm_report"
    assert fields["timestamp"] == "2026-08-14T12:00:00+00:00"
    assert json.loads(fields["payload"]) == payload


@pytest.mark.asyncio
async def test_publish_maps_shap_event_to_fraud_shap_stream():
    """shap_attribution must be appended to the fraud:shap stream."""
    mock_redis = AsyncMock()
    payload = {"transaction_id": "abc", "features": [0.1, 0.2]}

    with patch("src.core.stream_publisher.get_redis", return_value=mock_redis):
        await publish_transaction_event("shap_attribution", payload)

    stream, fields = mock_redis.xadd.await_args.args
    assert stream == "fraud:shap"
    assert fields["event_type"] == "shap_attribution"
    assert json.loads(fields["payload"])["features"] == [0.1, 0.2]


@pytest.mark.asyncio
async def test_publish_maps_embedding_event_to_fraud_embeddings_stream():
    """merchant_embedding must be appended to the fraud:embeddings stream."""
    mock_redis = AsyncMock()
    payload = {"transaction_id": "abc", "merchant_name": "Test Store"}

    with patch("src.core.stream_publisher.get_redis", return_value=mock_redis):
        await publish_transaction_event("merchant_embedding", payload)

    stream, fields = mock_redis.xadd.await_args.args
    assert stream == "fraud:embeddings"
    assert json.loads(fields["payload"])["merchant_name"] == "Test Store"


def test_event_stream_map_has_all_three_types():
    """Every event type maps to exactly one dedicated stream (FD-STREAM-001)."""
    assert EVENT_STREAM_MAP == {
        "llm_report": "fraud:llm",
        "shap_attribution": "fraud:shap",
        "merchant_embedding": "fraud:embeddings",
    }


@pytest.mark.asyncio
async def test_publish_unknown_event_type_raises_value_error():
    """An unknown event type must raise ValueError and write nothing."""
    mock_redis = AsyncMock()

    with patch("src.core.stream_publisher.get_redis", return_value=mock_redis):
        with pytest.raises(ValueError, match="Unknown event type"):
            await publish_transaction_event("nonsense", {})

    mock_redis.xadd.assert_not_awaited()


def test_decode_message_extracts_payload_from_str_fields():
    """decode_message must json.loads the payload field (FD-STREAM-002)."""
    fields = {
        "event_type": "shap_attribution",
        "timestamp": "2026-08-14T12:00:00+00:00",
        "payload": json.dumps({"transaction_id": "abc", "retry_count": 0}),
    }
    message = decode_message(fields)
    assert message == {"transaction_id": "abc", "retry_count": 0}


def test_decode_message_handles_bytes_fields():
    """decode_message must tolerate bytes keys/values (raw redis-py client)."""
    fields = {
        b"event_type": b"llm_report",
        b"timestamp": b"2026-08-14T12:00:00+00:00",
        b"payload": json.dumps({"transaction_id": "abc"}).encode(),
    }
    message = decode_message(fields)
    assert message == {"transaction_id": "abc"}
