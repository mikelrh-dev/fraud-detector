"""Health check endpoints for API and workers."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import counters
from src.core.dependencies import get_db, get_redis
from src.core.stream_dlq import get_consumer_group_status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# A worker backlog above this many unacked messages means the consumer is not
# keeping up; surfaced as "backed_up" so operators / alerts can react.
PENDING_BACKLOG_THRESHOLD = 100


# Note: The /health endpoint is defined in main.py for backward compatibility.
# This router provides /health/ready, /health/workers, and /metrics.


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check(
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> dict:
    """Readiness check — DB and Redis are reachable, and the ML layer is loaded.

    A6: this endpoint is unauthenticated, so it used to return ``str(exc)`` on
    failure. A driver exception can carry the database username, the host, the
    SQLSTATE and sometimes the offending statement, which is reconnaissance for
    anyone who can reach the port. The full exception is now logged
    server-side, where the operator running the container can read it; the
    response carries only the exception *type*, which is enough to tell a
    refused connection from a missing table without handing over the details.
    """
    checks: dict[str, str] = {}

    # Check DB
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("Readiness: database check failed", exc_info=True)
        checks["database"] = f"error: {type(exc).__name__}"

    # Check Redis
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.error("Readiness: redis check failed", exc_info=True)
        checks["redis"] = f"error: {type(exc).__name__}"

    # A17: the model file is baked into the image now, but a stale or truncated
    # artifact still loads as "absent" and makes predict() return 0.0 for the
    # whole ML layer. Surface it: a scoring service quietly contributing nothing
    # is not something an operator should have to infer from score drift.
    #
    # The value comes from `ml_model_status()` so this endpoint and
    # GET /monitoring/dashboard read the same signal. They used to disagree:
    # the dashboard answered "operational" without asking, so a panel could
    # report a healthy model while this check said `not_loaded`.
    try:
        from src.api.v1.transactions import ml_model_status

        checks["ml_model"] = ml_model_status()
    except Exception as exc:
        logger.error("Readiness: ML model check failed", exc_info=True)
        checks["ml_model"] = f"error: {type(exc).__name__}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/health/workers", status_code=status.HTTP_200_OK)
async def workers_health_check(
    redis_client: Redis = Depends(get_redis),
) -> dict:
    """Workers health check — consumer lag for all worker streams."""
    streams = [
        ("fraud:llm", "llm-workers", "llm-worker-1"),
        ("fraud:shap", "shap-workers", "shap-worker-1"),
        ("fraud:embeddings", "embedding-workers", "embedding-worker-1"),
    ]

    workers = {}
    for stream_name, group_name, consumer_name in streams:
        try:
            stream_len = await redis_client.xlen(stream_name)
            status = await get_consumer_group_status(
                redis_client, stream_name, group_name
            )
            pending_count = int(status.get("pending_count", 0) or 0)
            workers[stream_name] = {
                "stream_length": stream_len,
                "pending": pending_count,
                "status": "ok" if pending_count < PENDING_BACKLOG_THRESHOLD else "backed_up",
            }
        except Exception as exc:
            # A6: unauthenticated endpoint, so the message went to whoever can
            # reach the port. Log it in full, return only the type.
            logger.error("Worker health check failed for %s", stream_name, exc_info=True)
            workers[stream_name] = {
                "status": "error",
                "error": type(exc).__name__,
            }

    return {
        "workers": workers,
        # A18: a running-but-misconfigured worker leaves no consumer-group
        # backlog, so the fields above all read healthy. These counters are the
        # only signal that distinguishes it.
        "counters": counters.snapshot(),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/metrics")
async def prometheus_metrics(
    redis_client: Redis = Depends(get_redis),
) -> Response:
    """Prometheus metrics endpoint — consumer lag for all worker streams.

    Exposes metrics in Prometheus text format for scraping.
    """
    streams = [
        ("fraud:llm", "llm-workers", "llm-worker-1", "llm"),
        ("fraud:shap", "shap-workers", "shap-worker-1", "shap"),
        ("fraud:embeddings", "embedding-workers", "embedding-worker-1", "embedding"),
    ]

    lines = [
        "# HELP fraud_detector_stream_length Number of messages in the stream",
        "# TYPE fraud_detector_stream_length gauge",
        "# HELP fraud_detector_pending_messages Number of pending messages per worker",
        "# TYPE fraud_detector_pending_messages gauge",
    ]

    for stream_name, group_name, consumer_name, label in streams:
        try:
            stream_len = await redis_client.xlen(stream_name)
            status = await get_consumer_group_status(
                redis_client, stream_name, group_name
            )
            pending_count = int(status.get("pending_count", 0) or 0)
            lines.append(
                f'fraud_detector_stream_length{{stream="{label}"}} {stream_len}'
            )
            lines.append(
                f'fraud_detector_pending_messages{{worker="{label}"}} {pending_count}'
            )
        except Exception as exc:
            logger.warning("Failed to collect metrics for %s: %s", stream_name, exc)
            lines.append(f'fraud_detector_stream_length{{stream="{label}"}} 0')
            lines.append(f'fraud_detector_pending_messages{{worker="{label}"}} 0')

    # A18: failure counters that consumer lag cannot express.
    lines.append(
        "# HELP fraud_detector_worker_failures_total "
        "Messages a worker could not process, by reason"
    )
    lines.append("# TYPE fraud_detector_worker_failures_total counter")
    for counter_name, value in sorted(counters.snapshot().items()):
        lines.append(f"fraud_detector_worker_failures_total{{reason=\"{counter_name}\"}} {value}")

    return Response(
        content="\n".join(lines),
        media_type="text/plain",
    )
