"""Async SHAP worker — consumes ``fraud:shap`` queue messages and computes
feature attribution with ``shap.TreeExplainer`` over the scored feature
vector snapshot (SHP-001).

Mirrors the LLM worker: BRPOP loop, per-message session, retry with
incremented ``retry_count`` (max 3), and audit entries ``shap_computed``
/ ``shap_failed``. ``shap`` is imported lazily via ShapService — when it
or the model is unavailable the worker logs a warning and continues the
loop instead of crashing (SHP-005).
"""

import asyncio
import json
import logging
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import delete

from src.core.database import async_session_maker
from src.core.redis import enqueue_for_retry, get_redis
from src.models.shap_attribution import ShapAttribution
from src.services.audit import AuditService
from src.services.shap_service import ShapService, ShapUnavailableError

logger = logging.getLogger(__name__)

QUEUE_NAME = "fraud:shap"
MAX_RETRIES = 3
BACKOFF_BASE = 3


async def process_shap_message(
    message: dict[str, Any],
    db: Any,
    shap_service: ShapService,
    max_retries: int = MAX_RETRIES,
    audit_service: AuditService | None = None,
) -> bool:
    """Process a single SHAP request from the queue.

    Computes contributions off the snapshot feature vector, persists the
    top-5 rows (delete-then-insert — idempotent, SHP-002) and writes the
    audit trail (SHP-004). CPU-bound work runs via ``asyncio.to_thread``
    so the event loop stays responsive (SHP-001).

    Returns:
        True if the message is fully processed (success or permanent
        failure — no re-enqueue), False if it must be re-enqueued.
    """
    transaction_id = message.get("transaction_id", "unknown")
    features = message.get("features", [])
    feature_names = message.get("feature_names")
    retry_count = message.get("retry_count", 0)
    audit = audit_service or AuditService()

    try:
        contributions = await asyncio.to_thread(
            shap_service.explain,
            features,
            feature_names,
        )
    except ShapUnavailableError as exc:
        # SHP-005: shap or the model is missing — skip, never retry.
        logger.warning(
            "SHAP unavailable for transaction %s: %s — skipping",
            transaction_id,
            exc,
        )
        return True
    except Exception as exc:
        logger.exception(
            "SHAP computation failed for transaction %s (retry %d/%d)",
            transaction_id,
            retry_count,
            max_retries,
        )
        if retry_count >= max_retries:
            await audit.create_entry(
                db=db,
                action_type="shap_failed",
                transaction_id=transaction_id,
                details={
                    "error_type": type(exc).__name__,
                    "retry_count": retry_count,
                    "error": str(exc),
                },
            )
            logger.warning(
                "Max retries reached for transaction %s — SHAP attribution failed",
                transaction_id,
            )
            return True
        return False

    # Idempotent: replace any previous rows, never duplicate (SHP-002).
    await db.execute(
        delete(ShapAttribution).where(
            ShapAttribution.transaction_id == transaction_id
        )
    )

    rows = [
        ShapAttribution(
            transaction_id=transaction_id,
            feature=contribution.feature,
            contribution=contribution.contribution,
            rank=rank,
        )
        for rank, contribution in enumerate(contributions, start=1)
    ]
    db.add_all(rows)
    await db.flush()

    await audit.create_entry(
        db=db,
        action_type="shap_computed",
        transaction_id=transaction_id,
        details={
            "rank_count": len(rows),
            "model_fingerprint": message.get("model_fingerprint"),
            "retry_count": retry_count,
        },
    )
    logger.info(
        "SHAP attribution computed for transaction %s (retry=%d)",
        transaction_id,
        retry_count,
    )
    return True


async def run_worker(
    redis_client: Redis | None = None,
    shap_service: ShapService | None = None,
    max_iterations: int | None = None,
) -> None:
    """Main worker loop — consume and process SHAP requests (BRPOP).

    Args:
        redis_client: Redis client instance. If None, creates a new one.
        shap_service: ShapService instance. If None, creates a new one.
        max_iterations: Optional limit for testing (None = run forever).
    """
    svc = shap_service or ShapService()
    r = redis_client or get_redis()

    logger.info("SHAP worker started — waiting for messages on %s", QUEUE_NAME)
    iterations = 0

    while max_iterations is None or iterations < max_iterations:
        try:
            result = await r.brpop([QUEUE_NAME], timeout=5)  # type: ignore[misc]
            if result is None:
                iterations += 1
                continue

            _, data = result
            message = json.loads(data)

            logger.info(
                "Processing SHAP request for transaction %s",
                message.get("transaction_id", "unknown"),
            )

            db = async_session_maker()
            try:
                processed = await process_shap_message(
                    message=message,
                    db=db,
                    shap_service=svc,
                )

                if not processed:
                    # Need retry — re-enqueue with incremented retry_count
                    await enqueue_for_retry(r, message, QUEUE_NAME)

                await db.commit()
            except Exception:
                await db.rollback()
                raise
            finally:
                await db.close()

        except json.JSONDecodeError:
            logger.warning("Malformed message in queue — skipping")
        except Exception as exc:
            logger.exception("Unexpected error in worker loop: %s", exc)

        iterations += 1

    logger.info("SHAP worker stopped after %d iterations", iterations)


if __name__ == "__main__":
    asyncio.run(run_worker())
