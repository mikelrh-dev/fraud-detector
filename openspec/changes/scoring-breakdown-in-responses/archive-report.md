# Archive Report: Scoring Breakdown in Transaction Responses

---

## Section 1: Header

| Field | Value |
|-------|-------|
| Change name | `scoring-breakdown-in-responses` |
| Project | `fraud-detector` |
| Branch | `feat/scoring-breakdown-in-responses` |
| Archive date | 2026-08-11 |
| Status | **ARCHIVED** ✓ |

---

## Section 2: Lifecycle Summary

The change made the API response-shape contract explicit for scoring data on the transaction read endpoints: the detail endpoint now returns a nested `scoring` breakdown from the persisted `fraud_scores` row, and the list endpoint populates `risk_score = ensemble_score` plus `classification` per row via a single batched query (no N+1). Verified PASS and archived on 2026-08-11.

| Phase | Detail |
|-------|--------|
| **Proposed** | 2026-08-11 — Read endpoints ignored the persisted `fraud_scores` table (`risk_score` always null). Completes an already-specified fraud-dashboard requirement. |
| **Spec** | 5 ADDED requirements across 10 scenarios (FRD-DASH-SCORE-001 ×3, -002 ×4, -003 ×1, -004 ×1, -005 ×1). Additive — no existing requirements modified. |
| **Design** | 411 lines, 12 sections — nested `scoring` schema, `get_scores_for_transactions` batch helper (newest-wins via `setdefault`), list/detail endpoint data flow, frontend `ClassificationBadge` extraction, MSW fixture strategy, N+1 guard test. |
| **Tasks** | 16 tasks across 8 phases — backend foundation, endpoints, tests, frontend foundation/components/fixtures/tests, full verification. 8 tasks TDD-flagged (RED → GREEN → REFACTOR). |
| **Apply** | 5 commits, single PR to `master` (delivery strategy: single-pr, ~350 LOC under budget). |
| **Verify** | **PASS** — all 5 FRD-DASH-SCORE-001..005 requirements VERIFIED against real code + runtime evidence. 253 backend tests (245 baseline + 8 new), 35 frontend tests (32 + 3), ruff clean, mypy clean (49 files), `npx tsc --noEmit` exit 0. 0 critical findings. |
| **Archive** | 2026-08-11 — Delta merged into capability spec (`openspec/specs/fraud-dashboard/spec.md`), status updated to ARCHIVED. |

### Branch History

```
3f02a2a — fix(api): cast Decimal to float in ML user history features (merge base with master)
│
├── 3d0712e — feat(api): add get_scores_for_transactions batch helper
├── 4036492 — feat(api): return scoring breakdown from transaction endpoints
├── 9a48665 — docs(sdd): commit scoring-breakdown-in-responses SDD trail
├── ae51025 — feat(ui): render scoring breakdown on detail and live scores in list
└── e538ac3 — test: verify full scoring-breakdown suite
│
HEAD → feat/scoring-breakdown-in-responses
```

---

## Section 3: Final Statistics

| Metric | Value |
|--------|-------|
| Total commits | **5** |
| Total LOC (net) | **~260** (design estimate: +260/−90 across 13 files) |
| Backend tests | **253** passed (245 baseline + 8 new) |
| Frontend tests | **35** passed (32 + 3) |
| Static checks | ruff clean, mypy clean (49 files), `npx tsc --noEmit` exit 0 |
| Changed-file coverage | `services/transaction.py` 100%, `schemas/transaction.py` 100%, `api/v1/transactions.py` 91% (missing = pre-existing filter/alert branches) |
| Spec scenarios | **10/10** covered (5 requirements) |
| Critical findings | **0** |
| Warning findings | **2** (1 test gap, 1 pre-existing) |
| Suggestion findings | **1** (pre-existing duplication) |

### Files Changed — MODIFIED (12) + NEW (1)

| File | Change |
|------|--------|
| `src/schemas/transaction.py` | Added `ScoreBreakdown` model; `classification` + `scoring` fields on `TransactionResponse` |
| `src/services/transaction.py` | Added `get_scores_for_transactions` batch helper (one `IN` query, newest-wins) |
| `src/api/v1/transactions.py` | `_classification_str` helper; detail returns nested `scoring`; list populates `risk_score`/`classification` |
| `tests/integration/test_transaction_api.py` | `_make_mock_score` factory; updated 2 tests; added no-score detail test + N+1 guard test |
| `frontend/src/api/transactions.ts` | `classification` + optional nested `scoring` on `Transaction` type |
| `frontend/src/components/ClassificationBadge.tsx` | **NEW** — extracted shared badge (single source of truth) |
| `frontend/src/pages/ScoreResultCard.tsx` | Import shared `ClassificationBadge`, removed private copy |
| `frontend/src/pages/TransactionDetail.tsx` | `buildScoreResponse` adapter; reuses `ScoreResultCard`; fallback section when no score |
| `frontend/src/pages/TransactionsPage.tsx` | Added "Clasificación" column with badge; live scores |
| `frontend/src/components/TransactionTable.tsx` | Prefers `tx.classification` over status-derived |
| `frontend/src/tests/mocks/handlers.ts` | Deterministic fixtures (zero `Math.random()`); detail `scoring`; report 404 handler |
| `frontend/src/tests/TransactionDetail.test.tsx` | **NEW** — 2 scenarios (breakdown present / null fallback) |
| `frontend/src/tests/TransactionsPage.test.tsx` | Score + classification badge assertions |

---

## Section 4: Spec Coverage Summary

### ADDED Requirements (5 total, 10 scenarios)

| Requirement | ID | Scenarios | Status |
|-------------|----|-----------|--------|
| Transaction Detail Scoring Response | FRD-DASH-SCORE-001 | 3/3 | ✓ VERIFIED |
| Transaction List Scoring Fields | FRD-DASH-SCORE-002 | 4/4 | ✓ VERIFIED |
| risk_score Ensemble Alias | FRD-DASH-SCORE-003 | 1/1 | ✓ VERIFIED |
| POST Response Unchanged | FRD-DASH-SCORE-004 | 1/1 | ✓ VERIFIED |
| No Schema Migration | FRD-DASH-SCORE-005 | 1/1 | ✓ VERIFIED |

### Delta Spec Integration

The delta spec at `openspec/changes/scoring-breakdown-in-responses/specs/fraud-dashboard/spec.md` contains 5 ADDED requirements. Per the explicit archive instruction for this change, the delta requirements were **merged into the main capability spec** (`openspec/specs/fraud-dashboard/spec.md`): appended as new requirement sections under `## Requirements` with their IDs preserved (FRD-DASH-SCORE-001..005) and all 10 scenarios intact. All pre-existing requirements (Transaction List View, Transaction Detail View, Alert Management, Analyst Actions, Scoring Visualizations, Authentication Integration, Responsive Layout) were left untouched. The archived change folder retains the original delta spec for independent auditability.

### Verification Evidence (from Engram #351)

| Requirement | Evidence |
|-------------|----------|
| FRD-DASH-SCORE-001 | Detail endpoint: 404 fires before score query; nested `scoring` built via `ScoreBreakdown.model_validate`; nulls + HTTP 200 when absent — runtime-tested |
| FRD-DASH-SCORE-002 | List: ONE batched `IN` query outside the loop (L272), per-row only `scores.get` — N+1 proven by code reading AND `call_count == 3` test |
| FRD-DASH-SCORE-003 | `risk_score = score.ensemble_score` on both endpoints, asserted in integration tests |
| FRD-DASH-SCORE-004 | POST untouched — `TestCreateTransaction`/`test_integration_pipeline.py` unchanged, still includes `fired_rules` |
| FRD-DASH-SCORE-005 | No Alembic migration files added; `fraud_scores` table reused |

---

## Section 5: Artifacts Persisted

### Filesystem (OpenSpec)

| Artifact | Location |
|----------|----------|
| Proposal | `openspec/changes/scoring-breakdown-in-responses/proposal.md` |
| Exploration | `openspec/changes/scoring-breakdown-in-responses/exploration.md` |
| Delta spec | `openspec/changes/scoring-breakdown-in-responses/specs/fraud-dashboard/spec.md` |
| Design | `openspec/changes/scoring-breakdown-in-responses/design.md` |
| Tasks | `openspec/changes/scoring-breakdown-in-responses/tasks.md` (16/16 complete) |
| Archive report | `openspec/changes/scoring-breakdown-in-responses/archive-report.md` **(this file)** |
| Main spec (updated) | `openspec/specs/fraud-dashboard/spec.md` — 5 requirements merged, IDs preserved |

Note: `verify-report.md` was persisted to Engram (observation #351), not the filesystem — consistent with this repo's hybrid persistence pattern.

### Engram (Persistent Memory)

| Topic Key | Observation ID | Description |
|-----------|---------------|-------------|
| `sdd/scoring-breakdown-in-responses/apply-progress` | #350 | Implementation progress, 5 commits, TDD evidence |
| `sdd/scoring-breakdown-in-responses/verify-report` | #351 | Verification: PASS — all 5 requirements verified, 253/35 tests, static checks clean |
| `sdd/scoring-breakdown-in-responses/archive-report` | **(this save)** | Archive report |

---

## Section 6: Outstanding Work (Not Blocking)

### Warnings from Verification (2 total)

| ID | Finding | Severity | Notes |
|----|---------|----------|-------|
| W1 | FRD-DASH-SCORE-002 scenario 4 (soft-deleted transaction excluded) has no dedicated test | WARNING | Behavior comes from the pre-existing unchanged `deleted_at.is_(None)` filter; test gap only, not a behavior gap. |
| W2 | Pre-existing count-query ignores `date_from`/`date_to` filters | WARNING | Page query applies them; total may mismatch a filtered page. Out of scope for this change — predates it. |

### Suggestions from Verification (1 total)

| ID | Suggestion | Rationale |
|----|------------|-----------|
| S1 | Remove duplicated `statusToClassification` + CLASSIFICATION maps in `TransactionDetail.tsx` | Pre-existing duplication; could reuse the shared `ClassificationBadge`/`lib/score.ts` helpers. |

### Deferred Items

| Item | Status |
|------|--------|
| `fired_rules` in GET detail response | **Deferred to a future change** — not persisted in `fraud_scores`; would require an audit-trail read. `fired_rules: []` in the frontend adapter is a client-side constant only, never part of any GET API response. |
| Dedicated soft-delete exclusion test | Future test coverage improvement (W1). |
| Count-query date filter alignment | Pre-existing; separate cleanup change (W2). |

---

## Section 7: Next Steps for the User

### 1. Finish the branch

```bash
# Create PR from feat/scoring-breakdown-in-responses → master
# or merge locally:
git checkout master
git merge feat/scoring-breakdown-in-responses
```

### 2. Candidate follow-up changes

| Item | Priority |
|------|----------|
| `fired_rules` in GET detail (audit-trail read) | Next logical backend change |
| Re-scoring / backfilling historical transactions | Future |
| Dedicated soft-delete exclusion test | Low |
| Count-query date filter alignment | Low (pre-existing) |

---

## Section 8: Lessons Learned

1. **N+1 must be proven two ways** — The batched score query was verified by code reading (loop contains only `scores.get`, no `await`) AND by a runtime `call_count == 3` assertion test. Code reading alone can miss hidden awaits; the test is the durable guard.

2. **`setdefault` + `order_by(created_at.desc())` makes "newest wins" deterministic** — `fraud_scores.transaction_id` has no unique constraint, so duplicate rows per transaction are schema-possible. A plain dict comprehension would silently keep the oldest row (last in iteration order). The chosen pattern keeps detail and list in agreement.

3. **MSW fixtures must be deterministic for exact-score assertions** — The list fixture previously used `Math.random()`; tests asserting exact scores require fixed values (`isReview = i % 3 === 0`; 62.0 vs 15.0). Also: the detail page polls `/transactions/:id/report` — without a 404 handler MSW hits the real network and spams warnings.

4. **404 fires before the score query** — The detail endpoint raises 404 before the `fraud_scores` lookup, so the missing-transaction test needs no change and the no-score case stays HTTP 200 (FRD-DASH-SCORE-001 scenario 2 vs 3 are structurally distinct).

5. **Soft-deleted exclusion is inherited, not re-implemented** — Scores are only fetched for ids that survived the page query's `deleted_at.is_(None)` filter, so soft-deleted transactions and their scores are excluded with zero new logic.

6. **Adapter `fired_rules: []` is a client contract, not an API field** — `ScoreResultCard` requires the prop, but `fired_rules` is not persisted in `fraud_scores`; the adapter constant satisfies the component without leaking into any GET response schema (FRD-DASH-SCORE-004 guard).

---

## Section 9: Archive Confirmation

- [x] Delta spec merged into main capability spec — 5 requirements appended with IDs preserved, 10 scenarios intact
- [x] Pre-existing requirements in main spec untouched (no broken sections, heading hierarchy intact)
- [x] All artifacts persisted (proposal, exploration, spec, design, tasks, verify-report [#351], archive-report)
- [x] Tasks artifact: all 16 tasks marked complete (`- [x]`), no stale unchecked items
- [x] Verify report PASS — 0 critical findings, 2 warnings (1 test gap, 1 pre-existing), 1 suggestion
- [x] Deferred items recorded (`fired_rules` in GET detail → future change; soft-delete test; count-query filter mismatch)
- [x] Status updated to ARCHIVED in this report
- [x] Archive report persisted to engram (`sdd/scoring-breakdown-in-responses/archive-report`)
- [x] Change formally closed

---

## Section 10: Sign-off

```
Change:     scoring-breakdown-in-responses
Project:    fraud-detector
Branch:     feat/scoring-breakdown-in-responses
Final Phases:
  ✅ sdd-propose   — Intent, scope, approach, success criteria
  ✅ sdd-spec      — 5 ADDED requirements, 10 scenarios (FRD-DASH-SCORE-001..005)
  ✅ sdd-design    — Schema, batch helper, endpoint data flow, frontend reuse, test strategy
  ✅ sdd-tasks     — 16 tasks across 8 phases
  ✅ sdd-apply     — 5 commits, single PR (~350 LOC)
  ✅ sdd-verify    — 253 backend + 35 frontend tests, ruff/mypy/tsc clean, 10/10 scenarios
  ✅ sdd-archive   — Delta merged into capability spec, artifacts persisted, status=ARCHIVED

Final state: CLOSED ✓
Branch ready for merge to master.
```
