# Apply Progress: SHAP Feature Attribution

**Change**: shap-feature-attribution
**Phase**: apply — Batch 1 (backend core)
**Mode**: Strict TDD (RED → GREEN → REFACTOR)
**Branch**: `feat/shap-attribution`
**Date**: 2026-08-13

## Status

Batch 1 complete: **8/8 tasks** (1.1–1.8). 25 new tests, all passing. `ruff check src/` and `mypy src/` clean. Full suite: **319 passed** (baseline 294 + 25 new).

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

## Test Summary

- **Total tests written**: 25 (3 model + 10 service + 10 worker + 2 redis)
- **Total tests passing**: 319 (294 pre-existing + 25 new)
- **Layers used**: Unit (25)
- **Approval tests** (refactoring): None — no existing behavior refactored (`llm_worker.py` untouched; `src/core/redis.py` only appended `enqueue_for_retry`)
- **Pure functions created**: `ShapService._normalize_shap_values`, `ShapService._top_k`, `ShapService.model_fingerprint` (pure, deterministic)

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

## Deviations from Design

1. **`explain()` accepts `feature_names`**: design interface showed `explain(features)`, but the queue message carries `feature_names` and the design's own testing strategy requires the name-mismatch fallback — added `feature_names: list[str] | None = None`.
2. **`persist()` not a service method**: design listed `persist()` under `ShapService` in task 1.3, but the worker owns persistence (delete-then-insert + audit + commit in one session). Keeping persistence in the worker mirrors the LLM worker's report-persistence pattern; `ShapService` stays a pure explainer. Behavioral contract unchanged (SHP-002 met via worker tests).
3. **`scripts/init_db.py` F401s**: pre-existing intentional side-effect imports; left as-is (documented above).

## Issues Found

- Float precision in the service test (`0.1 * 7 == 0.7000000000000001`) — fixed with `pytest.approx`; production logic was correct.
- `alembic.ini` exists but its only revision is an empty scaffold — new table relies on `create_all`; if Alembic is adopted later, a migration for `shap_attributions` must be generated.

## Next

**Batch 2** (API + schemas + integration tests): tasks 2.1–2.4 — `src/schemas/transaction.py` `ShapContribution` + `ScoreBreakdown.shap_contributions`; POST enqueue to `fraud:shap` (fraud/review only, snapshot vector, best-effort); detail GET one ordered query; integration tests in `tests/integration/test_transaction_api.py`.
