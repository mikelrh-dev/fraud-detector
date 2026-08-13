# Proposal: Redis-Backed Velocity Features

## Intent

Offload velocity counting in `POST /api/v1/transactions` from Postgres (Query A) to Redis Sorted Sets; fix the bug where `tx_count_last_1h` reuses the 5-min count (`transactions.py:137`); retrain XGBoost with velocity-aware features (currently trained with velocity=0 everywhere).

## Business Problem

- **Pain**: extra DB query per request + wrong 1h velocity feature weaken the risk signal.
- **Users**: fraud analysts (better signal), ops (less DB load).
- **Rules**: scores 0-100; rule engine first; LLM only explains; soft delete; Redis failure never 500 (`enqueue` precedent).

## Current-State Gap

- `tx_count_last_1h` = `len(recent_txns)` (5-min) — duplicate, no real 1h aggregation.
- `generate_synthetic_data` (train_xgboost_aligned.py:73-82) generates `velocity_5min`/`velocity_1h` but discards them; training sees zeros.
- Query A (5-min scan) runs per request.

## Scope

### In Scope

1. `VelocityStore` service (`src/services/velocity_store.py`): ZADD/ZCOUNT pipeline, 24h trim, EXPIRE renewal, Postgres fallback.
2. Wire into POST /transactions: record txn, read real 5min/1h counts → `context.recent_transactions` + `user_history` (fixes 1h bug). Query B kept.
3. Retrain XGBoost propagating already-generated velocity values; regenerate CSV; revalidate ML-ALIGN thresholds.
4. Tests (strict TDD, RED first): unit + integration; extend `tests/conftest.py::mock_redis` (zadd/zcount/zremrangebyscore/expire).

### Out of Scope

- `amount_sum_24h` + `ip_distinct_count_1h` (needs IP in schema/payload; vector 12+; full regen)
- Removing Query B (known_cards/history stay DB-backed)
- ZREM on soft-delete

## Capabilities

### New Capabilities

- `velocity-store`: Redis sliding-window velocity counts (5min/1h) with Postgres fallback.

### Modified Capabilities

- `fraud-detection`: `tx_count_last_1h` becomes a real 1-hour count; pipeline resilient to Redis failure.

## Approach

ZSET score = txn timestamp. ZADD pipeline + ZCOUNT one round-trip; trim >24h; EXPIRE on ZADD. Redis error → Postgres queries (never raise). Retrain same change to keep train/serve aligned.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/services/velocity_store.py` | New | VelocityStore service |
| `src/api/v1/transactions.py` | Modified | Record + read counts; Query A replaced |
| `scripts/train_xgboost_aligned.py` | Modified | Propagate velocity; regenerate CSV |
| `tests/conftest.py` + tests | Modified/New | mock_redis ZSET methods; new tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Redis down | Med | Postgres fallback; never 500; log |
| Cold start counts=0 | Med | Accept; transient sub-detection |
| OOD distribution shift | Med | Retrain + revalidate thresholds |
| Soft-deleted txns counted ≤24h | Low | Accept; documented |
| ZSET growth | Low | 24h trim + EXPIRE renewal |

## Rollback Plan

1. Config toggle `velocity_store_enabled` preserves old Postgres path.
2. Keep `models/xgboost_paysim_v1.joblib`; revert if retrained model fails validation.
3. `git revert` — soft delete means no data loss; Redis disposable.

## Dependencies

- Redis 7 (docker-compose; ZSET native)
- Regenerated `data/synthetic_transactions.csv`
- XGBoost training env

## Open Decisions

1. Postgres fallback (recommended) vs fail-closed?
2. ZREM deleted txns from velocity sets now or defer?
3. Retrained model: overwrite v1 or v2 behind config?

## Success Criteria

- [ ] 1h count differs from 5min with txns >5min old
- [ ] Redis failure → Postgres fallback, HTTP 201 (no 500)
- [ ] Query A removed from hot path (velocity via Redis)
- [ ] High-velocity fraud scores > low-velocity legitimate
- [ ] pytest green, coverage ≥80%, ruff + mypy clean