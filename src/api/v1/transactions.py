"""Transaction endpoints — CRUD with fraud scoring pipeline."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.rate_limit import check_rate_limit
from src.core.config import settings
from src.core.dependencies import get_current_user, get_db, get_velocity_store, require_role
from src.core.redis import enqueue
from src.core.stream_publisher import publish_event
from src.models.fraud_alert import AlertStatus, FraudAlert
from src.models.fraud_score import FraudClassification, FraudScore
from src.models.shap_attribution import ShapAttribution
from src.models.transaction import Transaction, TransactionStatus
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
from src.services.rule_engine import RuleEngine
from src.services.shap_service import ShapService
from src.services.transaction import (
    create_transaction,
    delete_transaction,
    get_scores_for_transactions,
    get_transaction,
)
from src.services.velocity_store import VelocityStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/transactions",
    tags=["transactions"],
    dependencies=[Depends(check_rate_limit)],
)


def _classification_str(value: FraudClassification | str) -> str:
    """Normalize FraudClassification to its string value."""
    return value.value if hasattr(value, "value") else value


def _determine_friction_level(score: float, classification: str) -> tuple[str, str | None]:
    """Determine dynamic friction level and action based on risk score and classification.
    
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
        # In production, this would be configurable (3D Secure, SMS, biometric)
        if score >= 60:
            # Higher risk in review zone: require stronger authentication
            return "challenge", "request_3d_secure"
        else:
            # Lower risk in review zone: SMS is sufficient
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

# Load ML model at startup (synchronous, runs once)
_ml_service.load_model()


@router.post("", response_model=ScoreResponse, status_code=status.HTTP_201_CREATED)
async def create_and_score_transaction(
    payload: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    velocity_store: VelocityStore = Depends(get_velocity_store),
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
    txn = await create_transaction(
        db=db,
        amount=payload.amount,
        currency=payload.currency,
        merchant_name=payload.merchant_name,
        merchant_category=payload.merchant_category,
        card_last4=payload.card_last4,
        user_id=payload.user_id,
    )

    # 2. Build context for rule engine
    # Record the txn in the velocity store (Redis ZSET), then read real
    # 5min/1h counts. This replaces the per-request 5-minute Postgres scan
    # (Query A); counters fall back to Postgres when Redis is unavailable.
    await velocity_store.record_transaction(payload.user_id, txn.id, txn.created_at)
    velocity_counts = await velocity_store.get_counts(payload.user_id, db)

    # All user's non-deleted transactions for known cards
    all_user_query = select(Transaction).where(
        Transaction.user_id == payload.user_id,
        Transaction.deleted_at.is_(None),
    )
    all_user_result = await db.execute(all_user_query)
    all_user_txns = list(all_user_result.scalars().all())
    known_cards = list({t.card_last4 for t in all_user_txns if t.card_last4})

    # 3. Get graph features (fraud network analysis) — async
    graph_features = await _graph_service.get_graph_features(str(payload.user_id))

    # 3.5. Rule engine evaluation with timestamp and context
    now = datetime.now(tz=timezone.utc)
    tx_data: dict[str, Any] = {
        "amount": payload.amount,
        "merchant_name": payload.merchant_name,
        "merchant_category": payload.merchant_category,
        "card_last4": payload.card_last4,
        "user_id": str(payload.user_id),
        "timestamp": now.isoformat(),
        "country": "AR",  # simulate home country for demo purposes
    }
    context: dict[str, Any] = {
        "recent_transactions": velocity_counts["5min"],
        "known_cards": known_cards,
        "merchant_blacklist": ["crypto exchange pro", "online gambling", "money transfer now"],
        "home_country": "AR",
        "graph_features": graph_features,  # Add graph context for rules
    }
    rule_score, fired_rules = _rule_engine.evaluate(tx_data, context)

    # 4. ML scoring via XGBoost
    user_history = {
        "avg_amount": float(np.mean([float(t.amount) for t in all_user_txns])) if all_user_txns else 0.0,
        "std_amount": float(np.std([float(t.amount) for t in all_user_txns])) if len(all_user_txns) > 1 else 0.0,
        "tx_count_last_5min": velocity_counts["5min"],
        "tx_count_last_1h": velocity_counts["1h"],
    }
    features = _feature_engine.transform(tx_data, user_history=user_history)
    ml_score = _ml_service.predict(features)

    # 5. Ensemble scoring
    threshold = _ensemble_scorer.get_threshold(payload.amount)
    ensemble_score = _ensemble_scorer.combine(
        rule_score=rule_score,
        ml_score=ml_score,
    )
    classification = _ensemble_scorer.classify(ensemble_score, threshold)

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

    # 8.5. Update fraud graph: add transaction edges and mark fraudsters (async)
    # This happens AFTER classification is made
    try:
        await _graph_service.add_transaction(
            sender_id=str(payload.user_id),
            receiver_id=f"merchant_{payload.merchant_name}",  # Treat merchant as receiver node
            card_id=payload.card_last4,
            is_fraud=(classification == "fraud"),
        )
    except Exception:
        logger.exception("Failed to update fraud graph")

    # 9. Record audit trail for the scoring decision
    await _audit_service.create_entry(
        db=db,
        action_type="transaction_scored",
        transaction_id=txn.id,
        user_id=payload.user_id,
        details={
            "rule_score": rule_score,
            "ml_score": ml_score,
            "ensemble_score": ensemble_score,
            "threshold": threshold,
            "classification": classification,
            "fired_rules": fired_rules,
        },
    )

    # 10. Publish LLM report event to Redis Stream (best-effort, non-blocking)
    try:
        await publish_event("fraud:llm", {
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
        })
    except Exception:
        logger.exception("Failed to publish LLM event")

    # 11. Publish SHAP attribution event to Redis Stream (best-effort, only for fraud/review)
    # Snapshots the EXACT feature vector used for scoring
    if classification in ("fraud", "review"):
        try:
            await publish_event("fraud:shap", {
                "transaction_id": str(txn.id),
                "classification": classification,
                "features": features.tolist(),
                "feature_names": _feature_engine.get_feature_names(),
                "model_fingerprint": _shap_service.model_fingerprint(),
            })
        except Exception:
            logger.exception("Failed to publish SHAP event")

    # 12. Publish merchant embedding event for spoofing detection (best-effort)
    try:
        await publish_event("fraud:embeddings", {
            "transaction_id": str(txn.id),
            "merchant_name": payload.merchant_name,
        })
    except Exception:
        logger.exception("Failed to publish embedding event")

    # 13. Determine dynamic friction level based on score and classification
    friction_level, action = _determine_friction_level(ensemble_score, classification)

    return ScoreResponse(
        transaction_id=txn.id,
        rule_score=rule_score,
        ml_score=ml_score,
        ensemble_score=ensemble_score,
        threshold=threshold,
        classification=classification,
        fired_rules=fired_rules,
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
    """List transactions with optional filters."""
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

    # Get total count
    count_query = select(Transaction.id).where(Transaction.deleted_at.is_(None))
    if status_filter:
        count_query = count_query.where(Transaction.status == status_filter)
    if user_id:
        count_query = count_query.where(Transaction.user_id == user_id)

    total_result = await db.execute(count_query)
    total = len(total_result.all())

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
                amount=float(t.amount),
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
    txn = await get_transaction(db, transaction_id)
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    scores = await get_scores_for_transactions(db, [transaction_id])
    score = scores.get(transaction_id)
    scoring: ScoreBreakdown | None = None

    # FRD-SHP-001: one ordered query for attribution rows — only when a score
    # exists (unscored transactions skip it). Null when no rows exist.
    if score is not None:
        scoring = ScoreBreakdown.model_validate(score)
        shap_result = await db.execute(
            select(ShapAttribution)
            .where(ShapAttribution.transaction_id == transaction_id)
            .order_by(ShapAttribution.rank)
        )
        rows = list(shap_result.scalars().all())
        if rows:
            scoring.shap_contributions = [
                ShapContribution(feature=row.feature, contribution=row.contribution)
                for row in rows
            ]

    return TransactionResponse(
        id=txn.id,
        amount=float(txn.amount),
        currency=txn.currency,
        merchant_name=txn.merchant_name,
        merchant_category=txn.merchant_category,
        card_last4=txn.card_last4,
        status=txn.status.value if hasattr(txn.status, "value") else txn.status,
        user_id=txn.user_id,
        risk_score=score.ensemble_score if score else None,
        classification=_classification_str(score.classification) if score else None,
        scoring=scoring,
        created_at=txn.created_at,
        updated_at=txn.updated_at,
    )


@router.get("/{transaction_id}/embedding", response_model=dict, status_code=status.HTTP_200_OK)
async def get_embedding_analysis(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get merchant embedding analysis results for a transaction.
    
    Returns spoofing detection results if available (may return 404 if
    the worker hasn't processed the transaction yet).
    """
    from src.core.redis import redis_client
    
    try:
        result_key = f"embedding_result:{transaction_id}"
        result_json = await redis_client.get(result_key)
        
        if not result_json:
            return {
                "transaction_id": str(transaction_id),
                "status": "pending",
                "message": "Embedding analysis not yet completed",
            }
        
        import json
        result = json.loads(result_json)
        return result
    except Exception as exc:
        logger.exception("Failed to retrieve embedding result: %s", exc)
        return {
            "transaction_id": str(transaction_id),
            "status": "error",
            "message": str(exc),
        }


@router.get("/graph/stats", response_model=dict, status_code=status.HTTP_200_OK)
async def get_graph_stats(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get fraud network graph statistics.
    
    Returns overall graph metrics: nodes, edges, density, known fraudsters.
    """
    try:
        stats = await _graph_service.get_stats()
        return {
            "status": "ok",
            "graph": stats,
        }
    except Exception as exc:
        logger.exception("Failed to retrieve graph stats: %s", exc)
        return {
            "status": "error",
            "message": str(exc),
        }


@router.get("/{user_id}/graph-features", response_model=dict, status_code=status.HTTP_200_OK)
async def get_user_graph_features(
    user_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get fraud network features for a specific user.
    
    Returns: is_near_fraud, degree_centrality, shortest_path_to_fraud, connected_fraudsters.
    """
    try:
        features = await _graph_service.get_graph_features(user_id)
        return {
            "user_id": user_id,
            "graph_features": features,
        }
    except Exception as exc:
        logger.exception("Failed to retrieve graph features for user %s: %s", user_id, exc)
        return {
            "user_id": user_id,
            "status": "error",
            "message": str(exc),
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
