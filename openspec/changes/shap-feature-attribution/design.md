# Design: SHAP Feature Attribution for Suspicious Transactions

## Technical Approach

Async SHAP explanation pipeline mirroring the LLM worker. `POST /transactions` snapshots the scored feature vector into a new `fraud:shap` queue (fraud/review only, best-effort); a dedicated worker computes `shap.TreeExplainer` contributions off the snapshot inside `asyncio.to_thread`, persists top-5 `ShapAttribution` rows (delete-then-insert for idempotency), writes audit entries, and retries with the LLM backoff pattern. Detail API exposes `scoring.shap_contributions` via one extra ordered query; list/report untouched. Frontend renders an "Atribución SHAP" section with direction bars, hidden when null. Covers SHP-001..007, FD-SHP-001, FRD-SHP-001/2. XAI-001: read-only after scoring — never touches classification/scores/alerts.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| Feature vector | Snapshot at enqueue | Recalc in worker | VelocityStore windows + Query B stats shift; recalc explains a DIFFERENT vector (proposal §Current-State Gap) |
| shap import | Lazy `importlib.import_module("shap")` inside `_ensure_ready()` | Module-level import | SHP-005: worker survives missing shap; tests mock without shap installed |
| Model source | ShapService joblib-loads `models/xgboost_paysim_v1.joblib` itself (same default path as MLModelService) | Reuse `MLModelService._model` | Private attr; worker is a separate process; self-contained, mirrors `ml_model.py` |
| Explainer lifecycle | Service singleton, lazy TreeExplainer under `threading.Lock` | Per-message explainer | Init costs 100–500ms; BRPOP loop is single-consumer so `to_thread` calls serialize |
| shap_values normalization | list→`[1]`; 2D→as-is; 3D→`[..., 1]` | Assume one shape | Binary XGBoost output shape varies; class-fraud index 1 (SHP-002) |
| Persistence | Child table `shap_attributions`, delete-then-insert | JSONB column | Mirrors LLMReport; queryable/auditable; idempotent (SHP-002) |
| Retry helper | `enqueue_for_retry(redis, message, queue_name)` in `src/core/redis.py` | Duplicate in shap_worker | Shared; llm_worker left untouched (no behavior change, tests stay green) |
| Detail query | One `select ... order_by rank` only when `score is not None` | Always query | FRD-SHP-001 "single query"; skips pointless query for unscored txns; keeps null-score test at 2 execute calls |
| Migration | `create_all` via `scripts/init_db.py` + model export | Alembic | Project default (proposal open decision); confirm with maintainers at apply |
| Frontend placement | New `ShapAttributionCard` used by TransactionDetail | Extend ScoreResultCard | ScoreResultCard consumes `ScoreResponse` (POST shape); SHAP is detail-only (FRD-SHP-002) |
| Dependency | `shap==0.46.*`; numpy stays `1.26.*` | none | PyPI 0.46.0: requires py≥3.9, deps numpy/scipy/sklearn/pandas/numba — compatible with pins (verified 2026-08) |

## Data Flow

```
POST /api/v1/transactions
  transform() → features(10,) → predict() → classify()
  if fraud|review ──best-effort──▶ fraud:shap {transaction_id, classification,
                                features, feature_names, model_fingerprint}
                                        │ BRPOP
                                        ▼
shap_worker (per-message session, mirror llm_worker)
  asyncio.to_thread(ShapService.explain) → TreeExplainer.shap_values → top-5 by |v|
  delete existing rows → add_all 5 → audit shap_computed → commit
  failure → enqueue_for_retry(+1) / max → audit shap_failed

GET /api/v1/transactions/{id}
  txn → scores → (if score) SELECT ... ORDER BY rank → scoring.shap_contributions
```

## File Changes

| File | Action | ~Size |
|---|---|---|
| `src/models/shap_attribution.py` | Create | 35 |
| `src/services/shap_service.py` | Create | 120 |
| `src/workers/shap_worker.py` | Create | 170 |
| `src/models/__init__.py` | Modify: export | +3 |
| `scripts/init_db.py` | Modify: import | +1 |
| `src/core/redis.py` | Modify: `enqueue_for_retry` | +14 |
| `src/schemas/transaction.py` | Modify: `ShapContribution`, `ScoreBreakdown.shap_contributions` | +12 |
| `src/api/v1/transactions.py` | Modify: enqueue + detail query | +25 |
| `requirements.txt` | Modify: `shap==0.46.*` | +1 |
| `docker-compose.yml` | Modify: `shap-worker` service | +18 |
| `frontend/src/api/transactions.ts` | Modify: types | +8 |
| `frontend/src/lib/shap.ts` | Create: ES labels map | 35 |
| `frontend/src/components/ShapAttributionCard.tsx` | Create | 90 |
| `frontend/src/pages/TransactionDetail.tsx` | Modify: render card | +12 |
| `frontend/src/tests/mocks/handlers.ts` | Modify: fixture | +10 |
| `tests/unit/test_shap_service.py` | Create | 150 |
| `tests/test_shap_worker.py` | Create | 220 |
| `tests/integration/test_transaction_api.py` | Modify: 3rd query mock + enqueue tests | +90 |
| `frontend/src/tests/TransactionDetail.test.tsx` | Modify: render/hide | +60 |

## Interfaces / Contracts

Queue message:
```json
{"transaction_id":"<uuid>","classification":"fraud|review",
 "features":[10 floats],"feature_names":["amount",...],
 "model_fingerprint":"<size>:<mtime>","retry_count":0}
```

Worker: `process_shap_message(message, db, shap_service, max_retries=3, audit_service=None) -> bool` (True = done or permanent failure, False = re-enqueue). `ShapService.explain(features: list[float]) -> list[ShapContribution]` — top-5 ordered by |contribution|, signed; raises `ShapUnavailableError` when shap/model missing (SHP-005: skip, no retry). `ShapService.model_fingerprint()` = `"<size>:<mtime>"` via file stat (no shap import).

Normalization (non-obvious only):
```python
if isinstance(values, list): v = values[1]        # class-fraud
elif values.ndim == 3:       v = values[0, :, 1]  # Explanation-style
else:                        v = values           # already fraud margin
```

API schema:
```python
class ShapContribution(BaseModel):
    feature: str
    contribution: float

class ScoreBreakdown(BaseModel):
    # ...existing fields...
    shap_contributions: list[ShapContribution] | None = None
```

`ShapAttribution(BaseModel)`: `transaction_id` FK CASCADE, `feature` String(100), `contribution` Float, `rank` Integer; composite index `(transaction_id, rank)`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | shap_service | patch import→ImportError ⇒ ShapUnavailableError + warning; fake explainer ⇒ list/2D/3D paths, top-5 by \|v\| signed, name-mismatch fallback (`feature_i` + warning), fingerprint |
| Unit | worker | mirror test_llm_worker: success ⇒ delete + 5 rows + audit `shap_computed`; unavailable ⇒ skip, no retry; exception ⇒ False; max retries ⇒ audit `shap_failed`; loop/empty/malformed; idempotent re-run |
| Integration | API | detail ⇒ 5 ordered contributions; none ⇒ null; unscored ⇒ scoring null (2 execute calls); list unchanged (`call_count==3` preserved); POST enqueues ONLY fraud/review with snapshot==scored vector; redis down ⇒ 201 (patch module-level `enqueue`) |
| Frontend | render | MSW fixture with contributions ⇒ section + ES labels + direction styling; null ⇒ hidden |

## Migration / Rollout

No data migration. New table via `create_all` (re-run `python scripts/init_db.py`). Additive: new optional field, table, queue. Rollback = `git revert`; API returns null, UI hides section, worker stopped lets `fraud:shap` drain. Start via new compose `shap-worker` service (`python -m src.workers.shap_worker`, same volumes src+models).

## Open Questions

- [ ] create_all vs Alembic — confirm with maintainers at apply (design assumes create_all per proposal).
