# Design: Redis-Backed Velocity Features

## 1. Context

`POST /api/v1/transactions` (src/api/v1/transactions.py:93-138) runs two Postgres queries per request: **Query A** (5-min scan → `recent_txns`) and **Query B** (all-user txns → `known_cards`, avg/std). `user_history.tx_count_last_1h` reuses `len(recent_txns)` (L137) — the 1h feature is a duplicate of the 5-min count. Training (`train_xgboost_aligned.py:73-82`) already *computes* `velocity_5min`/`velocity_1h` per sample but discards them (CSV has no columns; `all_histories` are zeros at L251) — the model trains on velocity=0. Verified: `data/synthetic_transactions.csv` and `models/xgboost_paysim_v1.joblib` are git-tracked → `git revert` restores both. `redis==5.2.*` already installed; no fakeredis. `created_at` is tz-aware Python-side after flush (base.py:26) → usable as ZSET score.

**Specs implemented**: VEL-STORE-001..007 + delta FD-VEL-001..004.

## 2. Architecture Overview

```
POST /api/v1/transactions
  │ create_transaction() ──▶ txn (id, created_at)
  │ record_transaction(user, txn.id, created_at)      [ZADD+EXPIRE+ZREMRANGEBYSCORE, 1 RTT, best-effort]
  │ get_counts(user, db)  ──▶ Redis pipeline (3 cmds, 1 RTT): trim>24h → ZCOUNT 5min → ZCOUNT 1h
  │   └─ RedisError/Timeout/OSError ──▶ _pg_counts(db)  [1 PG query: created_at, last 1h, not deleted → split 5min]
  │ Query B (kept) ──▶ known_cards + avg/std
  │ context.recent_transactions = counts["5min"]   (rule high_velocity > 3)
  │ user_history = {avg, std, tx_count_last_5min: counts["5min"], tx_count_last_1h: counts["1h"]}
  ▼
ScoreResponse (unchanged) + enqueue (unchanged, still best-effort)
```

The new txn is recorded **before** counts are read, so it counts toward its own window — identical semantics to today (Query A ran in the same session after flush and saw the new row). Cold start = counts 0 (accepted, proposal risk). Per request with Redis up: **1 PG query + 1 Redis RTT** (was 2 PG queries).

## 3. Architecture Decisions

### Decision: VelocityStore as service reached via FastAPI dependency

| Option | Tradeoff | Decision |
|---|---|---|
| `get_velocity_store` DI dependency in dependencies.py | Matches get_db/get_redis override pattern in conftest; tests inject `VelocityStore(redis=mock_redis)` cleanly | **CHOSEN** |
| Module singleton `_velocity_store` + monkeypatch in tests | Matches `_rule_engine` precedent, but per-test monkeypatching is noisy | Rejected |
| Handler calls `get_redis()` directly | Couples endpoint to Redis internals; fallback logic leaks into the hot path | Rejected |

Handler gets `velocity_store: VelocityStore = Depends(get_velocity_store)`.

### Decision: Postgres fallback lives inside the store (`_pg_counts`), not the endpoint

| Option | Tradeoff | Decision |
|---|---|---|
| Private `_pg_counts(db)` on VelocityStore | One seam, one place to toggle/test; `get_counts(user, db)` mirrors service-layer convention (services take `db`) | **CHOSEN** |
| Fallback in endpoint | Scattering; spec VEL-STORE-005 is a store responsibility | Rejected |
| Fail-closed (500) | Violates "never 500 on Redis failure" (proposal + enqueue precedent) | Rejected |

Fallback = 1 query `select(Transaction.created_at) where user_id AND deleted_at IS NULL AND created_at >= now-1h`, split in Python at 5 min. Note: fallback excludes soft-deleted (matches Query A); Redis path includes them ≤24h — divergence accepted per VEL-STORE-006.

### Decision: Record-before-read (self-inclusion)

Recording before `get_counts` keeps today's rule semantics: the 4th txn in 5 min fires `high_velocity`. Accepted side effect: a Redis member may exist for a txn whose PG commit later fails (ghost count until 24h trim) — same window as the existing enqueue-before-commit pattern; documented.

### Decision: Key/score convention and window inclusivity

`velocity:{user_id}:tx`, score = `int(created_at.timestamp() * 1000)` (epoch ms), member = `str(txn.id)` (decode_responses=True pool → str). `ZADD` with the same member is idempotent (VEL-STORE-001). `ZCOUNT(min, "+inf")` is **inclusive** of `min` → boundary txn at exactly 5 min counts (VEL-STORE-002). Read pipeline order honors VEL-STORE-004 ("trim before counting"): `ZREMRANGEBYSCORE(-inf, now-86400s)` → `ZCOUNT` 5min → `ZCOUNT` 1h. Write pipeline: `ZADD` → `EXPIRE 90000s` (25h, covers trim + slack) → trim. Both 1 RTT.

### Decision: Error handling — RedisError family, not bare Exception

| Layer | Catch | Behavior |
|---|---|---|
| record | `(RedisError, TimeoutError, OSError)` | swallow + `logger.warning`; never raises (VEL-STORE-001) |
| read | same | log + `_pg_counts` fallback (VEL-STORE-005) |

Deliberately NOT bare `Exception`: spec only requires resilience to Redis unavailability; a programming bug in the store should still fail loudly. `redis.exceptions.TimeoutError` subclasses `RedisError`; `OSError` covers socket-level escapes.

### Decision: Pool-level socket timeouts in core/redis.py

Add `socket_connect_timeout=2.0, socket_timeout=2.0` to `ConnectionPool.from_url`. Without them a wedged Redis connection could hang the hot path indefinitely (default = None). redis-py temporarily disables socket timeout for blocking `BRPOP`/`BLPOP` → `dequeue` unaffected. Bounds both the new velocity calls and the existing `enqueue`.

### Decision: Config toggle `velocity_store_enabled` (default True)

`src/core/config.py` Feature Flags: `velocity_store_enabled: bool = True`. When False: `record_transaction` no-ops and `get_counts` short-circuits to `_pg_counts` (VEL-STORE-007, rollback path). No env var wiring needed beyond the setting.

### Decision: No fakeredis dependency

AsyncMock-based tests match the repo's established mocking style (conftest mock_db/mock_redis). ZCOUNT inclusivity is well-defined (inclusive both bounds); covered by asserting window minima. fakeredis would add a dep + async compatibility risk for marginal fidelity. Rejected.

### Decision: Retraining — propagate the values, regenerate CSV, overwrite v1

- `train_xgboost_aligned.py::generate_synthetic_data`: keep the already-computed `velocity_5min`/`velocity_1h` (L73-74, L81-82) in the tx dict (+2 lines).
- `_save_synthetic_csv`: fieldnames += `velocity_5min`, `velocity_1h`; `_load_synthetic_csv`: `row.get(..., "0")` fallback (backward-compatible with the current column-less CSV).
- `main()` L251: build synthetic histories `{"avg_amount": 0.0, "std_amount": 0.0, "tx_count_last_5min": …, "tx_count_last_1h": …}` from the CSV values instead of `[{}]*len`.
- `scripts/generate_synthetic_data.py`: add `velocity_5min` (fraud `randint(3,15)`, legit `randint(0,2)`) and `velocity_1h` (fraud `randint(10,60)`, legit `randint(0,5)`) to each tx + fieldnames — mirrors the trainer so either generator persists both columns (FD-VEL-004).
- Regenerate: `python scripts/generate_synthetic_data.py` (5% fraud, richer schema — trainer reads only its 5 keys + velocity, all present).
- Retrained model overwrites git-tracked `models/xgboost_paysim_v1.joblib` **only after** ML-ALIGN revalidation passes; old binary recoverable via git (rollback plan 3).

### Decision: ML-ALIGN revalidation procedure

1. Regen CSV → 2. `python scripts/train_xgboost_aligned.py` (velocity-aware features; note: SMOTE now sees non-zero velocity columns) → 3. `pytest tests/test_ml_model.py -q`: `>20` (crypto+high-vel) / `<10` (grocery, low-vel) / 10-feature shape. If the velocity-aware distribution shifts scores, revalidate thresholds from training log + sanity check, update the two assertions with documented old→new values, and record them in verify-report. Do NOT commit the new model/CSV until these pass.

## 4. Interfaces / Contracts

```python
# src/services/velocity_store.py (new)
class VelocityStore:
    def __init__(self, redis: Redis | None = None) -> None: ...   # None → get_redis() per call (enqueue precedent)
    async def record_transaction(self, user_id: UUID, transaction_id: UUID,
                                 created_at: datetime | None = None) -> None: ...  # best-effort, never raises
    async def get_counts(self, user_id: UUID, db: AsyncSession, *,
                         now: datetime | None = None) -> dict[str, int]: ...  # {"5min": n, "1h": m}; now = test seam
```

Constants: `VELOCITY_TTL_SECONDS = 90_000`, `TRIM_SECONDS = 86_400`, `WINDOW_5MIN = 300`, `WINDOW_1H = 3600` (seconds; ×1000 for ms scores).

Hot-path delta (transactions.py, after L91, before "2. Build context"):

```python
    await _velocity_store.record_transaction(payload.user_id, txn.id, txn.created_at)
    counts = await _velocity_store.get_counts(payload.user_id, db)
    # (Query A block L95-102 DELETED; Query B L104-111 unchanged)
    ...
    context = { ..., "recent_transactions": counts["5min"], ... }
    user_history = {
        "avg_amount": ...same..., "std_amount": ...same...,
        "tx_count_last_5min": counts["5min"],
        "tx_count_last_1h": counts["1h"],          # FIX: real 1h count
    }
```

DI seam (dependencies.py): `def get_velocity_store() -> VelocityStore: return VelocityStore()`.

## 5. Testing Strategy (strict TDD — RED first)

| Layer | Test | RED seed → GREEN |
|---|---|---|
| Unit (`tests/unit/test_velocity_store.py`, new) | record: ZADD key `velocity:{uid}:tx`, member `str(txn.id)`, score=epoch ms; EXPIRE 90000; trim; pipeline 1 RTT; idempotent same member | Fake redis via `VelocityStore(redis=fake)`; assert pipe calls |
| Unit | read: ZCOUNT mins = now-300_000 / -3_600_000 (boundary inclusive, VEL-STORE-002); maps `[0, 2, 8] → {"5min": 2, "1h": 8}`; empty → 0/0; per-user key isolation (VEL-STORE-003) | `now=` param for determinism |
| Unit | Redis error on record → no raise (VEL-STORE-001); on read → `_pg_counts` (mock_db rows split at 5 min) + warning log (VEL-STORE-005); `deleted_at` filter; disabled flag → PG only, zero Redis calls (VEL-STORE-007) | `pipe.execute` raises `redis.exceptions.ConnectionError` |
| Integration (`tests/integration/test_transaction_api.py`, modified) | seeded `zcount=[4,4]` → 201 + `"high_velocity" in fired_rules` (rule fires >3, self-inclusive); `zcount=[2,7]` → called with both window mins (1h≠5min regression, FD-VEL-002); pipe raises → 201 via PG fallback (FD-VEL-003, caplog warning); execute called **once** (Query B only) with Redis up (FD-VEL-001 Query A removed) | conftest: add `get_velocity_store` override + ZSET mock methods |
| Regression | existing POST tests stay green with default `zcount=0` (no velocity); test_integration_pipeline.py unaffected (mock scrolls `.scalars().all()` → fine) | — |
| Retraining | ML-ALIGN class revalidated (see Decision); FeatureEngine unit tests untouched (keys unchanged) | — |

conftest extension: `mock_redis` gains `zadd/expire/zremrangebyscore/zcount` AsyncMocks (defaults 0/1, True) + `pipeline = MagicMock()` whose `zcount` defaults 0 and `execute` returns `[0, 0, 0]`. Tests needing both record+read pipelines use `redis.pipeline.side_effect = [pipe_record, pipe_read]`.

## 6. File Changes

| File | Action | Change | Lines |
|---|---|---|---|
| `src/services/velocity_store.py` | Create | VelocityStore service (record/get_counts/_pg_counts, constants) | ~120 |
| `src/api/v1/transactions.py` | Modify | Del Query A (L95-102); add velocity_store param + record + counts; rewrite context/user_history | −25/+20 |
| `src/core/config.py` | Modify | `velocity_store_enabled: bool = True` (Feature Flags) | +2 |
| `src/core/redis.py` | Modify | Pool socket timeouts (2s) | +2 |
| `src/core/dependencies.py` | Modify | `get_velocity_store` dependency | +6 |
| `tests/conftest.py` | Modify | ZSET mocks + `get_velocity_store` override | +15 |
| `tests/unit/test_velocity_store.py` | Create | Unit suite (~12 tests, table §5) | ~180 |
| `tests/integration/test_transaction_api.py` | Modify | 4 new POST tests + seeding helper | +70 |
| `scripts/train_xgboost_aligned.py` | Modify | Propagate velocity → dict/CSV/loader/histories | +20/−2 |
| `scripts/generate_synthetic_data.py` | Modify | velocity columns per tx + fieldnames | +10 |
| `data/synthetic_transactions.csv` | Regenerate | run standalone generator after change | full rewrite |
| `tests/test_ml_model.py` | Modify | Revalidated ML-ALIGN thresholds (verify-report records values) | ±10 |

Total ≈ +435/−27. **Guard lines**: `Decision needed before apply: Yes`, `Chained PRs recommended: Yes`, `400-line budget risk: Medium` — PR1 = Redis store + hot path + tests (≈+420 incl. new files), PR2 = retraining/CSV/ML-ALIGN (model+CSV binary diffs isolated).

## 7. Migration / Rollout

No DB migration, no schema change. Rollout: deploy with `velocity_store_enabled=true`; rollback = set flag false (instantly returns to PG-only path) or `git revert` (model + CSV are git-tracked). Redis disposable — no data loss on revert. Cold-start counts=0 accepted transient. No ZREM on soft-delete (VEL-STORE-006 documents).

## 8. Risks & Open Questions

| Risk | Severity | Mitigation |
|---|---|---|
| Redis down at read → fallback query adds latency | Low | 1 extra PG query only on failure; socket timeouts bound hangs |
| Ghost member if PG commit fails after record | Low | 24h trim; bounded; documented (mirrors enqueue pattern) |
| Retrained model distribution shift breaks ML-ALIGN thresholds | Med | Revalidate before commit; old model via git; thresholds updated + documented |
| Two generators diverge (trainer 1% fraud vs standalone 5%) | Low | Both emit velocity; trainer is canonical for training; CSV regen explicit step |
| Phantom count after soft-delete ≤24h | Low | Accepted per VEL-STORE-006 |

**Open questions**: None blocking. Inherited proposal decisions confirmed: ZREM-on-delete deferred (VEL-STORE-006), overwrite v1 (git-tracked rollback).