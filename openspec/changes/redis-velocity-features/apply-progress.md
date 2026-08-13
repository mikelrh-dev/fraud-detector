# Apply Progress — redis-velocity-features (PR 1 + PR 2)

**Change**: redis-velocity-features
**Batch**: PR 1 (VelocityStore + hot path) + PR 2 (retraining alignment)
**Branch**: `chore/redis-velocity-features` (feature-branch-chain, tracker)
**Mode**: Strict TDD (RED → GREEN → REFACTOR)
**Status**: ✅ COMPLETE — 21/21 tasks (14 PR1 + 7 PR2). Ready for sdd-verify.

## Summary

PR 1 implemented the Redis-backed velocity path end to end: a new `VelocityStore`
service (ZSET record + 5min/1h count pipeline + Postgres fallback), wired into
`POST /api/v1/transactions` replacing Query A, with a config toggle
(`velocity_store_enabled`), Redis socket timeouts, a DI dependency, extended
`mock_redis` fixture, 14 unit tests and 3 new integration tests. The
`tx_count_last_1h` bug (duplicate of the 5-min count) is fixed: it now comes
from a real 1-hour ZCOUNT window.

PR 2 aligned training with the new serve path: both synthetic generators now
persist `velocity_5min`/`velocity_1h` (the trainer was computing and discarding
them), `data/synthetic_transactions.csv` was regenerated with the velocity
columns populated, `train_xgboost_aligned.py` builds per-sample FeatureEngine
histories from the CSV values instead of all-zeros, the model was retrained
(velocity-aware) and ML-ALIGN was revalidated — thresholds unchanged
(crypto ≈ 100 > 20, grocery ≈ 0 < 10).

## Verification

- `pytest tests/ -q` → **285 passed** (268 baseline + 17 new)
- `pytest tests/ --cov=src` → **89%** (threshold ≥80%)
- `ruff check src/` → clean; `mypy src/` → clean
- Pre-existing ruff F401/F841 in untouched `tests/` files (test_audit.py,
  test_models.py, etc.) are on master too — out of scope, not touched.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 record ZADD/EXPIRE/trim/RTT/idempotent | `tests/unit/test_velocity_store.py` | Unit | ✅ 268/268 | ✅ Written (ModuleNotFoundError) | ✅ Passed | ✅ 3 cases (score/expire, missing ts, re-record) | ✅ Constants extracted |
| 1.2 read windows/empty/isolation | `tests/unit/test_velocity_store.py` | Unit | ✅ 268/268 | ✅ Written | ✅ Passed | ✅ 4 cases ([2,8], [0,0], minima, isolation) | ✅ `_key`/`_score` helpers |
| 1.3 failure/fallback/toggle | `tests/unit/test_velocity_store.py` | Unit | ✅ 268/268 | ✅ Written | ✅ Passed | ✅ 5 cases (3 error types, PG split, deleted_at SQL, 5min boundary, toggle) | ✅ `_pg_counts` extracted |
| 2.1 velocity_store.py service | `tests/unit/test_velocity_store.py` | Unit | ✅ 268/268 | N/A (covered by 1.1–1.3 RED) | ✅ 14/14 | ✅ | ✅ `_REDIS_UNAVAILABLE` tuple |
| 2.2 config toggle | `tests/unit/test_velocity_store.py` | Unit | ✅ 268/268 | N/A | ✅ 14/14 | ✅ toggle test | ➖ None needed |
| 2.3 redis pool timeouts | `tests/unit/test_redis.py` (existing) | Unit | ✅ 2/2 | N/A (no behavior change) | ✅ 2/2 | ➖ Single | ➖ None needed |
| 2.4 get_velocity_store DI | `tests/integration/test_transaction_api.py` | Integration | ✅ 11/11 | N/A | ✅ via conftest override | ➖ Single | ➖ None needed |
| 3.1 conftest ZSET/pipeline mocks | `tests/integration/test_transaction_api.py` | Integration | ✅ 11/11 | N/A (infra) | ✅ | ➖ Single | ➖ None needed |
| 3.2 high_velocity + window mins | `tests/integration/test_transaction_api.py` | Integration | ✅ 11/11 | ✅ Written (high_velocity in []) | ✅ 2/2 | ✅ [4,4] and [2,7] | ➖ None needed |
| 3.3 PG fallback + 1 db.execute | `tests/integration/test_transaction_api.py` | Integration | ✅ 11/11 | ✅ Written (no warning) | ✅ 1/1 | ✅ Redis-up (1 exec) + down (2 exec) | ➖ None needed |
| 3.4 regression default zcount=0 | full suite | Integration | ✅ 268/268 | N/A | ✅ 285/285 | ✅ | ➖ None needed |
| 4.1 hot path wiring | `tests/integration/test_transaction_api.py` | Integration | ✅ 11/11 | ✅ RED before wiring | ✅ 14/14 | ✅ | ✅ removed timedelta import |
| 4.2 full verify (cov/ruff/mypy) | — | — | — | — | ✅ 89% / clean / clean | — | — |
| 5.1 VEL-STORE-006 docstring | — | Docs | — | — | ✅ module docstring | — | — |

## Test Summary

- **Total tests written**: 17 (14 unit + 3 integration)
- **Total tests passing**: 285 (268 baseline + 17 new)
- **Layers used**: Unit (14), Integration (3)
- **Approval tests**: None — no refactoring tasks
- **Pure functions created**: `VelocityStore._key`, `VelocityStore._score` (static)

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `src/services/velocity_store.py` | Created | VelocityStore: constants, `record_transaction`, `get_counts`, `_pg_counts`, error swallowing |
| `src/api/v1/transactions.py` | Modified | Removed Query A; added `Depends(get_velocity_store)`, record + counts; real 1h count |
| `src/core/config.py` | Modified | `velocity_store_enabled: bool = True` |
| `src/core/redis.py` | Modified | `socket_connect_timeout=2.0, socket_timeout=2.0` on pool |
| `src/core/dependencies.py` | Modified | `get_velocity_store()` dependency |
| `tests/conftest.py` | Modified | mock_redis ZSET AsyncMocks + pipeline (execute default `[0,0,0]`) + DI override |
| `tests/unit/test_velocity_store.py` | Created | 14 unit tests (record/read/fallback/toggle) |
| `tests/integration/test_transaction_api.py` | Modified | 3 velocity integration tests + helpers |
| `openspec/changes/redis-velocity-features/tasks.md` | Modified | PR1 tasks marked `[x]` (14/14) |

## Deviations from Design

None — implementation matches design.md. Notes on interpretation:

1. Task 3.3 wording ("exactly one db.execute") applies to the **Redis-up**
   path (FD-VEL-001). With Redis down, `_pg_counts` is a second execute
   (fallback count query, not the removed scan) — asserted as `call_count == 2`
   in the fallback test, consistent with FD-VEL-003.
2. `record_transaction` trim uses real wall-clock now (no `now` seam per the
   design contract) — unit test asserts a tolerance window around the clock.

## Issues Found

- **Budget variance**: actual code delta ~+616/−25 vs design forecast +440/−25.
  Driven by larger test files (13 unit tests vs 12 est, integration +99 vs
  +70) and a more verbose docstring. No scope creep — exactly the 14 PR1
  tasks. Mitigated by the already-chosen feature-branch-chain (PR1 isolated).
- **Enqueue latency noise**: `POST /transactions` still calls `enqueue` with the
  real pool (no DI) — in tests without a local Redis this logs a 2s socket
  timeout per attempt (caught, 201 still returned). Pre-existing pattern,
  unchanged behavior; suite time acceptable (30s).

## Workload / PR Boundary

- **Mode**: chained PR slice (feature-branch-chain) — PR 1 of 2
- **Current work unit**: VelocityStore + hot path + tests + toggle + docs
- **Boundary**: starts at `master` → `chore/redis-velocity-features`; ends with
  all 14 PR1 tasks green and committed. PR 2 (retraining) is a separate later
  run on this branch.
- **Commits**:
  - `f13accb` feat(velocity): add Redis-backed VelocityStore with Postgres fallback
  - `3e829fc` feat(api): wire velocity store into transaction scoring hot path

## Remaining (next batch — PR 2)

- [ ] 1.1–1.3 scripts/generate_synthetic_data.py + train_xgboost_aligned.py velocity columns
- [ ] 2.1 regenerate CSV, 2.2 retrain, 2.3 ML-ALIGN revalidation, 2.4 commit model+CSV

---

# PR 2 — Retraining Alignment (complete)

## Summary

Propagated velocity through the training pipeline (FD-VEL-004):
`scripts/generate_synthetic_data.py` now emits `velocity_5min`/`velocity_1h`
per transaction (fraud `randint(3,15)`/`randint(10,60)`, legit
`randint(0,2)`/`randint(0,5)` — mirrors the trainer) and persists them via a
module-level `FIELDNAMES`; `train_xgboost_aligned.py` keeps velocity in the
generated tx dict, writes/reads the columns in `_save/_load_synthetic_csv`
(`row.get(..., "0")` fallback for legacy CSVs), and replaces the all-zero
synthetic histories with a new pure `build_synthetic_history(tx)` that feeds
the CSV velocity + per-user stat values into FeatureEngine. CSV regenerated
(50,000 rows, 2,420 fraud ≈ 5%, both velocity columns populated in the correct
class ranges), model retrained, ML-ALIGN revalidated (13/13, thresholds
unchanged), and model + CSV committed after revalidation passed.

## Verification

- `pytest tests/ -q` → **294 passed** (285 baseline + 9 new unit tests)
- `pytest tests/test_ml_model.py -q` → **13 passed** (ML-ALIGN: crypto > 20, grocery < 10, 10-feature shape all hold)
- `ruff check src/ scripts/` → touched scripts clean; 10 pre-existing F401 errors remain in untouched `scripts/init_db.py` + `scripts/train_model.py` (on master too — out of scope)
- `mypy src/` → clean (no mypy in venv; run via global `mypy.exe`)

## TDD Cycle Evidence (PR 2)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 standalone generator velocity | `tests/unit/test_training_alignment.py` | Unit | ✅ 285/285 | ✅ Written (ImportError: FIELDNAMES) | ✅ 9/9 | ✅ 300 samples, both classes | ✅ FIELDNAMES constant, class-range constants |
| 1.2 trainer keeps velocity + CSV round-trip | `tests/unit/test_training_alignment.py` | Unit | ✅ 285/285 | ✅ Written (KeyError: velocity_5min) | ✅ 9/9 | ✅ 3 cases (save cols, load cols, legacy fallback) | ✅ constants, removed unused imports |
| 1.3 histories from CSV values | `tests/unit/test_training_alignment.py` | Unit | ✅ 285/285 | ✅ Written (ImportError: build_synthetic_history) | ✅ 9/9 | ✅ map + default-zero + FE propagation (2 vel cases) | ✅ pure `build_synthetic_history` |
| 2.1 regenerate CSV | `scripts/generate_synthetic_data.py` run | Data | ✅ | N/A (data regen) | ✅ 50,000 rows / 2,420 fraud / velocity ranges verified | ✅ per-class max checks | ➖ None needed |
| 2.2 retrain | `scripts/train_xgboost_aligned.py` run | Data | ✅ | N/A | ✅ PR-AUC 1.0000 | ✅ sanity crypto/grocery | ➖ None needed |
| 2.3 ML-ALIGN revalidate | `tests/test_ml_model.py` | Integration | ✅ 13/13 | N/A (threshold check) | ✅ 13/13 | ➖ existing thresholds still valid | ➖ thresholds NOT changed |
| 2.4 commit model+CSV | — | — | — | — | ✅ after 2.3 passed | — | — |

## Training Metrics — before → after

| Metric | Before (velocity=0 features) | After (velocity-aware) |
|--------|------------------------------|------------------------|
| Training data | 50,000 CSV rows, 1% fraud (trainer format, no velocity cols) | 50,000 rows, 4.84% fraud (standalone format, velocity cols populated) |
| Feature matrix | (50000, 10) | (50000, 10) — contract unchanged |
| ML-ALIGN sanity: crypto (50k, 3am, vel 10/50) | ≈ 99.99995 | 100.00 |
| ML-ALIGN sanity: grocery (50, 12pm, vel 0/2) | ≈ 0.00295 | 0.00 |
| PR-AUC / Precision / Recall / F1 / ROC-AUC | not persisted from prior run (binary only in git) | 1.0000 / 1.0000 / 1.0000 / 1.0000 / 1.0000 |
| Confusion (test) | n/a | TN=9516, FP=0, FN=0, TP=484 |
| Optimal cost threshold | 0.50 (documented in commit ab3c632) | 0.50, expected cost 0.00 |

## Test Summary (PR 2)

- **Total tests written**: 9 (all unit, `tests/unit/test_training_alignment.py`)
- **Total tests passing**: 294 (285 baseline + 9 new)
- **Layers used**: Unit (9)
- **Approval tests**: None — no refactoring of existing behavior
- **Pure functions created**: `build_synthetic_history` (train_xgboost_aligned.py)

## Files Changed (PR 2)

| File | Action | What Was Done |
|------|--------|---------------|
| `scripts/generate_synthetic_data.py` | Modified | Velocity class-range constants, `velocity_5min/1h` in tx dict, module `FIELDNAMES` (+2 cols), fraud_count output fix, removed unused numpy import |
| `scripts/train_xgboost_aligned.py` | Modified | Velocity constants; tx dict keeps velocity; `_save/_load_synthetic_csv` velocity cols with "0" fallback; new `build_synthetic_history`; main() histories from CSV values; removed unused imports/`base_date` |
| `data/synthetic_transactions.csv` | Regenerated | 50,000 rows, 5% fraud, velocity + user-stat columns persisted |
| `models/xgboost_paysim_v1.joblib` | Overwritten | Retrained with velocity-aware features (git-tracked rollback) |
| `tests/unit/test_training_alignment.py` | Created | 9 unit tests: generator velocity, CSV round-trip + fallback, history mapping, FeatureEngine propagation |
| `openspec/changes/redis-velocity-features/tasks.md` | Modified | PR2 tasks 1.1–2.4 marked `[x]` (21/21 total) |
| `openspec/changes/redis-velocity-features/apply-progress.md` | Modified | This merged artifact |

`tests/test_ml_model.py` NOT modified — thresholds (>20 / <10) revalidated and still hold with the new model.

## Deviations from Design (PR 2)

1. **Histories include user stats, not only velocity**: task 1.3 says "from CSV
   values" for all four keys; the standalone CSV has `user_avg_amount`/
   `user_std_amount` columns so they are propagated too (design text showed
   `avg_amount: 0.0` but the task wording and the CSV both provide real
   values). `build_synthetic_history` falls back to 0 when absent.
2. **`fraud_count` in the standalone generator was counting every row** (any
   `tx-` prefix) — fixed to count `is_fraud == "1"`; output now prints the real
   count (2,420) instead of 50,000.
3. **ML-ALIGN thresholds unchanged** (design allowed updating them "if shifted"):
   the velocity-aware model still separates crypto+high-vel (>20) from
   grocery+low-vel (<10) with large margin, so no assertion edit was needed.

## Issues Found (PR 2)

- **Perfect test metrics (1.0) are an artifact of the synthetic distribution**:
  velocity windows (3–15 vs 0–2) are non-overlapping, so XGBoost separates the
  holdout perfectly (TN=9516, FP=0, FN=0, TP=484). The previous model behaved
  similarly (crypto ≈ 100 / grocery ≈ 0.003). Not a regression; flag for
  verify/real-world expectations. Cost-optimal threshold remains 0.50.
- **Category vocabulary mismatch**: standalone generator uses
  `low_risk/medium_risk/high_risk` merchant categories, which are NOT in
  `FeatureEngine.HIGH_RISK_CATEGORIES` (cryptocurrency, money_transfer, …), so
  `merchant_risk_level`/`is_crypto` features are 0 for all synthetic training
  rows. Pre-existing standalone-generator behavior; ML-ALIGN still passes
  because the velocity/amount/hour/round signals carry the separation. Noted,
  not fixed (would change the generator's schema — out of PR2 scope).
- **mypy not installed in `.venv`** — verified via global `mypy.exe` (clean).
- Remaining ruff F401s in `scripts/init_db.py` + `scripts/train_model.py` are
  pre-existing and in files outside this change — not touched.

## Workload / PR Boundary (PR 2)

- **Mode**: chained PR slice (feature-branch-chain) — PR 2 of 2
- **Current work unit**: retraining alignment (velocity propagation, CSV regen, retrain, ML-ALIGN)
- **Boundary**: starts on `chore/redis-velocity-features` at PR1 commits; ends
  with all 7 PR2 tasks green and committed. Model + CSV binary diffs isolated
  from PR1's code diff.
- **Commits (PR 2)**:
  - `feat(ml): propagate velocity features through synthetic training pipeline` — scripts + new unit tests
  - `chore(ml): regenerate velocity-aware synthetic CSV and retrain model` — CSV + model binary (post-ML-ALIGN)
  - `docs(sdd): record PR2 apply progress for redis-velocity-features` — tasks.md + apply-progress.md

## Status

21/21 tasks complete (14 PR1 + 7 PR2). **Ready for sdd-verify.**
