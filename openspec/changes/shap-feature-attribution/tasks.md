# Tasks: SHAP Feature Attribution for Suspicious Transactions

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1100 (B1 ~730, B2 ~130, B3 ~215) |
| 400-line budget risk | High |
| Chained PRs recommended | No |
| Suggested split | Direct main merge, 3 sequential batches |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

No PR chain — direct main merge per user preference; review batches sequentially. Design question: `create_all` vs Alembic — confirm at apply.

## Batch 1: Backend Core (model + shap_service + worker + tests)

- [x] **1.1 RED — `tests/unit/test_shap_service.py`**: import→ImportError ⇒ `ShapUnavailableError`+warning; fake explainer ⇒ list/2D/3D normalization (fraud idx 1), top-5 by |contribution| signed, name-mismatch fallback `feature_i`; fingerprint `size:mtime`, no shap import. (SHP-001, SHP-002, SHP-005)
- [x] **1.2 GREEN — `src/models/shap_attribution.py`**: uuid PK, `transaction_id` FK CASCADE, `feature` String(100), `contribution` Float, `rank` Integer, index `(transaction_id, rank)`; export `src/models/__init__.py` + `scripts/init_db.py`. (SHP-002)
- [x] **1.3 GREEN — `src/services/shap_service.py`**: lazy importlib shap under lock; joblib model; `explain()` top-5 ranked signed; `persist()` delete-then-insert; `model_fingerprint()`; `ShapUnavailableError`. (SHP-001, SHP-002, SHP-005)
- [x] **1.4 RED — `tests/test_shap_worker.py`** (mirror `test_llm_worker.py`): success ⇒ delete + 5 rows + audit `shap_computed`; unavailable ⇒ skip no retry; exception ⇒ False; max retries ⇒ audit `shap_failed`; idempotent re-run; malformed/empty queue. (SHP-002..005)
- [x] **1.5 GREEN — `src/workers/shap_worker.py`**: `process_shap_message(message, db, shap_service, max_retries=3, audit_service=None) -> bool`; BRPOP `fraud:shap` loop (max_iterations); `asyncio.to_thread`; audit `shap_computed`/`shap_failed`; `python -m` entry. (SHP-001..005)
- [x] **1.6 GREEN — `enqueue_for_retry(redis, message, queue_name, backoff_base=3)` in `src/core/redis.py`**; `llm_worker.py` untouched. (SHP-003)
- [x] **1.7 GREEN — `shap==0.46.*` in `requirements.txt`**; `shap-worker` compose service (`python -m src.workers.shap_worker`). (SHP-006)
- [x] **1.8 REFACTOR — Gate**: pytest shap tests, `ruff check src/`, `mypy src/` green. (SHP-001..006)

## Batch 2: API + Schemas + Integration Tests

- [ ] **2.1 RED — `tests/integration/test_transaction_api.py`**: detail ⇒ 5 ordered contributions (4th execute); none ⇒ null; unscored ⇒ scoring null (2 executes); list `call_count==3`; POST enqueues ONLY fraud/review, snapshot==scored vector; redis down ⇒ 201 (patch `enqueue`). (FD-SHP-001, FRD-SHP-001, SHP-005, SHP-007)
- [ ] **2.2 GREEN — `src/schemas/transaction.py`**: `ShapContribution{feature, contribution}`; `ScoreBreakdown.shap_contributions: list | None = None`. (FRD-SHP-001)
- [ ] **2.3 GREEN — `src/api/v1/transactions.py`**: POST — fraud/review ⇒ best-effort `enqueue("fraud:shap", {transaction_id, classification, features, feature_names, model_fingerprint})`; detail — if score, one `select(ShapAttribution).order_by(rank)` → `shap_contributions`; list + report untouched. (FD-SHP-001, FRD-SHP-001, SHP-007)
- [ ] **2.4 REFACTOR — Gate**: `pytest tests/ -v --cov=src`, `ruff`, `mypy` green; SHP-007 unchanged. (FD-SHP-001, FRD-SHP-001, SHP-005, SHP-007)

## Batch 3: Frontend + MSW + Tests

- [ ] **3.1 RED — `frontend/src/tests/mocks/handlers.ts`** (detail fixture gains 5 `shap_contributions`) **+ `TransactionDetail.test.tsx`**: section + ES labels + direction when present; hidden when null. (FRD-SHP-002)
- [ ] **3.2 GREEN — `frontend/src/api/transactions.ts`**: `ShapContribution` type + `shap_contributions`; create `frontend/src/lib/shap.ts` ES label map. (FRD-SHP-002)
- [ ] **3.3 GREEN — `frontend/src/components/ShapAttributionCard.tsx`**: up to 5 bars, direction (positive→fraud red, negative→legit green), ES labels, nothing when empty. (FRD-SHP-002)
- [ ] **3.4 GREEN — `frontend/src/pages/TransactionDetail.tsx`**: render `<ShapAttributionCard contributions={tx.scoring?.shap_contributions} />`. (FRD-SHP-002)
- [ ] **3.5 REFACTOR — Gate**: `npm test` + `npx tsc --noEmit` green. (FRD-SHP-002)
