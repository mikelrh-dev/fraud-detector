"""Health check endpoints for API and workers."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    """Readiness check — DB and Redis are reachable."""
    checks = {}

    # Check DB
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    # Check Redis
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

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
            workers[stream_name] = {
                "status": "error",
                "error": str(exc),
            }

    return {
        "workers": workers,
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

    return Response(
        content="\n".join(lines),
        media_type="text/plain",
    )
