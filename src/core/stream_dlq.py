"""Dead-Letter Queue (DLQ) and retry handling for Redis Streams.

Handles messages that fail processing after MAX_RETRIES and puts them
in a dead-letter stream for debugging and manual intervention.
"""

import json
import logging
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Dead-letter stream for failed messages
DLQ_STREAM_NAME = "fraud:dlq"
MAX_RETRIES = 3
PENDING_TIMEOUT_MS = 300000  # 5 minutes


async def send_to_dlq(
    redis_client: redis.Redis,
    stream_name: str,
    message_id: str,
    consumer_group: str,
    consumer_name: str,
    error_reason: str,
    original_data: dict,
) -> None:
    """Send a failed message to the dead-letter queue.
    
    Args:
        redis_client: Redis async client
        stream_name: Original stream name
        message_id: Original message ID
        consumer_group: Consumer group that failed
        consumer_name: Consumer that failed
        error_reason: Why processing failed
        original_data: Original message data
    """
    try:
        # Add to DLQ with context
        dlq_entry = {
            "original_stream": stream_name,
            "original_message_id": str(message_id),
            "consumer_group": consumer_group,
            "consumer_name": consumer_name,
            "error_reason": error_reason,
            "original_data": json.dumps(original_data),
        }
        
        await redis_client.xadd(
            DLQ_STREAM_NAME,
            dlq_entry,
            maxlen=10000,  # Keep last 10K failed messages
        )
        
        # ACK the original message to remove from PEL
        await redis_client.xack(stream_name, consumer_group, message_id)
        
        logger.warning(
            "Message sent to DLQ: stream=%s, msg_id=%s, reason=%s",
            stream_name,
            message_id,
            error_reason,
        )
        
    except Exception as exc:
        logger.error("Failed to send message to DLQ: %s", exc)


async def recover_pending_messages(
    redis_client: redis.Redis,
    stream_name: str,
    consumer_group: str,
    consumer_name: str,
) -> list[tuple[str, dict]]:
    """Recover messages pending for more than PENDING_TIMEOUT_MS.
    
    Uses XAUTOCLAIM to automatically transfer stuck messages from other
    consumers in the group to this consumer for retry.
    
    Args:
        redis_client: Redis async client
        stream_name: Stream name to check
        consumer_group: Consumer group
        consumer_name: This consumer name
    
    Returns:
        List of (message_id, fields_dict) for recovered messages
    """
    try:
        # Use XAUTOCLAIM to transfer pending messages to this consumer
        # min_idle_time=300000: messages idle for >5 minutes
        result = await redis_client.xautoclaim(
            stream_name,
            consumer_group,
            consumer_name,
            min_idle_time=PENDING_TIMEOUT_MS,
            count=10,  # Recover max 10 per call
        )
        
        if result and result[1]:  # result[1] contains the messages
            recovered_messages = result[1]
            logger.info(
                "Recovered %d pending messages from stream %s",
                len(recovered_messages),
                stream_name,
            )
            return recovered_messages
        
        return []
        
    except Exception as exc:
        logger.error("Failed to recover pending messages: %s", exc)
        return []


async def get_consumer_group_status(
    redis_client: redis.Redis,
    stream_name: str,
    consumer_group: str,
) -> dict:
    """Get status of a consumer group (pending messages, consumers).
    
    Args:
        redis_client: Redis async client
        stream_name: Stream name
        consumer_group: Consumer group name
    
    Returns:
        Dict with consumer group info
    """
    try:
        pending = await redis_client.xpending(stream_name, consumer_group)
        
        if not pending:
            return {
                "stream": stream_name,
                "group": consumer_group,
                "pending_count": 0,
                "consumers": [],
            }
        
        # pending: [count, min_id, max_id, [consumers]]
        pending_count = pending.get("pending", 0)
        min_id = pending.get("min", "")
        max_id = pending.get("max", "")
        consumers = pending.get("consumers", [])
        
        # Format consumers info
        formatted_consumers = [
            {
                "name": consumer_name,
                "pending": int(consumer_data.get("pending", 0)),
            }
            for consumer_name, consumer_data in consumers.items()
        ]
        
        return {
            "stream": stream_name,
            "group": consumer_group,
            "pending_count": pending_count,
            "min_id": min_id,
            "max_id": max_id,
            "consumers": formatted_consumers,
        }
        
    except Exception as exc:
        logger.error("Failed to get consumer group status: %s", exc)
        return {
            "stream": stream_name,
            "group": consumer_group,
            "error": str(exc),
        }
