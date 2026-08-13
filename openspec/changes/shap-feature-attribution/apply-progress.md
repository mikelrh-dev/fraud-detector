# Apply Progress: SHAP Feature Attribution

**Change**: shap-feature-attribution
**Phase**: apply — Batch 1 (backend core) + Batch 2 (API + schemas + integration tests) + Batch 3 (frontend + MSW + tests)
**Mode**: Strict TDD (RED → GREEN → REFACTOR)
**Branch**: `feat/shap-attribution`
**Dates**: 2026-08-13 (Batch 1), 2026-08-13 (Batch 2), 2026-08-13 (Batch 3)

## Status

- **Batch 1 complete**: 8/8 tasks (1.1–1.8). 25 new tests, all passing. `ruff check src/` and `mypy src/` clean. Full suite: **319 passed** (baseline 294 + 25 new).
- **Batch 2 complete**: 4/4 tasks (2.1–2.4). 10 new tests, all passing. Full suite: **329 passed** (319 + 10 new). `ruff check src/` and `mypy src/` clean. SHP-007 invariant preserved — classification/scores/alerts untouched; SHAP strictly additive (new queue message, new detail field, one optional query).
- **Batch 3 complete**: 5/5 tasks (3.1–3.5). 12 new frontend tests, all passing. Frontend suite: **47 passed** (baseline 35 + 12 new). `npx tsc --noEmit` clean. Backend suite re-run: **329 passed** (unchanged — frontend-only batch). FRD-SHP-002 met: section renders top-5 with ES labels + direction (positive → red fraud, negative → green legit), hidden when null/empty.

## Decision: create_all vs Alembic (confirmed)

The design left the migration mechanism as an open decision ("confirm with maintainers at apply"). Evidence confirmed **`create_all`** as the project's de-facto pattern:

- `alembic/versions/b02e4753e78e_initial.py` is an empty scaffold (`upgrade()`/`downgrade()` are `pass`) — Alembic is not actively used for schema management.
- Every model (`llm_reports`, `fraud_scores`, …) is created via `scripts/init_db.py` → `Base.metadata.create_all(engine)`.
- `ShapAttribution` was wired into `scripts/init_db.py` accordingly (model export is what registers the table on `Base.metadata`).

Note: `scripts/init_db.py` triggers pre-existing intentional `F401` warnings in ruff (imports are the side-effect registration mechanism for `create_all`); the file lives under `scripts/` and is outside the project's `ruff check src/` gate. No fix applied to avoid breaking table registration.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.2 | `tests/unit/test_models.py` | Unit | ✅ 294/294 | ✅ Written (collection error: `src.models.shap_attribution` missing) | ✅ Passed 18/18 | ✅ 3 cases (columns, FK CASCADE, composite index) + export | ➖ None needed (structural) |
| 1.1 | `tests/unit/test_shap_service.py` | Unit | N/A (new file) | ✅ Written (collection error: `src.services.shap_service` missing) | ✅ Passed 10/10 | ✅ 10 cases: list/2D/3D, top-5 signed, tie-break, name fallback, fingerprint present/missing, shap-import error, model-missing, output contract | ✅ Float assertion fixed via `pytest.approx` (test-side) |
| 1.4 | `tests/test_shap_worker.py` | Unit | N/A (new file) | ✅ Written (collection error: `src.workers.shap_worker` missing) | ✅ Passed 11/11 | ✅ 10 cases: success 5 rows + delete + audit, unavailable skip, exception→False, max retries→`shap_failed`, idempotent re-run, missing features, loop process/empty/malformed/re-enqueue | ➖ None needed |
| 1.6 | `tests/unit/test_redis.py` | Unit | ✅ 294/294 | ✅ Written (collection error: `enqueue_for_retry` missing) | ✅ Passed 4/4 | ✅ 2 cases (increments from 0, defaults to 1) | ➖ None needed |
| 1.3 | `src/services/shap_service.py` | Unit | via 1.1 | — (implemented to pass 1.1 tests) | ✅ Passed | covered by 1.1 cases | ✅ Clean, no refactor needed |
| 1.5 | `src/workers/shap_worker.py` | Unit | via 1.4 | — (implemented to pass 1.4 tests) | ✅ Passed | covered by 1.4 cases | ✅ Clean, no refactor needed |
| 1.7 | `requirements.txt` + `docker-compose.yml` | — | N/A | — (declarative change) | ✅ `shap==0.46.*` + `shap-worker` service | ➖ Single (Triangulation skipped: declarative file change, no branching logic) | ➖ None needed |
| 1.8 | gate: `pytest tests/ -q`, `ruff check src/`, `mypy src/` | — | ✅ 294/294 | — | ✅ 319 passed; ruff + mypy clean | — | ✅ Full gate green |
| 2.1 | `tests/integration/test_transaction_api.py` + `tests/unit/test_schemas.py` | Integration + Unit | ✅ 319/319 | ✅ Written (schema ImportError `ShapContribution`; integration 5 failed: 3rd-execute StopIteration, missing `shap_contributions`, no `fraud:shap` enqueue, no SHAP log) | ✅ Passed | ✅ 8 cases: 5 ordered contributions, absent→null, unscored→2 executes, list call_count==3, fraud/review enqueue (2), legitimate no-enqueue, redis-down 201 | ✅ mypy narrowing restructure in detail endpoint |
| 2.2 | `src/schemas/transaction.py` | Unit | via 2.1 | — (implemented to pass 2.1 schema tests) | ✅ Passed 17/17 | covered by 2.1 cases | ➖ None needed |
| 2.3 | `src/api/v1/transactions.py` | Integration | via 2.1 | — (implemented to pass 2.1 API tests) | ✅ Passed 19/19 | covered by 2.1 cases | ➖ None needed |
| 2.4 | gate: `pytest tests/ -q`, `ruff check src/`, `mypy src/` | — | ✅ 319/319 | — | ✅ 329 passed; ruff + mypy clean | — | ✅ Full gate green |
| 3.1 | `frontend/src/tests/TransactionDetail.test.tsx` + `frontend/src/tests/mocks/handlers.ts` | Integration (page + MSW) | ✅ 35/35 | ✅ Written (testid `shap-attribution` absent; `./shap` and card imports unresolved) | ✅ Passed 14/14 (touched files) | ✅ 3 cases: 5-row render with ES labels + direction counts (3 fraud / 2 legit), null → hidden, existing score/none tests still green | ➖ None needed |
| 3.2 | `frontend/src/lib/shap.test.ts` + `src/api/transactions.ts` + `src/lib/shap.ts` | Unit | N/A (new file) | ✅ Written (collection error: `./shap` unresolved) | ✅ Passed 7/7 | ✅ 7 cases: 10 real backend labels, alias keys, fallback raw name, +sign, -sign, zero, direction fraud/legit | ➖ None needed |
| 3.3 | `frontend/src/tests/ShapAttributionCard.test.tsx` + `src/components/ShapAttributionCard.tsx` | Unit | N/A (new file) | ✅ Written (collection error: card import unresolved) | ✅ Passed 3/3 | ✅ 3 cases: positive render (labels, signed values, direction texts), null → null, empty array → null | ➖ None needed |
| 3.4 | `frontend/src/pages/TransactionDetail.tsx` | Integration | via 3.1 | — (implemented to pass 3.1 page tests) | ✅ Passed 4/4 | covered by 3.1 cases | ➖ None needed |
| 3.5 | gate: `npm test`, `npx tsc --noEmit`, `pytest tests/ -q` | — | ✅ 35/35 | — | ✅ 47 frontend + 329 backend; tsc clean | — | ✅ Full gate green |

## Test Summary

- **Total tests written**: 47 (25 Batch 1 + 10 Batch 2 + 12 Batch 3)
- **Total tests passing**: frontend 47/47; backend 329/329 (294 pre-existing + 35 new backend)
- **Layers used**: Unit (30 backend + 10 frontend lib/card), Integration (5 backend + 2 frontend page)
- **Approval tests** (refactoring): None — no existing behavior refactored (`llm_worker.py` untouched; `src/core/redis.py` only appended `enqueue_for_retry`; `ScoreResponse` POST shape untouched)
- **Pure functions created**: `ShapService._normalize_shap_values`, `ShapService._top_k`, `ShapService.model_fingerprint`, `featureLabel`, `formatContribution`, `contributionDirection` (all pure, deterministic)

## Files Changed (Batch 1)

| File | Action | What Was Done |
|------|--------|---------------|
| `src/models/shap_attribution.py` | Created | ShapAttribution ORM model (uuid PK, transaction_id FK CASCADE, feature String(100), contribution Float, rank Integer, composite index) |
| `src/models/__init__.py` | Modified | Export `ShapAttribution` |
| `scripts/init_db.py` | Modified | Import `ShapAttribution` for `create_all` registration |
| `src/services/shap_service.py` | Created | Lazy importlib shap import under lock, joblib model load, `explain()` top-5 signed, `model_fingerprint()`, `ShapUnavailableError` |
| `src/core/redis.py` | Modified | Shared `enqueue_for_retry(redis, message, queue_name, backoff_base=3)` |
| `src/workers/shap_worker.py` | Created | BRPOP `fraud:shap` loop, `process_shap_message`, `asyncio.to_thread`, delete-then-insert, audit `shap_computed`/`shap_failed`, retry via shared helper |
| `requirements.txt` | Modified | `shap==0.46.*` |
| `docker-compose.yml` | Modified | `shap-worker` service (`python -m src.workers.shap_worker`) |
| `tests/unit/test_models.py` | Modified | ShapAttribution field/constraint/index + export tests |
| `tests/unit/test_shap_service.py` | Created | 10 service tests (no shap installed) |
| `tests/test_shap_worker.py` | Created | 10 worker tests mirroring `test_llm_worker.py` |
| `tests/unit/test_redis.py` | Modified | 2 `enqueue_for_retry` tests |
| `openspec/changes/shap-feature-attribution/tasks.md` | Modified | Batch 1 tasks marked `[x]` |
| `openspec/changes/shap-feature-attribution/apply-progress.md` | Created | This artifact |

## Files Changed (Batch 2)

| File | Action | What Was Done |
|------|--------|---------------|
| `src/schemas/transaction.py` | Modified | `ShapContribution{feature, contribution}` schema; `ScoreBreakdown.shap_contributions: list[ShapContribution] \| None = None` (FRD-SHP-001) |
| `src/api/v1/transactions.py` | Modified | POST step 11: best-effort `enqueue("fraud:shap", {transaction_id, classification, features: features.tolist(), feature_names, model_fingerprint})` when classification ∈ {fraud, review} (FD-SHP-001); module-level `_shap_service = ShapService()`; GET detail: one `select(ShapAttribution).order_by(rank)` only when score exists → `scoring.shap_contributions`; list + report untouched |
| `tests/unit/test_schemas.py` | Modified | `TestShapContribution` (3) + `TestScoreBreakdown` shap cases (2); existing `model_validate` test updated with `score.shap_contributions = None` |
| `tests/integration/test_transaction_api.py` | Modified | 200-detail gains 3rd SHAP mock + null assertion; new ordered-contributions test (single query, ORDER BY rank); unscored test asserts `call_count == 2`; new `TestCreateTransactionShapEnqueue` (fraud/review parametrized snapshot, legitimate no-enqueue, redis-down 201) |
| `openspec/changes/shap-feature-attribution/tasks.md` | Modified | Batch 2 tasks 2.1–2.4 marked `[x]` |
| `openspec/changes/shap-feature-attribution/apply-progress.md` | Modified | Batch 2 section merged (this artifact) |

## Files Changed (Batch 3)

| File | Action | What Was Done |
|------|--------|---------------|
| `frontend/src/tests/mocks/handlers.ts` | Modified | GET detail fixture gains deterministic `scoring.shap_contributions` (5 items ordered by \|v\|: amount +35, tx_count_last_1h +18, tx_count_last_5min +12, merchant_risk_level -5, amount_round_number -2) (FRD-SHP-002) |
| `frontend/src/api/transactions.ts` | Modified | `ShapContribution{feature, contribution}` interface; `Transaction.scoring.shap_contributions?: ShapContribution[] \| null` (detail-only; `ScoreResponse` POST shape untouched per FRD-SHP-001) |
| `frontend/src/lib/shap.ts` | Created | ES label map (10 real backend feature names + design alias keys) + pure helpers `featureLabel`, `formatContribution` (+/- sign, one decimal), `contributionDirection` (≥0 → fraud, <0 → legitimate) |
| `frontend/src/components/ShapAttributionCard.tsx` | Created | "Atribución SHAP" section: top-k rows, normalized direction bars (positive → red, negative → green), signed contribution, ES labels; renders null when contributions null/empty; `data-testid="shap-attribution"` |
| `frontend/src/pages/TransactionDetail.tsx` | Modified | Renders `<ShapAttributionCard contributions={tx.scoring?.shap_contributions} />` after the scoring section; card self-hides when absent |
| `frontend/src/lib/shap.test.ts` | Created | 7 unit tests (labels, alias/fallback, sign formatting, direction) |
| `frontend/src/tests/ShapAttributionCard.test.tsx` | Created | 3 tests: positive render (labels/signs/direction texts), null → null, [] → null |
| `frontend/src/tests/TransactionDetail.test.tsx` | Modified | +2 tests: SHAP section renders with ES labels + direction counts (3 "Hacia fraude" / 2 "Hacia legítimo"), hidden when `shap_contributions: null` |
| `openspec/changes/shap-feature-attribution/tasks.md` | Modified | Batch 3 tasks 3.1–3.5 marked `[x]` — **17/17 total complete** |
| `openspec/changes/shap-feature-attribution/apply-progress.md` | Modified | Batch 3 section merged (this artifact) |

## Deviations from Design

1. **`explain()` accepts `feature_names`**: design interface showed `explain(features)`, but the queue message carries `feature_names` and the design's own testing strategy requires the name-mismatch fallback — added `feature_names: list[str] | None = None`.
2. **`persist()` not a service method**: design listed `persist()` under `ShapService` in task 1.3, but the worker owns persistence (delete-then-insert + audit + commit in one session). Keeping persistence in the worker mirrors the LLM worker's report-persistence pattern; `ShapService` stays a pure explainer. Behavioral contract unchanged (SHP-002 met via worker tests).
3. **`scripts/init_db.py` F401s**: pre-existing intentional side-effect imports; left as-is (documented above).
4. **Batch 2 — no deviations**: schema, POST enqueue (message exactly per design Interfaces contract minus `retry_count`, which the worker defaults to 0), and detail single-query match design. Detail returns `null` when no rows (empty list is never assigned) per FRD-SHP-001 "null when none exist". `model_fingerprint` sourced from `_shap_service.model_fingerprint()` (module-level singleton, mirrors other services).
5. **Batch 3 — fixture uses real backend feature names**: the batch brief suggested keys like `merchant_risk`/`velocity_5min`/`round_amount` (design-map aliases), but the actual backend `FEATURE_NAMES` are `merchant_risk_level`/`tx_count_last_5min`/`amount_round_number`. Fixture uses the REAL names so rendered labels resolve; `shap.ts` maps both the real names and the design's alias keys (defensive).
6. **Batch 3 — `contributionDirection` treats 0 as fraud**: design says positive → fraud, negative → legit; zero is unspecified — treated as `>= 0` (consistent with `formatContribution` "+0.0"). Documented in the helper.
7. **Batch 3 — bar width normalized**: bars scale to the largest |contribution| in the set (relative bars) instead of raw absolute widths, since contributions are unbounded floats.

## Issues Found

- Float precision in the service test (`0.1 * 7 == 0.7000000000000001`) — fixed with `pytest.approx`; production logic was correct.
- `alembic.ini` exists but its only revision is an empty scaffold — new table relies on `create_all`; if Alembic is adopted later, a migration for `shap_attributions` must be generated.
- Batch 2: mypy `union-attr` on `scoring` in the detail endpoint (no narrowing correlation between `score is not None` and `scoring is not None`) — restructured to compute `scoring` inside the `if score is not None:` block; mypy clean.
- Batch 2: `test_legitimate_does_not_enqueue_shap` passes vacuously in RED (no enqueue exists yet); it becomes a real guard after implementation (would fail on over-enqueueing) and is part of the triangulation set with the positive fraud/review cases.
- Batch 3: the "hidden when null" page test passed vacuously during RED (section never rendered yet); it becomes a real guard now that the section exists — the null override proves the card hides, and the empty-array card test triangulates the same path at component level.
- Batch 3: "Monto" as a SHAP row label collides with the "Monto" field in "Información General" — page test scopes assertions with `within(section)` via `data-testid="shap-attribution"` to avoid ambiguous matches.

## Next

All 17/17 tasks complete across the 3 batches. **Ready for sdd-verify**: `pytest tests/ -v --cov=src`, `ruff check src/`, `mypy src/`, `npm test`, `npx tsc --noEmit` all green; success criteria from the proposal (POST enqueue filter, top-5 persistence, detail exposure, UI render/hide) verified by 47 new tests total.
