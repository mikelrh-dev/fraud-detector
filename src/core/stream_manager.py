"""Redis Streams group management — consumer groups and legacy migration.

Consumer-group pattern (design D2): every worker type owns a dedicated
consumer group over its stream (``shap-workers`` on ``fraud:shap``, etc.).
``ensure_consumer_group`` makes group creation idempotent at worker startup
(XGROUP CREATE with MKSTREAM — creates the stream too if missing, tolerates
BUSYGROUP when the group already exists).

``migrate_legacy_list`` is the transition bridge (design D5 / FD-STREAM-004):
messages still sitting in the old list-based queue (enqueued before this
deploy) are drained into the new stream so nothing is lost mid-transition.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from redis.exceptions import ResponseError

logger = logging.getLogger(__name__)


async def ensure_consumer_group(
    redis_client: Any,
    stream_name: str,
    group_name: str,
) -> None:
    """Idempotently create a consumer group over ``stream_name``.

    Uses ``XGROUP CREATE <stream> <group> 0 MKSTREAM``: entry id 0 means the
    group reads the whole stream from the beginning (including entries that
    pre-date the group, e.g. migrated legacy messages), and MKSTREAM creates
    the stream key when it does not exist yet.

    Args:
        redis_client: Redis client (async).
        stream_name: e.g. ``fraud:shap``.
        group_name: e.g. ``shap-workers``.

    Raises:
        ResponseError: for errors other than BUSYGROUP (group exists — ok).
    """
    try:
        await redis_client.xgroup_create(
            stream_name, group_name, id="0", mkstream=True
        )
        logger.info(
            "Created consumer group %s on stream %s", group_name, stream_name
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
        logger.info(
            "Consumer group %s already exists on stream %s", group_name, stream_name
        )


async def migrate_legacy_list(
    redis_client: Any,
    legacy_list: str,
    stream_name: str,
    event_type: str,
) -> int:
    """Drain leftover messages from a legacy Redis list into the stream.

    Before this deploy the API pushed work onto plain lists (``fraud:shap``,
    ``fraud:embeddings``, ``fraud:reports``). Any message still queued there
    when a worker starts is re-appended to the new stream (XADD) so no work
    enqueued pre-transition is lost (FD-STREAM-004 / design D5).

    Args:
        redis_client: Redis client (async).
        legacy_list: the old list key to drain (e.g. ``fraud:reports``).
        stream_name: destination stream (e.g. ``fraud:llm``).
        event_type: event type stamped on each migrated entry.

    Returns:
        The number of migrated messages.
    """
    migrated = 0
    while True:
        raw = await redis_client.rpop(legacy_list)
        if raw is None:
            break
        payload = raw if isinstance(raw, str) else raw.decode("utf-8")
        fields = {
            "event_type": event_type,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "payload": payload,  # already a JSON string — do not re-encode
        }
        await redis_client.xadd(stream_name, fields)
        migrated += 1

    if migrated:
        logger.info(
            "Migrated %d legacy messages from %s into stream %s",
            migrated,
            legacy_list,
            stream_name,
        )
    return migrated
