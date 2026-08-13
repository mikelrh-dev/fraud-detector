# Apply Progress — redis-velocity-features (PR 1)

**Change**: redis-velocity-features
**Batch**: PR 1 — VelocityStore + hot path wiring + unit/integration tests + config toggle + docs
**Branch**: `chore/redis-velocity-features` (feature-branch-chain, base for PR 2)
**Mode**: Strict TDD (RED → GREEN → REFACTOR)
**Status**: ✅ COMPLETE — 14/14 PR1 tasks done. Ready for sdd-verify.

## Summary

Implemented the Redis-backed velocity path end to end: a new `VelocityStore`
service (ZSET record + 5min/1h count pipeline + Postgres fallback), wired into
`POST /api/v1/transactions` replacing Query A, with a config toggle
(`velocity_store_enabled`), Redis socket timeouts, a DI dependency, extended
`mock_redis` fixture, 14 unit tests and 3 new integration tests. The
`tx_count_last_1h` bug (duplicate of the 5-min count) is fixed: it now comes
from a real 1-hour ZCOUNT window. PR 2 (retraining alignment, tasks 1.1–2.4 of
the PR 2 section) is intentionally NOT started.

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
