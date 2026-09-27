"""Transactional outbox: durable hand-off from Postgres to Redis Streams.

A19: the scoring endpoint called ``publish_event`` three times, fire-and-forget.
Each was wrapped in try/except, so a Redis blip produced a committed,
fully-scored transaction with no LLM report, no SHAP attribution and no merchant
embedding. The failure *was* logged, so the audit's "silently" was wrong, but
nothing could ever discover or repair the gap: the report endpoint would report
``pending`` forever and no reconciliation query existed.

Two properties this buys, and only the second was obvious:

1. **Durability.** The event is a row in the same transaction as the scored
   transaction, so it commits atomically with it. A relay publishes it later. If
   the API dies between commit and publish, the row is still there.
2. **No pre-commit race.** The events used to be published *before* the commit,
   because the real commit happens in the ``get_db`` teardown, after the handler
   returns. All three consumer tables have a hard foreign key to
   ``transactions.id``, so a worker that picked the message up inside that
   sub-millisecond window hit an FK violation and burned its retries against a
   transaction that was about to exist. Publishing strictly after the commit
   removes that window entirely.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.stream_publisher import publish_event
from src.models.outbox_event import OutboxEvent

logger = logging.getLogger(__name__)

#: How many rows one drain pass publishes. Bounded so a large backlog does not
#: monopolise the loop and starve the API's own work.
BATCH_SIZE = 100

#: Rows that have failed this many times are left alone rather than retried
#: forever. A payload that cannot be published is a bug, and an infinite retry
#: would keep the API's relay permanently busy with it.
MAX_ATTEMPTS = 10


def enqueue_event(
    db: AsyncSession,
    stream_name: str,
    payload: dict[str, Any],
) -> OutboxEvent:
    """Stage an event for publication. Caller must commit the session.

    Never raises and never touches Redis: the point is that the request path
    cannot fail because the event bus is down. That is the opposite of the
    fire-and-forget behaviour it replaces, where an outage cost three events per
    transaction.
    """
    try:
        event = OutboxEvent(
            stream_name=stream_name,
            payload=json.dumps(payload, default=str),
        )
        db.add(event)
        return event
    except Exception:
        # A serialisation failure must not roll back a scored transaction. The
        # transaction and its score are the valuable part; the event is
        # enrichment. Surfaced loudly because it means the payload has a type
        # json cannot handle.
        logger.exception(
            "Failed to stage outbox event for stream %s — the transaction will "
            "be committed without it",
            stream_name,
        )
        return None  # type: ignore[return-value]


async def drain_once(
    db: AsyncSession,
    *,
    batch_size: int = BATCH_SIZE,
) -> tuple[int, int]:
    """Publish one batch of pending events. Returns ``(published, failed)``.

    Called with its own session, after the producing transaction has committed —
    that ordering is what removes the pre-commit FK race.
    """
    result = await db.execute(
        select(OutboxEvent)
        .where(OutboxEvent.attempts < MAX_ATTEMPTS)
        .order_by(OutboxEvent.id)
        .limit(batch_size)
    )
    pending = list(result.scalars().all())
    if not pending:
        return (0, 0)

    published = 0
    failed = 0

    for event in pending:
        try:
            await publish_event(event.stream_name, json.loads(event.payload))
        except Exception as exc:
            failed += 1
            event.attempts += 1
            event.last_error = str(exc)[:500]
            logger.warning(
                "Outbox publish failed (id=%s, stream=%s, attempt=%s/%s): %s",
                event.id,
                event.stream_name,
                event.attempts,
                MAX_ATTEMPTS,
                exc,
            )
            continue

        published += 1
        # Delete rather than mark: this is a transport queue, and a row that has
        # been delivered has no further use. AuditEntry is the audit trail.
        await db.execute(delete(OutboxEvent).where(OutboxEvent.id == event.id))

    await db.commit()
    return (published, failed)


class OutboxRelay:
    """Background loop that drains the outbox into the Redis streams.

    Runs in the API process. A single instance is enough because publishing is
    idempotent from the caller's perspective: at-least-once delivery, and the
    consumers already delete-then-insert for SHAP attributions, so a duplicate
    is harmless there.
    """

    def __init__(
        self,
        session_factory: Any,
        *,
        interval: float = 0.5,
    ) -> None:
        self._session_factory = session_factory
        self._interval = interval
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def _run(self) -> None:
        logger.info("Outbox relay started (interval=%ss)", self._interval)
        while not self._stopping.is_set():
            try:
                async with self._session_factory() as session:
                    published, failed = await drain_once(session)
                if published or failed:
                    logger.info(
                        "Outbox drain: %s published, %s failed", published, failed
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # The relay must outlive any single failure, including a database
                # or Redis outage, or one blip silently stops all event delivery
                # until the next deploy.
                logger.warning("Outbox relay iteration failed: %s", exc)

            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                # asyncio.TimeoutError, not the builtin: on Python 3.10 they are
                # different classes, and catching the builtin let the timeout
                # propagate out of _run, killing the relay after exactly one
                # iteration. The symptom was the worst possible one for an
                # outbox: a single blip stopped all event delivery, silently,
                # until the next deploy.
                continue

        logger.info("Outbox relay stopped")

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
