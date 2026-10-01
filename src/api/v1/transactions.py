"""Transaction endpoints - CRUD with fraud scoring pipeline.

The fraud scoring pipeline (rule engine -> feature engine -> ML model ->
ensemble) lives in ``src.services.scoring_service.ScoringService``; this
module orchestrates I/O around it. Ownership model (R1-003): analysts see
only their own transactions; admins see everything. Foreign objects are
reported as 404 to avoid leaking existence.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.rate_limit import check_rate_limit
from src.core.config import settings
from src.core.dependencies import (
    get_current_user,
    get_db,
    get_redis,
    get_velocity_store,
    require_role,
)
from src.core.redis import get_redis as get_shared_redis
from src.models.fraud_alert import AlertStatus, FraudAlert
from src.models.fraud_score import FraudClassification, FraudScore
from src.models.shap_attribution import ShapAttribution
from src.models.transaction import Transaction, TransactionStatus
from src.schemas.monitoring import ModelStatus
from src.schemas.scoring import ScoreResponse
from src.schemas.transaction import (
    ScoreBreakdown,
    ShapContribution,
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
)
from src.services.audit import AuditService
from src.services.ensemble import EnsembleScorer
from src.services.feature_engine import FeatureEngine
from src.services.graph_service import FraudGraphService
from src.services.ml_model import MLModelService
from src.services.outbox import enqueue_event
from src.services.rule_engine import RuleEngine
from src.services.scoring_service import ScoringService
from src.services.shap_service import ShapService
from src.services.transaction import (
    create_transaction,
    delete_transaction,
    get_scores_for_transactions,
    get_transaction,
)
from src.services.velocity_store import VelocityStore

logger = logging.getLogger(__name__)

# A22: how many recent amounts feed the std_amount feature. Bounds an
# otherwise unbounded read on every scored transaction.
STD_AMOUNT_SAMPLE_SIZE = 500

router = APIRouter(
    prefix="/transactions",
    tags=["transactions"],
    dependencies=[Depends(check_rate_limit)],
)


def _classification_str(value: FraudClassification | str) -> str:
    """Normalize FraudClassification to its string value."""
    if isinstance(value, str):
        return value
    return value.value


def _is_admin(current_user: dict) -> bool:
    """True if the authenticated user has the admin role."""
    return current_user.get("role") == "admin"


def _current_user_uuid(current_user: dict) -> uuid.UUID:
    """Parse the authenticated user's id from the JWT subject claim."""
    return uuid.UUID(str(current_user["user_id"]))


def _to_float(value: object) -> float:
    """Total Decimal/str -> float conversion; never raises."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _determine_friction_level(
    score: float, classification: str, threshold: float
) -> tuple[str, str | None]:
    """Determine dynamic friction level and action based on risk score and classification.

    Args:
        score: Ensemble risk score (0-100).
        classification: Fraud classification string.
        threshold: Dynamic threshold for the transaction's amount tier.

    Returns:
        (friction_level, action) tuple where:
        - friction_level: "allow" | "challenge" | "block"
        - action: specific action or None
    """
    if classification == "fraud":
        # Fraud: automatic block
        return "block", "block_transaction"

    if classification == "review":
        # Grey zone: challenge user
        # Use the midpoint of the review band [threshold*0.75, threshold]
        # to decide between stronger (3D Secure) and lighter (SMS) friction.
        review_midpoint = threshold * 0.875
        if score >= review_midpoint:
            return "challenge", "request_3d_secure"
        else:
            return "challenge", "request_sms"

    # Legitimate: no friction
    return "allow", None


_rule_engine = RuleEngine()
_ensemble_scorer = EnsembleScorer()
_audit_service = AuditService()
_ml_service = MLModelService()
_feature_engine = FeatureEngine()
_shap_service = ShapService()
_graph_service = FraudGraphService()
# CV-001: scoring pipeline lives in a service. It holds the same component
# instances the tests monkeypatch (transactions_api._feature_engine etc.),
# so existing test contracts are preserved while the orchestration logic
# moves out of the endpoint.
_scoring_service = ScoringService(
    rule_engine=_rule_engine,
    feature_engine=_feature_engine,
    ml_service=_ml_service,
    ensemble_scorer=_ensemble_scorer,
)

# Load ML model at startup (synchronous, runs once)
_ml_service.load_model()


def ml_model_status() -> ModelStatus:
    """The one derivation of "is the ML model loaded?".

    Lives next to ``_ml_service`` because it reads that object, and both
    ``/health/ready`` (api/v1/health.py) and ``/monitoring/dashboard``
    (api/v1/monitoring.py) return its result, so the two endpoints read the
    same signal and cannot contradict each other.

    This function exists because the dashboard used to answer the literal
    ``"operational"`` without consulting anything: a panel could claim a
    working model while the readiness probe said ``not_loaded``, which is the
    same class of assertion-without-measurement this project keeps removing.

    Deliberately not wrapped in a try/except. A diagnostic that swallows its
    own failure and reports "ok" is worse than a 500, and ``is_available`` is
    a read-only property that only reads ``_model is not None`` — there is
    nothing here that can plausibly fail once the module has imported.
    """
    return ModelStatus.OK if _ml_service.is_available else ModelStatus.NOT_LOADED


@router.post("", response_model=ScoreResponse, status_code=status.HTTP_201_CREATED)
async def create_and_score_transaction(
    payload: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    velocity_store: VelocityStore = Depends(get_velocity_store),
    redis_client: Redis = Depends(get_redis),
) -> ScoreResponse:
    """Create a transaction and run the full scoring pipeline.

    The rule engine evaluates the transaction, the ensemble scorer
    combines scores, and if the result exceeds the threshold, a fraud
    alert is created.
    """
    # 0. Feature flag guard
    if not settings.fraud_detection_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fraud detection is currently disabled",
        )

    # 1. Create the transaction
    # F2: Always use the authenticated user's identity — ignore payload.user_id
    # (IDOR prevention). The payload field is deprecated and ignored.
    user_uuid = _current_user_uuid(current_user)
    try:
        txn = await create_transaction(
            db=db,
            amount=payload.amount,
            currency=payload.currency,
            merchant_name=payload.merchant_name,
            merchant_category=payload.merchant_category,
            card_last4=payload.card_last4,
            user_id=user_uuid,
        )
    except Exception:
        logger.exception("Failed to create transaction")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error processing request",
        )

    # 2. Velocity counters (Redis ZSET with PG fallback)
    await velocity_store.record_transaction(user_uuid, txn.id, txn.created_at)
    velocity_counts = await velocity_store.get_counts(user_uuid, db)

    # 2.5. User history via SQL aggregates (CV-004): push known_cards
    # (DISTINCT) and avg_amount to the database.  std_amount is computed
    # Python-side because SQLite (test runner) lacks func.stddev — this
    # keeps the test suite portable while still reducing data transfer.
    base_filter = (
        Transaction.user_id == user_uuid,
        Transaction.deleted_at.is_(None),
    )

    # Known cards: SELECT DISTINCT card_last4 (portable, no ORM entities).
    cards_result = await db.execute(
        select(Transaction.card_last4).where(*base_filter).distinct()
    )
    known_cards = sorted(cards_result.scalars().all())

    # Average amount: SELECT AVG(amount) (portable via func.avg).
    avg_result = await db.execute(
        select(func.avg(Transaction.amount)).where(*base_filter)
    )
    avg_amount = float(avg_result.scalars().one() or 0.0)

    # Std amount: fetch only the amount column (no entities) and compute
    # std Python-side for SQLite portability.
    #
    # A22: this had no LIMIT, so every scored transaction materialised the user's
    # entire amount history in memory just to take a standard deviation. On a
    # long-lived account that is an unbounded read on the hot path. Capped to the
    # most recent N, which is also the more meaningful window: the feature is a
    # deviation from the user's *current* typical behaviour, not from their
    # entire transaction history including behaviour they have since changed.
    amounts_result = await db.execute(
        select(Transaction.amount)
        .where(*base_filter)
        .order_by(Transaction.created_at.desc())
        .limit(STD_AMOUNT_SAMPLE_SIZE)
    )
    amounts = [float(a) for a in amounts_result.scalars().all()]

    # 3. Graph features — CPU-bound BFS runs off the event loop (R2)
    graph_features = await asyncio.to_thread(
        _graph_service.get_graph_features, str(user_uuid)
    )

    # 4. Build scoring inputs
    now = datetime.now(tz=timezone.utc)
    tx_data: dict[str, Any] = {
        "amount": payload.amount,
        "merchant_name": payload.merchant_name,
        "merchant_category": payload.merchant_category,
        "card_last4": payload.card_last4,
        "user_id": str(user_uuid),
        "timestamp": now.isoformat(),
        "country": "AR",  # simulate home country for demo purposes
    }
    user_history = {
        "avg_amount": avg_amount,
        "std_amount": float(np.std(amounts)) if len(amounts) > 1 else 0.0,
        "tx_count_last_5min": velocity_counts["5min"],
        "tx_count_last_1h": velocity_counts["1h"],
    }
    context: dict[str, Any] = {
        "recent_transactions": velocity_counts["5min"],
        "known_cards": known_cards,
        # From settings, not a literal in the request path (ML-01): extending
        # the list should not need a code change and a deploy. The default
        # preserves the previous three entries exactly, so scoring is
        # unchanged. rule_engine.py lowercases both sides before matching.
        "merchant_blacklist": settings.merchant_blacklist,
        "home_country": "AR",
        "graph_features": graph_features,
    }

    # 5. Scoring pipeline (CV-001 in service; CV-002 CPU-bound steps
    # are offloaded to a thread inside compute_scores)
    score = await _scoring_service.compute_scores(tx_data, context, user_history)
    rule_score, fired_rules = score.rule_score, score.fired_rules
    features = score.features
    ml_score = score.ml_score
    threshold = score.threshold
    ensemble_score = score.ensemble_score
    classification = score.classification
    layers_used = score.layers_used

    # 6. Persist the score
    fraud_score = FraudScore(
        transaction_id=txn.id,
        rule_score=rule_score,
        ml_score=ml_score,
        ensemble_score=ensemble_score,
        threshold=threshold,
        classification=FraudClassification(classification),
    )
    db.add(fraud_score)

    # 7. Create alert if fraud
    if classification == "fraud":
        alert = FraudAlert(
            transaction_id=txn.id,
            status=AlertStatus.OPEN,
            score=ensemble_score,
            threshold=threshold,
            classification=classification,
        )
        db.add(alert)

    # 8. Update transaction status
    status_map: dict[str, TransactionStatus] = {
        "legitimate": TransactionStatus.APPROVED,
        "review": TransactionStatus.FLAGGED,
        "fraud": TransactionStatus.BLOCKED,
    }
    txn.status = status_map.get(classification, TransactionStatus.PENDING)

    await db.flush()

    # 8.5. Update fraud graph: add transaction edges and mark fraudsters.
    # Runs after classification; the graph mutation is CPU/lock bound so it
    # happens in a thread, then the snapshot is persisted to Redis.
    try:
        await _graph_service.add_transaction_persisted(
            sender_id=str(user_uuid),
            receiver_id=f"merchant_{payload.merchant_name}",  # Treat merchant as receiver node
            card_id=payload.card_last4,
            is_fraud=(classification == "fraud"),
            redis_client=redis_client,
        )
    except Exception:
        logger.exception("Failed to update fraud graph")

    # 9. Record audit trail for the scoring decision
    await _audit_service.create_entry(
        db=db,
        action_type="transaction_scored",
        transaction_id=txn.id,
        user_id=user_uuid,
        details={
            "rule_score": rule_score,
            "ml_score": ml_score,
            "ensemble_score": ensemble_score,
            "threshold": threshold,
            "classification": classification,
            "fired_rules": fired_rules,
        },
    )

    # 10. Stage the LLM report event (A19: transactional outbox).
    #
    # These used to be three fire-and-forget publish_event calls wrapped in
    # try/except, so a Redis blip left a committed, fully-scored transaction
    # with no report, no SHAP attribution and no embedding — and nothing could
    # ever find the gap. Staging a row in this same session makes the event
    # commit atomically with the transaction, and the relay publishes it after.
    #
    # It also removes a race the audit did not name: publication happened
    # *before* the commit (the real commit is in the get_db teardown, after this
    # handler returns), and all three consumer tables have a hard FK to
    # transactions.id, so a worker picking the message up in that window hit a
    # foreign key violation and burned its retries.
    enqueue_event(
        db,
        "fraud:llm",
        {
            "transaction_id": str(txn.id),
            "score_breakdown": {
                "rule_score": rule_score,
                "ml_score": ml_score,
                "ensemble_score": ensemble_score,
                "threshold": threshold,
                "classification": classification,
                "fired_rules": fired_rules,
            },
            "transaction": {
                "id": str(txn.id),
                "amount": payload.amount,
                "currency": payload.currency,
                "merchant_name": payload.merchant_name,
                "merchant_category": payload.merchant_category,
            },
        },
    )

    # 11. Stage the SHAP attribution event (only for fraud/review).
    # Snapshots the EXACT feature vector used for scoring.
    if classification in ("fraud", "review"):
        enqueue_event(
            db,
            "fraud:shap",
            {
                "transaction_id": str(txn.id),
                "classification": classification,
                "features": features.tolist(),
                "feature_names": _feature_engine.get_feature_names(),
                "model_fingerprint": _shap_service.model_fingerprint(),
            },
        )

    # 12. Stage the merchant embedding event for spoofing detection.
    enqueue_event(
        db,
        "fraud:embeddings",
        {
            "transaction_id": str(txn.id),
            "merchant_name": payload.merchant_name,
        },
    )

    # 13. Determine dynamic friction level based on score and classification
    friction_level, action = _determine_friction_level(ensemble_score, classification, threshold)

    return ScoreResponse(
        transaction_id=txn.id,
        rule_score=rule_score,
        ml_score=ml_score,
        ensemble_score=ensemble_score,
        threshold=threshold,
        classification=classification,
        fired_rules=fired_rules,
        layers_used=list(layers_used),
        created_at=datetime.now(tz=timezone.utc),
        friction_level=friction_level,
        action=action,
    )


@router.get("", response_model=TransactionListResponse)
async def list_transactions_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    user_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TransactionListResponse:
    """List transactions with optional filters.

    Non-admin users are always scoped to their own transactions; requesting
    another user's id is rejected outright (R1-003).
    """
    if not _is_admin(current_user):
        own_id = _current_user_uuid(current_user)
        if user_id is not None and user_id != own_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot list another user's transactions",
            )
        user_id = own_id

    skip = (page - 1) * page_size

    query = select(Transaction).where(Transaction.deleted_at.is_(None))

    if status_filter:
        query = query.where(Transaction.status == status_filter)
    if user_id:
        query = query.where(Transaction.user_id == user_id)
    if date_from:
        query = query.where(Transaction.created_at >= date_from)
    if date_to:
        query = query.where(Transaction.created_at <= date_to)

    # Get total count — apply IDENTICAL filters to the count query (R4).
    # Use func.count() instead of len(.all()) for efficiency.
    count_query = select(func.count()).select_from(Transaction).where(
        Transaction.deleted_at.is_(None)
    )
    if status_filter:
        count_query = count_query.where(Transaction.status == status_filter)
    if user_id:
        count_query = count_query.where(Transaction.user_id == user_id)
    if date_from:
        count_query = count_query.where(Transaction.created_at >= date_from)
    if date_to:
        count_query = count_query.where(Transaction.created_at <= date_to)

    total = (await db.execute(count_query)).scalar_one()

    # Stable ordering: created_at DESC with id DESC as tiebreaker
    query = query.order_by(Transaction.created_at.desc(), Transaction.id.desc())
    query = query.offset(skip).limit(page_size)
    result = await db.execute(query)
    transactions = list(result.scalars().all())

    # Single batched score query over the page ids — never per-row (no N+1)
    scores = await get_scores_for_transactions(db, [t.id for t in transactions])

    items = []
    for t in transactions:
        score = scores.get(t.id)
        items.append(
            TransactionResponse(
                id=t.id,
                amount=_to_float(t.amount),
                currency=t.currency,
                merchant_name=t.merchant_name,
                merchant_category=t.merchant_category,
                card_last4=t.card_last4,
                status=t.status.value if hasattr(t.status, "value") else t.status,
                user_id=t.user_id,
                risk_score=score.ensemble_score if score else None,
                classification=(
                    _classification_str(score.classification) if score else None
                ),
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
        )

    return TransactionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction_endpoint(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TransactionResponse:
    """Get a single transaction by ID."""
    try:
        txn = await get_transaction(db, transaction_id)
    except Exception:
        logger.exception("Failed to get transaction %s", transaction_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error processing request",
        )
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    if not _is_admin(current_user) and str(txn.user_id) != current_user["user_id"]:
        # 404 (not 403) so the endpoint does not leak foreign ids' existence.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    scores = await get_scores_for_transactions(db, [transaction_id])
    score = scores.get(transaction_id)
    breakdown: ScoreBreakdown | None = None

    # FRD-SHP-001: one ordered query for attribution rows - only when a score
    # exists (unscored transactions skip it). Null when no rows exist.
    if score is not None:
        breakdown = ScoreBreakdown.model_validate(score)
        shap_result = await db.execute(
            select(ShapAttribution)
            .where(ShapAttribution.transaction_id == transaction_id)
            .order_by(ShapAttribution.rank)
        )
        rows = list(shap_result.scalars().all())
        if rows:
            assert breakdown is not None  # narrowed by `if score is not None`
            breakdown.shap_contributions = [
                ShapContribution(feature=row.feature, contribution=row.contribution)
                for row in rows
            ]

    return TransactionResponse(
        id=txn.id,
        amount=_to_float(txn.amount),
        currency=txn.currency,
        merchant_name=txn.merchant_name,
        merchant_category=txn.merchant_category,
        card_last4=txn.card_last4,
        status=txn.status.value if hasattr(txn.status, "value") else txn.status,
        user_id=txn.user_id,
        risk_score=score.ensemble_score if score else None,
        classification=_classification_str(score.classification) if score else None,
        scoring=breakdown,
        created_at=txn.created_at,
        updated_at=txn.updated_at,
    )


@router.get(
    "/{transaction_id}/embedding", response_model=dict, status_code=status.HTTP_200_OK
)
async def get_embedding_analysis(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get merchant embedding analysis results for a transaction.

    Returns spoofing detection results if available (may return 404 if
    the worker hasn't processed the transaction yet).
    """
    try:
        txn = await get_transaction(db, transaction_id)
    except Exception:
        logger.exception("Failed to get transaction %s for embedding", transaction_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error processing request",
        )
    if txn is None or (
        not _is_admin(current_user) and str(txn.user_id) != current_user["user_id"]
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    redis = get_shared_redis()
    try:
        result_key = f"embedding_result:{transaction_id}"
        result_json = await redis.get(result_key)

        if not result_json:
            return {
                "transaction_id": str(transaction_id),
                "status": "pending",
                "message": "Embedding analysis not yet completed",
            }

        import json

        result = json.loads(result_json)
        return result
    except Exception:
        logger.exception("Failed to retrieve embedding result for %s", transaction_id)
        return {
            "transaction_id": str(transaction_id),
            "status": "error",
            "message": "Failed to retrieve embedding result",
        }


@router.get("/graph/stats", response_model=dict, status_code=status.HTTP_200_OK)
async def get_graph_stats(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get fraud network graph statistics.

    Returns overall graph metrics: nodes, edges, density, known fraudsters.

    A7: this returned the whole-graph counts to any authenticated caller. The
    fraud graph is deliberately cross-user — that is what makes near-fraud
    detection work at all — so there is no meaningful per-user subset to return
    here. Scoping it is therefore not an option: the endpoint is admin-only.
    Per-user graph *features* remain available to everyone on
    `/transactions/{user_id}/graph-features`, which is the endpoint that
    actually feeds scoring.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Whole-graph statistics require an admin role",
        )
    try:
        stats = await asyncio.to_thread(_graph_service.get_stats)
        return {
            "status": "ok",
            "graph": stats,
        }
    except Exception:
        logger.exception("Failed to retrieve graph stats")
        return {
            "status": "error",
            "message": "Failed to retrieve graph stats",
        }


@router.get(
    "/{user_id}/graph-features", response_model=dict, status_code=status.HTTP_200_OK
)
async def get_user_graph_features(
    user_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get fraud network features for a specific user.

    Returns: is_near_fraud, degree_centrality, shortest_path_to_fraud, connected_fraudsters.
    """
    own_id = str(_current_user_uuid(current_user))
    if user_id != own_id and not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view another user's graph features",
        )
    try:
        features = await asyncio.to_thread(
            _graph_service.get_graph_features, user_id
        )
        return {
            "user_id": user_id,
            "graph_features": features,
        }
    except Exception:
        logger.exception(
            "Failed to retrieve graph features for user %s", user_id
        )
        return {
            "user_id": user_id,
            "status": "error",
            "message": "Failed to retrieve graph features",
        }


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction_endpoint(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
) -> None:
    """Soft-delete a transaction (admin only)."""
    txn = await delete_transaction(db, transaction_id)
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
