# Archive Report: Redis-Backed Velocity Features

---

## Section 1: Header

| Field | Value |
|-------|-------|
| Change name | `redis-velocity-features` |
| Project | `fraud-detector` |
| Branch | `chore/redis-velocity-features` (feature-branch-chain: PR 1 + PR 2) |
| Archive date | 2026-08-13 |
| Status | **ARCHIVED** ✓ |

---

## Section 2: Lifecycle Summary

The change offloaded velocity counting in `POST /api/v1/transactions` from Postgres (Query A) to Redis Sorted Sets via a new `VelocityStore` service, fixed the bug where `tx_count_last_1h` duplicated the 5-minute count, and retrained XGBoost with real velocity-aware features. Verified PASS and archived on 2026-08-13.

| Phase | Detail |
|-------|--------|
| **Proposed** | 2026-08-13 — Pain: extra DB query per request + wrong 1h velocity feature weaken the risk signal. Rules: scores 0-100; rule engine first; Redis failure never 500; soft delete. |
| **Spec** | New capability `velocity-store` (VEL-STORE-001..007, 9 scenarios) + 4 ADDED requirements on `fraud-detection` (FD-VEL-001..004, 7 scenarios). Additive — no existing requirements modified. |
| **Design** | VelocityStore service via `get_velocity_store` DI; ZSET key `velocity:{user_id}:tx`, score = epoch ms, member = `str(txn.id)`; read pipeline trim → ZCOUNT 5min → ZCOUNT 1h (1 RTT, inclusive minima); TTL 90000s / trim 86400s / windows 300+3600; `_pg_counts` Postgres fallback; config toggle `velocity_store_enabled` (default True); retraining alignment (FD-VEL-004). |
| **Tasks** | 21 tasks across 2 chained PRs — 14 PR1 (VelocityStore + hot path + tests) + 7 PR2 (retraining alignment). Strict TDD (RED → GREEN → REFACTOR) on code tasks. |
| **Apply** | 7 commits across 2 PR slices (feature-branch-chain): PR1 = f13accb, 3e829fc, 32be73f; PR2 = 1324411, e182949, f6a2b4e, 7a9ed77. 26 new tests (14 unit velocity_store + 9 unit training_alignment + 3 integration). |
| **Verify** | **PASS** — 21/21 tasks complete; 294/294 tests green (268 baseline intact); 19/19 spec scenarios compliant; coverage 89% ≥ 80%; mypy clean; ruff clean on all 7 changed files. 0 critical findings. |
| **Archive** | 2026-08-13 — FD-VEL-001..004 delta merged into capability spec (`openspec/specs/fraud-detection/spec.md`); `velocity-store` spec already canonical; status updated to ARCHIVED. |

### Branch History

```
f13accb — feat(velocity): add Redis-backed VelocityStore with Postgres fallback   (PR1)
3e829fc — feat(api): wire velocity store into transaction scoring hot path        (PR1)
32be73f — docs(sdd): record PR1 apply progress for redis-velocity-features        (PR1)
1324411 — feat(ml): propagate velocity features through synthetic training pipeline (PR2)
e182949 — chore(ml): regenerate velocity-aware synthetic CSV and retrain model    (PR2)
f6a2b4e — docs(sdd): record PR2 apply progress for redis-velocity-features        (PR2)
7a9ed77 — docs(sdd): mark PR2 handoff complete in merged apply-progress           (PR2)
HEAD → chore/redis-velocity-features
```

---

## Section 3: Final Statistics

| Metric | Value |
|--------|-------|
| Total commits | **7** (3 PR1 + 4 PR2) |
| Delivery | **2 chained PRs** (feature-branch-chain), tracker branch `chore/redis-velocity-features` |
| Tests | **294** passed (268 baseline + 26 new) |
| New test files | **2** (`tests/unit/test_velocity_store.py` 14, `tests/unit/test_training_alignment.py` 9) |
| Extended test files | `tests/integration/test_transaction_api.py` (+3), `tests/conftest.py` (mock_redis ZSET), `tests/test_ml_model.py` (ML-ALIGN revalidated 13/13, thresholds unchanged) |
| Coverage | **89%** (threshold 80%) — `velocity_store.py` 100%, `transactions.py` 91% |
| Static checks | ruff clean on changed files (10 F401s pre-existing in untouched scripts), mypy clean (50 files) |
| Spec scenarios | **19/19** compliant (VEL-STORE 9 + FD-VEL 7 + ML-ALIGN revalidation) |
| Critical findings | **0** |
| Warning findings | **2** (informational coverage notes, pre-existing lint) |
| Suggestion findings | **4** (S1–S4, see Section 6) |

### Files Changed — NEW (4) + MODIFIED (10)

| File | Action | Change |
|------|--------|--------|
| `src/services/velocity_store.py` | **NEW** | VelocityStore: ZADD/ZCOUNT pipeline, trim, TTL, `_pg_counts` fallback, `_REDIS_UNAVAILABLE` swallowing |
| `src/api/v1/transactions.py` | Modified | `Depends(get_velocity_store)`; record txn; Query A deleted; real 5min/1h counts into context + user_history |
| `src/core/config.py` | Modified | `velocity_store_enabled: bool = True` feature flag |
| `src/core/redis.py` | Modified | `socket_connect_timeout=2.0, socket_timeout=2.0` on pool |
| `src/core/dependencies.py` | Modified | `get_velocity_store()` dependency |
| `tests/conftest.py` | Modified | mock_redis ZSET AsyncMocks + pipeline (execute default `[0,0,0]`) + DI override |
| `tests/unit/test_velocity_store.py` | **NEW** | 14 unit tests (record/read/fallback/toggle) |
| `tests/integration/test_transaction_api.py` | Modified | 3 velocity integration tests (high_velocity, window mins, PG fallback) |
| `scripts/generate_synthetic_data.py` | Modified | Velocity class-range constants, `velocity_5min/1h` columns, module `FIELDNAMES`, fraud_count fix |
| `scripts/train_xgboost_aligned.py` | Modified | Velocity propagation, `_save/_load_synthetic_csv` velocity cols + "0" fallback, pure `build_synthetic_history` |
| `data/synthetic_transactions.csv` | Regenerated | 50,000 rows, 2,420 fraud ≈ 5%, velocity columns populated |
| `models/xgboost_paysim_v1.joblib` | Overwritten | Retrained velocity-aware (git-tracked rollback) |
| `tests/unit/test_training_alignment.py` | **NEW** | 9 unit tests (generator velocity, CSV round-trip, history mapping, FeatureEngine propagation) |

---

## Section 4: Spec Coverage Summary

### Delta Spec Integration

The delta spec at `openspec/changes/redis-velocity-features/specs/fraud-detection/spec.md` contains 4 ADDED requirements. Per the archive convention, the delta requirements were **merged into the main capability spec** (`openspec/specs/fraud-detection/spec.md`): appended as new requirement sections under `## Requirements` with their IDs preserved (FD-VEL-001..004) and all 7 scenarios intact. All pre-existing requirements (Transaction CRUD, Rule Engine Scoring, ML Anomaly Detection, Ensemble Scoring, Fraud Alert Generation, Fraud Score Persistence) were left untouched. The archived change folder retains the original delta spec for independent auditability.

The new capability spec `openspec/specs/velocity-store/spec.md` was created directly as canonical during the spec phase and is final as-is (VEL-STORE-001..007).

### ADDED Requirements — fraud-detection (4 total, 7 scenarios)

| Requirement | ID | Scenarios | Status |
|-------------|----|-----------|--------|
| Velocity Context from VelocityStore | FD-VEL-001 | 2/2 | ✓ VERIFIED |
| Real 1-Hour Velocity Count | FD-VEL-002 | 2/2 | ✓ VERIFIED |
| Scoring Resilient to Velocity Store Failure | FD-VEL-003 | 1/1 | ✓ VERIFIED |
| Velocity-Aware Training Data | FD-VEL-004 | 2/2 | ✓ VERIFIED |

### New Capability Requirements — velocity-store (7 total, 9 scenarios)

| Requirement | ID | Status |
|-------------|----|--------|
| Velocity Write Path | VEL-STORE-001 | ✓ VERIFIED |
| Velocity Read Path — 5min/1h Counts | VEL-STORE-002 | ✓ VERIFIED |
| Per-User Isolation | VEL-STORE-003 | ✓ VERIFIED |
| 24-Hour Trim and TTL Renewal | VEL-STORE-004 | ✓ VERIFIED |
| Postgres Fallback | VEL-STORE-005 | ✓ VERIFIED |
| Soft-Delete Accounting | VEL-STORE-006 | ✓ VERIFIED (by design/doc — permissive MAY clause, see S1) |
| Configuration Toggle | VEL-STORE-007 | ✓ VERIFIED |

### Verification Evidence (from `verify-report.md`)

| Requirement | Evidence |
|-------------|----------|
| VEL-STORE-001 | `test_zadd_key_member_score_expire_and_trim_one_pipeline`, `test_record_uses_current_time_when_created_at_missing`, `test_re_record_same_transaction_uses_same_member`, `test_record_never_raises_on_redis_failures` (3 params) |
| VEL-STORE-002 | `test_maps_pipeline_results_to_both_windows` (`[0,2,8]→{5min:2,1h:8}`), inclusive min = now−300_000ms, `test_pg_fallback_counts_txn_at_exactly_five_minutes` |
| VEL-STORE-003 | `test_counts_isolated_per_user_key` |
| VEL-STORE-004 | ZREMRANGEBYSCORE −inf→now−86400s queued before ZCOUNT, EXPIRE 90000 asserted (1 RTT) |
| VEL-STORE-005 | `test_record_never_raises_on_redis_failures`, `test_read_redis_error_falls_back_to_postgres_and_logs`, integration `test_redis_down_falls_back_to_postgres` (201, caplog warning) |
| VEL-STORE-006 | Docstring documents divergence (task 5.1); `test_pg_fallback_excludes_soft_deleted` contrasts PG path; no ZREM on delete by construction |
| VEL-STORE-007 | `test_toggle_disabled_uses_postgres_only` |
| FD-VEL-001 | `test_velocity_count_fires_high_velocity_rule` (seeded 4); `test_1h_count_is_distinct_from_5min_and_no_query_a` (`mock_db.execute.call_count == 1`) + git diff proof (Query A deleted) |
| FD-VEL-002 | Both window mins queried (`mins[0] != mins[1]`); `test_empty_set_returns_zero_counts`; existing POST tests with default zcount=0 |
| FD-VEL-003 | `test_redis_down_falls_back_to_postgres` (201, `call_count==2`, warning) |
| FD-VEL-004 | `tests/unit/test_training_alignment.py` (FIELDNAMES, per-class ranges, round-trip, legacy fallback, FeatureEngine propagation) + regenerated CSV header/rows (fraud vel 7/50, legit 2/1) + ML-ALIGN revalidated (13/13) |

---

## Section 5: Artifacts Persisted

### Filesystem (OpenSpec)

| Artifact | Location |
|----------|----------|
| Proposal | `openspec/changes/redis-velocity-features/proposal.md` |
| Delta spec | `openspec/changes/redis-velocity-features/specs/fraud-detection/spec.md` |
| Tasks | `openspec/changes/redis-velocity-features/tasks.md` (21/21 complete) |
| Apply progress | `openspec/changes/redis-velocity-features/apply-progress.md` (PR1 + PR2 merged) |
| Verify report | `openspec/changes/redis-velocity-features/verify-report.md` |
| Archive report | `openspec/changes/redis-velocity-features/archive-report.md` **(this file)** |
| Main spec (updated) | `openspec/specs/fraud-detection/spec.md` — FD-VEL-001..004 appended, IDs preserved |
| Main spec (canonical) | `openspec/specs/velocity-store/spec.md` — created during spec phase, final |

### Engram (Persistent Memory)

| Topic Key | Description |
|-----------|-------------|
| `sdd/redis-velocity-features/archive-report` | **(this save)** — archive report |

---

## Section 6: Outstanding Work (Not Blocking)

### Warnings from Verification (2 total)

| ID | Finding | Severity | Notes |
|----|---------|----------|-------|
| W1 | Changed-file coverage below 80% for `dependencies.py` (75%) and `redis.py` (65%) | WARNING | Pre-existing files touched by ≤2 lines each; untested lines are pre-existing auth/queue paths. Informational per Strict TDD rules; not blocking. |
| W2 | `ruff check src/ scripts/` exits 1 on 10 F401s | WARNING | Pre-existing in untouched `scripts/init_db.py` + `scripts/train_model.py`; confirmed on master. Out of scope. |

### Suggestions from Verification (4 total)

| ID | Suggestion | Rationale |
|----|------------|-----------|
| S1 | Direct test for VEL-STORE-006 Redis-path soft-delete inclusion | Permissive MAY clause with no failure mode; docstring + PG-fallback contrast only. |
| S2 | FeatureEngine-level assertion (`features[3]` vs `features[4]`) for FD-VEL-002 | `ScoreResponse` doesn't expose `user_history`; pipeline seam is the correct seam today. |
| S3 | Validate retrained model against real-world distribution | Perfect metrics (PR-AUC 1.0000, FP=0/FN=0) are an artifact of non-overlapping synthetic velocity windows (fraud 3–15 vs legit 0–2). |
| S4 | Workspace hygiene: untracked `mejoras_portfolio_fraud_detector.zip` + folder | Unrelated to this change; consider gitignore or cleanup. |

### Deferred Items

| Item | Status |
|------|--------|
| `amount_sum_24h` feature | **Deferred to a future change** — needs amount aggregation in the velocity store or schema; out of scope. |
| `ip_distinct_count_1h` feature | **Deferred** — needs IP in schema/payload (vector 12+); would require full retrain. |
| Query B removal (known_cards/history stay DB-backed) | **Deferred** — all-user transaction query intentionally kept; only Query A (5-min scan) was removed. |
| ZREM on soft-delete | **Deferred** — accepted behavior: soft-deleted txns MAY count ≤24h (VEL-STORE-006); PG fallback excludes them. |

---

## Section 7: Next Steps for the User

### 1. Delivery (handled by orchestrator)

```bash
# Chained PRs (feature-branch-chain), tracker branch chore/redis-velocity-features:
# PR 1: f13accb..32be73f (VelocityStore + hot path)
# PR 2: 1324411..7a9ed77 (retraining alignment)
```

### 2. Candidate follow-up changes

| Item | Priority |
|------|----------|
| `amount_sum_24h` + `ip_distinct_count_1h` (needs IP in payload; vector 12+; full retrain) | Next logical velocity extension |
| S1: direct soft-delete inclusion test | Low |
| Cleanup pre-existing ruff F401s in scripts | Low (out of scope) |

---

## Section 8: Lessons Learned

1. **The 1h bug was invisible to the rule engine** — `tx_count_last_1h = len(recent_txns)` reused the 5-min window, so high-velocity detection over an hour was silently wrong. Fixing it required both a source diff and a window-minima test (`mins[0] != mins[1]`) because the response schema doesn't expose the raw counts.

2. **Redis failure must never 500** — following the `enqueue` precedent, the store swallows `(RedisError, TimeoutError, OSError)` (not bare `Exception`) so genuine bugs fail loud while infra failures degrade gracefully to Postgres.

3. **Inclusive window minima are a subtle boundary** — a transaction at exactly now−300s must count in both 5min and 1h windows; the min bound is `now − 300000ms` inclusive, proven by both unit and PG-fallback tests.

4. **Train/serve parity is a two-sided contract** — the trainer was computing velocity and discarding it (training saw zeros). Aligning required generator, CSV schema, `build_synthetic_history`, FeatureEngine propagation, retrain, and ML-ALIGN revalidation in ONE change to keep the pipeline coherent.

5. **Perfect ML metrics on synthetic data are an artifact, not a win** — non-overlapping velocity ranges (fraud 3–15 vs legit 0–2) let XGBoost separate the holdout perfectly (TN=9516, FP=0). Flagged for real-world validation before production trust (S3).

6. **One RTT read pipeline** — trim (ZREMRANGEBYSCORE) + 2 ZCOUNTs in a single `pipe.execute()` keeps the hot path to one round trip while bounding set growth.

---

## Section 9: Archive Confirmation

- [x] Delta spec merged into main capability spec — FD-VEL-001..004 appended with IDs preserved, 7 scenarios intact
- [x] `velocity-store` capability spec already canonical — final as-is (VEL-STORE-001..007)
- [x] Pre-existing requirements in `openspec/specs/fraud-detection/spec.md` untouched (heading hierarchy intact)
- [x] All artifacts persisted (proposal, delta spec, tasks, apply-progress, verify-report, archive-report)
- [x] Tasks artifact: all 21 tasks marked complete (`- [x]`), no stale unchecked items
- [x] Verify report PASS — 0 critical findings, 2 warnings (informational), 4 suggestions
- [x] Deferred items recorded (`amount_sum_24h`, `ip_distinct_count_1h`, Query B removal, ZREM on soft-delete)
- [x] Known risks/limitations recorded (cold start counts=0, soft-delete 24h inclusion, synthetic metrics artifact)
- [x] Status updated to ARCHIVED in this report
- [x] Archive report persisted to engram (`sdd/redis-velocity-features/archive-report`)
- [x] Change formally closed

---

## Section 10: Sign-off

```
Change:     redis-velocity-features
Project:    fraud-detector
Branch:     chore/redis-velocity-features
Final Phases:
  ✅ sdd-propose   — Intent, scope, approach, rollback plan, success criteria
  ✅ sdd-spec      — New capability velocity-store (VEL-STORE-001..007) + 4 ADDED requirements (FD-VEL-001..004)
  ✅ sdd-design    — VelocityStore service, read pipeline, fallback, toggle, retraining alignment
  ✅ sdd-tasks     — 21 tasks across 2 chained PRs (14 PR1 + 7 PR2)
  ✅ sdd-apply     — 7 commits, 26 new tests, CSV + model regenerated
  ✅ sdd-verify    — 294/294 tests, 19/19 scenarios, coverage 89%, mypy clean, PASS
  ✅ sdd-archive   — Delta merged into capability spec, artifacts persisted, status=ARCHIVED

Final state: CLOSED ✓
Delivery: 2 chained PRs (feature-branch-chain) — handled by orchestrator.
```
