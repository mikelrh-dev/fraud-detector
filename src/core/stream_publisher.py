"""Event publisher for Redis Streams.

Publishes fraud detection events to Redis Streams instead of simple queues.
Supports consumer groups for scaling workers horizontally.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

from src.core.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


async def get_stream_client() -> redis.Redis:
    """Get or create Redis stream client."""
    global _redis
    if _redis is None:
        _redis = await redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
    return _redis


async def publish_event(stream_name: str, event_data: dict[str, Any]) -> str:
    """Publish event to a Redis Stream with automatic size limit.
    
    Args:
        stream_name: Name of the stream (e.g., "fraud:shap", "fraud:embeddings")
        event_data: Event payload (will be JSON-encoded)
    
    Returns:
        Message ID from Redis
    """
    try:
        client = await get_stream_client()
        
        # Add timestamp to event
        event_with_ts = {
            **event_data,
            "published_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        
        # XADD to stream with MAXLEN to prevent unbounded growth
        # maxlen=100000 keeps ~50MB in Redis (500B avg per event)
        # approximate=True uses efficient trimming (~10% off)
        message_id = await client.xadd(
            stream_name,
            {"data": json.dumps(event_with_ts)},
            maxlen=100000,  # Trim stream to 100K events
            approximate=True,  # Use approximate trimming for efficiency
        )
        
        logger.debug("Published event to stream %s: %s", stream_name, message_id)
        return message_id.decode("utf-8") if isinstance(message_id, bytes) else message_id
        
    except Exception as exc:
        logger.error("Failed to publish event to stream %s: %s", stream_name, exc)
        raise


async def ensure_consumer_group(stream_name: str, group_name: str) -> None:
    """Ensure a consumer group exists for a stream.
    
    Args:
        stream_name: Name of the stream
        group_name: Name of the consumer group
    """
    try:
        client = await get_stream_client()
        
        # Try to create consumer group (will fail if already exists, which is fine)
        try:
            await client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
            logger.info("Created consumer group %s for stream %s", group_name, stream_name)
        except redis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                # Group already exists
                logger.debug("Consumer group %s already exists for stream %s", group_name, stream_name)
            else:
                raise
                
    except Exception as exc:
        logger.error("Failed to ensure consumer group %s for stream %s: %s", group_name, stream_name, exc)
        raise


async def close() -> None:
    """Close Redis connection."""
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
        logger.info("Closed Redis stream client")
