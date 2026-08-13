# Tasks: Redis-Backed Velocity Features

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ≈ +420/−25; PR2 ≈ +30 + CSV/model binary diffs; total ≈ +450/−27 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (store + hot path + tests) → PR 2 (retraining alignment) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | VelocityStore + hot path wiring + tests | PR 1 | Base: tracker branch `chore/redis-velocity-features`; unit + integration tests shipped with code; autonomous + verifiable |
| 2 | Retraining alignment (CSV regen, velocity history, ML-ALIGN) | PR 2 | Base: PR 1 branch; depends on PR 1; model/CSV binary diffs isolated here |

## PR 1 — VelocityStore Service + Hot Path (base: chore/redis-velocity-features)

### Phase 1: RED — Unit tests

- [x] 1.1 Write `tests/unit/test_velocity_store.py` failing tests: record ZADD key `velocity:{uid}:tx`, member `str(txn.id)`, score=epoch ms, EXPIRE 90000, trim, 1 pipeline RTT, idempotent re-record [VEL-STORE-001, VEL-STORE-004]
- [x] 1.2 Add failing read tests: inclusive ZCOUNT mins = now−300s/−3600s, mapping `[0,2,8]→{"5min":2,"1h":8}`, empty→0/0, per-user key isolation [VEL-STORE-002, VEL-STORE-003]
- [x] 1.3 Add failing failure tests: record RedisError→no raise; read RedisError→`_pg_counts` + warning; `_pg_counts` excludes `deleted_at`; flag off→zero Redis calls [VEL-STORE-005, VEL-STORE-007]

### Phase 2: GREEN — Service + infra

- [x] 2.1 Create `src/services/velocity_store.py`: constants (TTL 90000 / trim 86400 / windows 300+3600), `record_transaction`, `get_counts`, `_pg_counts` (1h select, split at 5min), swallow `(RedisError, TimeoutError, OSError)` + logger.warning [VEL-STORE-001..006]
- [x] 2.2 Add `velocity_store_enabled: bool = True` to `src/core/config.py` Feature Flags [VEL-STORE-007]
- [x] 2.3 Add `socket_connect_timeout=2.0, socket_timeout=2.0` to `src/core/redis.py` pool [VEL-STORE-005]
- [x] 2.4 Add `get_velocity_store()` dependency in `src/core/dependencies.py` [FD-VEL-001]

### Phase 3: RED — Integration tests

- [ ] 3.1 Extend `tests/conftest.py`: mock_redis ZSET AsyncMocks + `pipeline` (default execute `[0,0,0]`) + `get_velocity_store` override [FD-VEL-001]
- [ ] 3.2 Add failing POST tests: seeded zcount `[4,4]`→201 + `"high_velocity"` in fired_rules; `[2,7]`→both window mins, 1h≠5min [FD-VEL-001, FD-VEL-002]
- [ ] 3.3 Add failing test: pipeline raises→201 via PG fallback + caplog warning; exactly one `db.execute` (Query B only) [FD-VEL-003, FD-VEL-001]
- [ ] 3.4 Verify existing POST tests stay green with default zcount=0 (regression) [FD-VEL-002]

### Phase 4: GREEN — Hot path wiring

- [ ] 4.1 Modify `src/api/v1/transactions.py`: `Depends(get_velocity_store)`; record txn; `get_counts`; delete Query A (L95-102); `context.recent_transactions`=5min; `user_history` 5min/1h from counts [FD-VEL-001, FD-VEL-002]
- [ ] 4.2 Run `pytest tests/ -v --cov=src` (≥80%), `ruff check src/`, `mypy src/` — all green [Success criteria]

### Phase 5: Documentation

- [ ] 5.1 Document VEL-STORE-006 accepted divergence (Redis includes soft-deleted ≤24h vs PG fallback excludes) in `velocity_store.py` docstring [VEL-STORE-006]

## PR 2 — Retraining Alignment (base: PR 1 branch)

### Phase 1: Propagate velocity through training pipeline

- [ ] 1.1 Modify `scripts/generate_synthetic_data.py`: add `velocity_5min`/`velocity_1h` to `generate_transaction` dict + fieldnames [FD-VEL-004]
- [ ] 1.2 Modify `scripts/train_xgboost_aligned.py`: keep velocity in tx dict (L73-82); `_save_synthetic_csv` fieldnames += both; `_load_synthetic_csv` `row.get(..., "0")` fallback [FD-VEL-004]
- [ ] 1.3 Replace `[{}]*len` synthetic histories (L251) with per-sample `{"avg_amount", "std_amount", "tx_count_last_5min", "tx_count_last_1h"}` from CSV values [FD-VEL-004]

### Phase 2: Regenerate, retrain, revalidate

- [ ] 2.1 Regenerate CSV: `python scripts/generate_synthetic_data.py` (persists both velocity columns) [FD-VEL-004]
- [ ] 2.2 Retrain: `python scripts/train_xgboost_aligned.py` (velocity-aware features) [FD-VEL-004]
- [ ] 2.3 Revalidate ML-ALIGN: `pytest tests/test_ml_model.py -q` — crypto+high-vel >20, grocery+low-vel <10, 10-feature shape; update thresholds in `tests/test_ml_model.py` with documented old→new values if shifted [FD-VEL-004]
- [ ] 2.4 Commit new `models/xgboost_paysim_v1.joblib` + CSV only after 2.3 passes (git-tracked rollback) [FD-VEL-004]
