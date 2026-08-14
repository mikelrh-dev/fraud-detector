"""Tests for stream group management helpers (FD-STREAM-002, FD-STREAM-004)."""

import json
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ResponseError

from src.core.stream_manager import ensure_consumer_group, migrate_legacy_list


@pytest.mark.asyncio
async def test_ensure_consumer_group_creates_with_mkstream():
    """A missing group must be created with MKSTREAM (FD-STREAM-002)."""
    mock_redis = AsyncMock()

    await ensure_consumer_group(mock_redis, "fraud:shap", "shap-workers")

    mock_redis.xgroup_create.assert_awaited_once_with(
        "fraud:shap", "shap-workers", id="0", mkstream=True
    )


@pytest.mark.asyncio
async def test_ensure_consumer_group_tolerates_busygroup():
    """BUSYGROUP (group already exists) must not raise (FD-STREAM-002)."""
    mock_redis = AsyncMock()
    mock_redis.xgroup_create.side_effect = ResponseError(
        "BUSYGROUP Consumer Group name already exists"
    )

    await ensure_consumer_group(mock_redis, "fraud:llm", "llm-workers")

    mock_redis.xgroup_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_consumer_group_re_raises_other_errors():
    """A non-BUSYGROUP ResponseError must propagate."""
    mock_redis = AsyncMock()
    mock_redis.xgroup_create.side_effect = ResponseError("NOGROUP No such key")

    with pytest.raises(ResponseError, match="NOGROUP"):
        await ensure_consumer_group(mock_redis, "fraud:llm", "llm-workers")


@pytest.mark.asyncio
async def test_migrate_legacy_list_drains_into_stream():
    """Leftover legacy list messages must be XADDed into the stream (FD-STREAM-004)."""
    mock_redis = AsyncMock()
    messages = [
        json.dumps({"transaction_id": "a", "retry_count": 0}),
        json.dumps({"transaction_id": "b", "retry_count": 0}),
    ]
    mock_redis.rpop = AsyncMock(side_effect=[messages[0], messages[1], None])

    migrated = await migrate_legacy_list(
        mock_redis, "fraud:shap", "fraud:shap", "shap_attribution"
    )

    assert migrated == 2
    assert mock_redis.rpop.await_count == 3
    assert mock_redis.xadd.await_count == 2
    # Each migrated message lands on the stream with the event type preserved
    streams = [call.args[0] for call in mock_redis.xadd.call_args_list]
    assert streams == ["fraud:shap", "fraud:shap"]


@pytest.mark.asyncio
async def test_migrate_legacy_list_empty_is_noop():
    """An empty legacy list must migrate zero messages and not crash."""
    mock_redis = AsyncMock()
    mock_redis.rpop = AsyncMock(return_value=None)

    migrated = await migrate_legacy_list(
        mock_redis, "fraud:embeddings", "fraud:embeddings", "merchant_embedding"
    )

    assert migrated == 0
    mock_redis.xadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_migrate_legacy_list_llm_uses_fraud_reports_source():
    """The LLM legacy list is fraud:reports, drained into fraud:llm (design D5)."""
    mock_redis = AsyncMock()
    mock_redis.rpop = AsyncMock(
        side_effect=[json.dumps({"transaction_id": "a"}), None]
    )

    migrated = await migrate_legacy_list(
        mock_redis, "fraud:reports", "fraud:llm", "llm_report"
    )

    assert migrated == 1
    mock_redis.rpop.assert_awaited_with("fraud:reports")
    assert mock_redis.xadd.await_args.args[0] == "fraud:llm"
