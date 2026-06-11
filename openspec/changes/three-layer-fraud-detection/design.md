# Design: Three-Layer Fraud Detection

## Technical Approach

A three-layer fraud scoring pipeline: **Rule Engine** (deterministic, code-based) → **ML Anomaly Detection** (Isolation Forest via scikit-learn Pipeline) → **Ensemble Scoring** (weighted average with dynamic thresholds). Fraud-classified transactions trigger async LLM report generation via Redis queue. JWT auth protects all endpoints. React dashboard provides analyst workflow.

Data flows synchronously through rules + ensemble, then asynchronously through ML (batch) and LLM (queue). Every decision is captured in an immutable audit trail.

## Architecture Decisions

### Decision: Rule Storage Strategy

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Code-based rules | Fast, type-safe, requires deploy for changes | **CHOSEN** — v1 stability first |
| DB-driven rules | Runtime editable, needs cache invalidation | Deferred to v2 |

**Rationale**: Code-based rules eliminate a class of runtime bugs (malformed rules, stale cache). Rules are business logic — they belong in code, reviewed via PR.

### Decision: ML Model Choice

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Isolation Forest | Unsupervised, fast, explainable | **CHOSEN** |
| Autoencoder | Captures non-linear patterns, needs GPU | Deferred — infra cost |
| XGBoost | Highest accuracy with labels, needs labeled data | Deferred — insufficient labeled data |

**Rationale**: Isolation Forest is unsupervised — works with the Kaggle dataset's natural anomaly structure. Serializes cleanly with joblib.

### Decision: Ensemble Strategy

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Weighted average | Simple, tunable, explainable | **CHOSEN** |
| Stacking meta-model | Learns optimal weights, needs labeled data | Deferred |

**Rationale**: `ensemble = w_rules * rule_score + w_ml * ml_score`. Weights stored in config. Dynamic thresholds by amount tier (lower threshold for higher amounts).

### Decision: LLM Processing

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Redis queue + worker | Non-blocking, retry, eventual consistency | **CHOSEN** |
| FastAPI BackgroundTasks | Simple, no retry, lost on restart | Rejected — reliability |

**Rationale**: LLM calls take 3-10s. Queue prevents API blocking. Redis provides durability and retry semantics.

### Decision: Frontend Stack

| Option | Tradeoff | Decision |
|--------|----------|----------|
| React + Vite + TS + Recharts + Zustand + React Query | Type-safe, good ecosystem, moderate boilerplate | **CHOSEN** |
| HTMX + Jinja2 | Simple, less interactive | Rejected — dashboard needs real-time feel |

## Data Flow

```
Client ──POST──→ API ──→ TransactionService
                         │
                         ├──→ RuleEngine (sync, <10ms)
                         │       └──→ fired_rules[], rule_score
                         │
                         ├──→ FeatureEngine (sync, <5ms)
                         │       └──→ feature_vector
                         │
                         ├──→ MLModelService (sync, <50ms)
                         │       └──→ ml_score
                         │
                         ├──→ EnsembleScorer (sync, <1ms)
                         │       └──→ ensemble_score, threshold, classification
                         │
                         ├──→ FraudScore (persist)
                         ├──→ FraudAlert (if classified=fraud)
                         │
                         └──→ Redis Queue (if classified=fraud)
                                 └──→ LLMWorker (async)
                                         └──→ Ollama API
                                         └──→ LLMReport (persist)
```

## Sequence: Transaction Scoring

```
Client          API             RuleEngine      MLService       Ensemble        Redis           LLMWorker
  │               │                │               │               │               │               │
  │──POST /tx──→  │                │               │               │               │               │
  │               │──evaluate──→   │               │               │               │               │
  │               │←─rules,score── │               │               │               │               │
  │               │──features──→   │               │               │               │               │
  │               │               │──extract──→    │               │               │               │
  │               │←─feature_vec── │               │               │               │               │
  │               │──score──→                      │               │               │               │
  │               │←─ml_score───── │               │               │               │               │
  │               │──combine──→                                    │               │               │
  │               │←─ensemble─────                                 │               │               │
  │               │──persist──→ (FraudScore, FraudAlert)                                                   │
  │               │──enqueue──→                                                    │──LPUSH──→      │
  │←─201 + score─ │                │               │               │               │               │
  │               │                │               │               │               │──BRPOP──→      │
  │               │                │               │               │               │               │──Ollama──→
  │               │                │               │               │               │               │←─report───
  │               │                │               │               │               │               │──persist──→
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/core/config.py` | Modify | Add JWT, ensemble weights, threshold tiers, Ollama timeout settings |
| `src/core/database.py` | Create | Async SQLAlchemy session factory, Base model |
| `src/core/redis.py` | Create | Redis connection pool, queue helpers |
| `src/core/security.py` | Create | JWT encode/decode, password hashing (bcrypt), token blacklist |
| `src/core/dependencies.py` | Create | FastAPI dependency injectors (get_db, get_redis, get_current_user) |
| `src/models/base.py` | Create | BaseModel with id, created_at, updated_at, soft delete |
| `src/models/transaction.py` | Create | Transaction model (amount, currency, merchant, card, status) |
| `src/models/fraud_score.py` | Create | FraudScore model (rule_score, ml_score, ensemble_score, threshold, classification) |
| `src/models/fraud_alert.py` | Create | FraudAlert model (transaction_id, status, score, threshold) |
| `src/models/rule.py` | Create | Rule metadata model (name, weight, description, active) |
| `src/models/llm_report.py` | Create | LLMReport model (transaction_id, report_text, model_name, status, generation_time) |
| `src/models/ml_model_run.py` | Create | MLModelRun model (model_version, metrics, status, drift_detected) |
| `src/models/user.py` | Create | User model (username, email, hashed_password, role) |
| `src/models/audit_entry.py` | Create | AuditEntry model (immutable, SHA-256 checksum, action_type, metadata) |
| `src/schemas/transaction.py` | Create | Pydantic schemas for transaction CRUD |
| `src/schemas/auth.py` | Create | Pydantic schemas for login, register, token response |
| `src/schemas/scoring.py` | Create | Pydantic schemas for score response, ensemble breakdown |
| `src/schemas/alert.py` | Create | Pydantic schemas for alert list and actions |
| `src/schemas/report.py` | Create | Pydantic schemas for LLM report response |
| `src/schemas/monitoring.py` | Create | Pydantic schemas for drift reports, model runs |
| `src/schemas/audit.py` | Create | Pydantic schemas for audit trail queries |
| `src/services/rule_engine.py` | Create | Deterministic rule evaluation with configurable weights |
| `src/services/feature_engine.py` | Create | Scikit-learn Pipeline for feature extraction |
| `src/services/ml_model.py` | Create | Model loading, inference, serialization (joblib) |
| `src/services/ensemble.py` | Create | Weighted scoring with dynamic threshold lookup |
| `src/services/llm.py` | Create | Ollama client wrapper with prompt templates |
| `src/services/transaction.py` | Create | Transaction CRUD with soft delete |
| `src/services/auth.py` | Create | User registration, login, token management |
| `src/services/monitoring.py` | Create | Evidently drift detection, performance tracking |
| `src/services/audit.py` | Create | Audit entry creation with checksum, query API |
| `src/workers/llm_worker.py` | Create | Async Redis consumer, Ollama caller, retry logic |
| `src/workers/monitoring_worker.py` | Create | Periodic drift detection job |
| `src/api/v1/router.py` | Create | API v1 router aggregation |
| `src/api/v1/transactions.py` | Create | Transaction CRUD + scoring endpoints |
| `src/api/v1/auth.py` | Create | Login, register, refresh, logout endpoints |
| `src/api/v1/alerts.py` | Create | Alert list, review, analyst action endpoints |
| `src/api/v1/reports.py` | Create | LLM report retrieval endpoint |
| `src/api/v1/monitoring.py` | Create | Drift reports, model runs, reference data endpoints |
| `src/api/v1/audit.py` | Create | Audit trail query + export endpoints |
| `src/api/main.py` | Modify | Mount v1 router, add lifespan (DB init, worker startup) |
| `requirements.txt` | Modify | Add scikit-learn, joblib, evidently, python-jose, passlib, numpy, pandas |
| `docker/Dockerfile.api` | Create | Multi-stage Python 3.11 build |
| `docker/Dockerfile.frontend` | Create | Node 20 build + nginx serve |
| `docker-compose.yml` | Modify | Add model volume, worker service, healthchecks |
| `frontend/` | Create | React + Vite + TS application |
| `tests/` | Create | Full TDD test suite |

## Interfaces / Contracts

### Scoring Response
```python
class ScoreResponse(BaseModel):
    transaction_id: UUID
    rule_score: float          # 0-100
    ml_score: float            # 0-100
    ensemble_score: float      # 0-100
    threshold: float           # dynamic by amount tier
    classification: Literal["legitimate", "review", "fraud"]
    fired_rules: list[str]
    created_at: datetime
```

### JWT Token Payload
```python
{
    "sub": "<user_id>",
    "role": "admin" | "analyst",
    "exp": <unix_timestamp>,
    "iat": <unix_timestamp>
}
```

### Redis Queue Message
```json
{
    "transaction_id": "uuid",
    "score_breakdown": {
        "rule_score": 60,
        "ml_score": 80,
        "ensemble_score": 72,
        "fired_rules": ["high_amount", "high_velocity"]
    },
    "retry_count": 0,
    "enqueued_at": "2024-01-01T00:00:00Z"
}
```

### Amount Threshold Tiers
| Tier | Amount Range | Threshold |
|------|-------------|-----------|
| Low | $0 - $1,000 | 70 |
| Medium | $1,001 - $10,000 | 60 |
| High | $10,001 - $50,000 | 50 |
| Critical | > $50,000 | 40 |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Rule engine determinism, feature extraction consistency, ensemble math, JWT encode/decode, prompt template assembly | pytest with fixed inputs, assert exact outputs |
| Unit | ML model scoring with serialized mock model | joblib.dump a pre-trained IsolationForest, test inference |
| Integration | Transaction CRUD + scoring pipeline end-to-end | TestClient with test DB (asyncpg test container or in-memory SQLite fallback) |
| Integration | Auth flow: register → login → access protected → refresh → logout → token rejected | TestClient + Redis mock |
| Integration | LLM worker: enqueue → consume → mock Ollama → persist report | Redis fakeredis + httpx mock for Ollama |
| E2E | Full pipeline: POST transaction → verify score → verify alert → verify queue → verify report | Docker compose test profile |

## Migration / Rollout

1. **Feature flag**: `FRAUD_DETECTION_ENABLED` env var (default: `false`). All scoring endpoints return 503 if disabled.
2. **Model versioning**: Serialized models named `model_vN.joblib`. Symlink `model_latest.joblib` points to active version. Rollback = update symlink.
3. **Database**: Alembic migrations with `downgrade` scripts. All models have soft delete — no data loss on rollback.
4. **Frontend**: Standalone service. If broken, API still works. Disable in docker-compose.
5. **Full rollback**: `git revert` merge commit. Audit trail preserved (append-only).

## Open Questions

- [ ] Should the ML model be loaded at startup or lazy-loaded on first inference? (Tradeoff: startup latency vs. cold-start latency)
- [ ] Should Evidently drift reports be computed synchronously on request or via periodic background job? (Tradeoff: freshness vs. compute cost)
- [ ] What is the exact feature vector schema for the Isolation Forest? (Needs alignment with Kaggle dataset columns + synthetic features)
