"""Health check endpoints for API and workers."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import counters
from src.core.dependencies import get_db, get_redis
from src.core.stream_dlq import get_consumer_group_status
from src.models.fraud_score import FraudScore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# A worker backlog above this many unacked messages means the consumer is not
# keeping up; surfaced as "backed_up" so operators / alerts can react.
PENDING_BACKLOG_THRESHOLD = 100

# --- SHAP worker liveness -----------------------------------------------------
#
# `/health/workers` measures queue depth, and a worker that drains `fraud:shap`
# without producing anything looks perfect on that measure: pending goes to zero,
# stream length is bounded by MAXLEN, and every field reads healthy. That is the
# A18 failure — the worker acked every message while writing zero
# `shap_attributions` rows, against 26 fraud/review transactions, and nothing
# said so. The counters block is a fast signal, but counters are in-process: a
# restarted worker resets them, and a worker that cannot even reach Redis to
# increment a counter leaves nothing to read.
#
# So this reports an OUTCOME rather than an activity: did this deployment
# actually produce attributions for the fraud/review traffic it received? The
# worker stamps `shap:health:last_attribution_ts` after every committed
# attribution; below, that stamp is compared against recent traffic. Draining
# without producing is no longer expressible as a healthy reading.
#
# The key literal is duplicated from `src/workers/shap_worker.py` (LIVENESS_KEY),
# mirroring how `STREAM_NAME` is already duplicated in the stream table below.

#: Duplicated from `shap_worker.LIVENESS_KEY`.
SHAP_LIVENESS_KEY = "shap:health:last_attribution_ts"

#: How far back to look for fraud/review traffic that SHOULD have produced an
#: attribution.
#:
#: 15 minutes. Long enough that a low-volume deployment is not permanently
#: parked in the "no traffic" branch — where the check reports healthy for the
#: uninformative reason that there was nothing to verify, which is how a real
#: outage could hide in a quiet system. Short enough that the verdict is still
#: relevant by the next scrape.
SHAP_LIVENESS_TRAFFIC_WINDOW_SECONDS = 15 * 60

#: How old the last attribution may be, given traffic in that window, before the
#: worker is called degraded.
#:
#: 2 hours = window (15 min) + 1 h + 45 min. The arithmetic matters more than the
#: number:
#:
#: - WINDOW. A healthy worker's newest attribution can never be older than the
#:   window. Attributions are written after their transaction, so if traffic
#:   exists in [now-W, now] the newest one was stamped no earlier than now-W.
#:   Window alone would therefore be the tightest correct bound.
#: - COMPUTE LAG. The stamp trails its transaction: ~0.09 s warm, 4-7 s for the
#:   first explanation after a cold start, and up to ~30 s down the retry/DLQ
#:   path (MAX_RETRIES=3 with 1+2+4 s backoff). Small, but not zero — a cold
#:   start must not be able to trip the check.
#: - CLOCK SKEW. The worker stamps with its own clock and this comparison uses the
#:   API's. A worker running an hour behind would otherwise read as stale, so the
#:   threshold carries a full hour of skew headroom. That is deliberately generous:
#:   these processes sit on one host, so an hour of skew means something is badly
#:   wrong elsewhere and reporting it as stale is the correct, useful answer.
#:   A worker running AHEAD yields a negative age, which reads as fresh — a
#:   missed detection, not a false alarm, which is the right side to err on for
#:   a liveness probe.
#:
#: The cost of all that headroom is detection latency: a broken worker is named
#: here on a slower cadence than the counters and DLQ depth catch it. That is the
#: intended trade. A false "degraded" pages someone for nothing, and a page that
#: cries wolf is a page that stops being read — at which point this signal, like
#: the counters, becomes decoration. Slow and never wrong beats fast and noisy.
SHAP_LIVENESS_STALE_AFTER_SECONDS = 2 * 60 * 60


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


def _as_epoch_seconds(raw: object) -> float | None:
    """Read the beacon as a number, whatever shape Redis handed back.

    redis-py returns bytes when the client is built without
    ``decode_responses=True`` and str when it is, and the worker does not care
    which it gets. An unparseable value yields None, which reads downstream as
    "absent" — the honest verdict, since a beacon nobody can read is a beacon
    nobody can trust.
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return None
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


async def _count_recent_fraud_review(db: AsyncSession) -> int | None:
    """Count fraud/review transactions in the window — the traffic that ought
    to have produced attributions.

    ``fraud_scores.classification in ('fraud', 'review')`` is exactly the
    condition `create_and_score_transaction` uses to publish to ``fraud:shap``,
    so this counts the messages the worker was actually handed. Counting
    something broader (all transactions) would make the check fire during quiet
    periods when no SHAP work existed to do.

    None means the query could not run — reported as unverified rather than
    guessed at, because a zero here would read as "no traffic" and quietly turn
    the check into a no-op.
    """
    window_start = datetime.now(tz=timezone.utc) - timedelta(
        seconds=SHAP_LIVENESS_TRAFFIC_WINDOW_SECONDS
    )
    try:
        result = await db.execute(
            select(func.count())
            .select_from(FraudScore)
            .where(
                FraudScore.classification.in_(("fraud", "review")),
                FraudScore.created_at >= window_start,
            )
        )
        # `await db.execute(...)` yields a CursorResult, whose `.scalar()` is
        # SYNCHRONOUS — only the execute is awaitable. Writing `await` here
        # raises TypeError, the broad except below swallows it, and this check
        # reports `checked: false` forever: green, silent, and dead. Matches
        # monitoring.py, which reads its counts the same way.
        return int(result.scalar() or 0)
    except Exception:
        logger.warning("SHAP liveness: traffic query failed", exc_info=True)
        return None


async def _shap_liveness(db: AsyncSession, redis_client: Redis) -> dict:
    """Compare the worker's last committed attribution against live traffic.

    Three outcomes, two labels:

    - No traffic in the window -> ``ok``. There was no work to produce; absence
      of output is the expected reading, not a fault.
    - Traffic and a fresh stamp -> ``ok``. The worker is demonstrably producing.
    - Traffic and a stale or absent stamp -> ``degraded``. This is the silence:
      fraud/review transactions arrived, the worker drained them, and nothing
      came out the other side.

    When the check itself cannot run (database or Redis unreachable) it reports
    ``checked: false`` and stays ``ok``. It must not claim ``degraded`` — that
    would blame the SHAP worker for an API-side outage — and it must not raise,
    because a probe that 500s takes the whole worker topology report down with
    it. ``checked: false`` plus ``reason`` says plainly that the question went
    unanswered; ``/health/ready`` is where database and Redis reachability are
    reported, so the failure is not hidden, only not duplicated.
    """
    report: dict = {
        "status": "ok",
        "checked": False,
        "traffic_window_seconds": SHAP_LIVENESS_TRAFFIC_WINDOW_SECONDS,
        "stale_after_seconds": SHAP_LIVENESS_STALE_AFTER_SECONDS,
        "fraud_review_count": None,
        "last_attribution_ts": None,
        "last_attribution_age_seconds": None,
        "reason": "",
    }

    traffic = await _count_recent_fraud_review(db)
    if traffic is None:
        report["reason"] = (
            "Traffic query unavailable — liveness not evaluated. "
            "Check /health/ready for database reachability."
        )
        return report

    report["fraud_review_count"] = traffic

    try:
        raw = await redis_client.get(SHAP_LIVENESS_KEY)
    except Exception as exc:
        logger.warning("SHAP liveness: beacon read failed", exc_info=True)
        report["reason"] = (
            f"Liveness beacon unreadable ({type(exc).__name__}) — liveness not "
            "evaluated. Check /health/ready for Redis reachability."
        )
        return report

    stamp = _as_epoch_seconds(raw)
    if stamp is not None:
        report["last_attribution_ts"] = stamp
        report["last_attribution_age_seconds"] = round(
            datetime.now(tz=timezone.utc).timestamp() - stamp, 3
        )

    report["checked"] = True

    if traffic == 0:
        report["reason"] = (
            f"No fraud/review transactions in the last "
            f"{SHAP_LIVENESS_TRAFFIC_WINDOW_SECONDS}s — nothing to verify."
        )
        return report

    if stamp is None:
        report["status"] = "degraded"
        report["reason"] = (
            f"{traffic} fraud/review transaction(s) in the last "
            f"{SHAP_LIVENESS_TRAFFIC_WINDOW_SECONDS}s but {SHAP_LIVENESS_KEY} "
            f"is absent or unreadable — the worker is draining fraud:shap "
            f"without writing attributions."
        )
        return report

    age = report["last_attribution_age_seconds"]
    if age > SHAP_LIVENESS_STALE_AFTER_SECONDS:
        report["status"] = "degraded"
        report["reason"] = (
            f"{traffic} fraud/review transaction(s) in the last "
            f"{SHAP_LIVENESS_TRAFFIC_WINDOW_SECONDS}s, but the last attribution "
            f"was written {age:.0f}s ago (stale after "
            f"{SHAP_LIVENESS_STALE_AFTER_SECONDS}s)."
        )
        return report

    report["reason"] = (
        f"Last attribution written {age:.0f}s ago for {traffic} fraud/review "
        f"transaction(s) in the last {SHAP_LIVENESS_TRAFFIC_WINDOW_SECONDS}s."
    )
    return report


@router.get("/health/workers", status_code=status.HTTP_200_OK)
async def workers_health_check(
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> dict:
    """Workers health check — consumer lag for all worker streams, plus whether
    the SHAP worker is actually producing.
    """
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
        # A18, second half: counters are in-process and reset on restart, so they
        # cannot be the only thing standing between a drained worker and a green
        # board. This one compares the last attribution this worker actually wrote
        # against the fraud/review traffic it was handed.
        "shap_liveness": await _shap_liveness(db, redis_client),
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
