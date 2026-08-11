# Tasks: Scoring Breakdown in Transaction Responses

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~350 (additions + deletions: ~+260/−90 across 12 files) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR (base = `feat/scoring-breakdown-in-responses`) |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Entire change: backend helper+schema+endpoints+tests, frontend types+badge+detail+list, MSW fixtures, 2 test files | PR 1 | Base = `feat/scoring-breakdown-in-responses`; ~350 LOC under budget; full backend (245) + frontend (32) suites green |

## Phase 1: Backend Foundation

### Task Dependency Map

```
1.1 (service helper) ──┐
                       ├── 2.1 (detail endpoint) ── 3.1 (update detail/list tests)
1.2 (schema) ──────────┤        └── 3.2 (no-score detail test)
                       ├── 2.2 (list endpoint)  ── 3.1
                       └──        └── 3.3 (N+1 guard test)
                                       └── 8.1 (full verification)

4.1 (frontend types) ── 4.2 (ClassificationBadge) ── 5.2 (list column) ── 7.2 (list test)
   │                        │
   ├── 5.1 (detail adapter) ─── 7.1 (detail test)
   └── 5.3 (TransactionTable)
6.1 (MSW fixtures) ── deps: 4.1 — placed BEFORE 7.1/7.2 (tests assert on deterministic fixtures)
8.1 (verify) ── deps: all
```

### Tasks

- [x] **1.1 — Add `get_scores_for_transactions` batch helper** — Modify `src/services/transaction.py`: import `FraudScore`; add `async def get_scores_for_transactions(db: AsyncSession, transaction_ids: list[UUID]) -> dict[UUID, FraudScore]` — empty ids → `{}` early return (no SQL); one `select(FraudScore).where(FraudScore.transaction_id.in_(ids)).order_by(FraudScore.created_at.desc())`; build dict with `setdefault` so **newest row wins** (no unique constraint on `transaction_id`). +15 LOC. Deps: none. **TDD**: RED — write `tests/unit/test_transaction_service.py` (empty list returns `{}` and never calls `db.execute`; batch of 2 ids → both returned from a single query; 2 rows with same `transaction_id` → newest by `created_at` kept). GREEN — implement. Run: `.\.venv\Scripts\python -m pytest tests/unit/test_transaction_service.py -v`. DoD: one query per call, deterministic newest-wins, empty-input guard tested.

- [x] **1.2 — Add `ScoreBreakdown` schema + `TransactionResponse` fields** — Modify `src/schemas/transaction.py`: `ScoreBreakdown` model with `rule_score: float`, `ml_score: float`, `ensemble_score: float`, `threshold: float`, `classification: str` and `model_config = {"from_attributes": True}` (mirrors `ScoreResponse` minus `transaction_id`/`created_at`/`fired_rules` — `fired_rules` NOT persisted); add `classification: str | None = None` and `scoring: ScoreBreakdown | None = None` to `TransactionResponse`. `TransactionCreate`/`TransactionListResponse` untouched. +20 LOC. Deps: none. **TDD**: RED — add shape assertions to `tests/unit/test_schemas.py` (`ScoreBreakdown.model_validate(fraud_score_mock)` maps all five attrs; `TransactionResponse()` defaults keep `risk_score`/`classification`/`scoring` None). GREEN — implement. DoD: schema imports clean; `from_attributes` validation proven by test.

## Phase 2: Backend Endpoints

- [x] **2.1 — Detail endpoint returns nested `scoring`** — Modify `src/api/v1/transactions.py` (replace L296-313 body): add module helper `_classification_str(value: FraudClassification | str) -> str` (normalize enum — mirrors status pattern L274/309); after the 404 branch, `scores = await get_scores_for_transactions(db, [transaction_id])`; build response with `risk_score=score.ensemble_score if score else None`, `classification=_classification_str(score.classification) if score else None`, `scoring=ScoreBreakdown.model_validate(score) if score else None`. +15 LOC. Deps: 1.1, 1.2. **TDD**: RED — the updated/new integration tests (3.1, 3.2) are written first and fail; GREEN — implement. Acceptance: FRD-DASH-SCORE-001 scenarios 1-3 (breakdown present; absent → nulls + HTTP 200; missing txn → 404 unchanged) + FRD-DASH-SCORE-003 alias (`risk_score == ensemble_score`).

- [x] **2.2 — List endpoint populates `risk_score` + `classification`** — Modify `src/api/v1/transactions.py` (insert after page query L262): `scores = await get_scores_for_transactions(db, [t.id for t in transactions])` — **single batched `IN` query, never per-row**; per-row `risk_score=score.ensemble_score if score else None`, `classification=_classification_str(score.classification) if score else None`. Pagination/count logic and `deleted_at.is_(None)` filter untouched (soft-deleted rows and their scores excluded). +10 LOC. Deps: 1.1, 1.2. **TDD**: RED — updated/list tests (3.1, 3.3) written first and fail; GREEN — implement. Acceptance: FRD-DASH-SCORE-002 scenarios 1-4 (all scored; mixed nulls; exactly one batched query; soft-deleted excluded) + FRD-DASH-SCORE-003.

## Phase 3: Backend Tests

- [x] **3.1 — Update integration tests for score-aware responses** — Modify `tests/integration/test_transaction_api.py`: add `_make_mock_score(**overrides) -> MagicMock` factory (mirrors `_make_mock_transaction`; defaults rule 45.0, ml 60.0, ensemble 52.0, threshold 70.0, `FraudClassification.REVIEW`); update `test_get_existing_transaction_returns_200` — `execute = AsyncMock(side_effect=[txn_result, score_result])`, assert `risk_score == 52.0`, `scoring.rule_score == 45.0`, `scoring.ml_score == 60.0`, `scoring.ensemble_score == 52.0`, `scoring.threshold == 70.0`, `scoring.classification == "review"`, top-level `classification == "review"`; update `test_list_transactions_returns_paginated` — `side_effect = [count_result, list_result, score_result]` (**order: count → page → batched scores**), assert `items[0].risk_score == 52.0`, `items[0].classification == "review"`. `test_get_nonexistent_transaction_returns_404` unchanged (404 fires before score query). +60 LOC. Deps: 2.1, 2.2. **TDD**: written as RED before 2.1/2.2 implementation; confirm GREEN here. Run: `.\.venv\Scripts\python -m pytest tests/integration/test_transaction_api.py -v`.

- [x] **3.2 — Add no-score detail test** — Add `test_get_transaction_without_score_returns_nulls` to `tests/integration/test_transaction_api.py`: `side_effect = [txn_result, empty_score_result]` (`all.return_value = []`); assert HTTP 200, `risk_score is None`, `scoring is None`, `classification is None`. Deps: 2.1. **TDD**: RED first, GREEN after 2.1. Covers FRD-DASH-SCORE-001 scenario 2.

- [x] **3.3 — Add N+1 guard test** — Add `test_list_batches_score_queries_no_n_plus_1` to `tests/integration/test_transaction_api.py`: N=2 transactions with 2 scores, `side_effect = [count_result, list_result, score_result]`; assert `mock_db.execute.call_count == 3` — count + page + **exactly one** batched score query for 2 rows; proves no per-row queries. Deps: 2.2. **TDD**: RED first, GREEN after 2.2. Covers FRD-DASH-SCORE-002 scenario 3.

## Phase 4: Frontend Foundation

- [x] **4.1 — Extend `Transaction` type with scoring fields** — Modify `frontend/src/api/transactions.ts`: add `classification: string | null`; add optional `scoring?: { rule_score: number; ml_score: number; ensemble_score: number; threshold: number; classification: string | null } | null` (backend guarantees non-nullable ml float — no null branch). `ScoreResponse` untouched (still powers POST result card). +12 LOC. Deps: none. **N/A — types only**. DoD: `npx tsc --noEmit` clean.

- [x] **4.2 — Extract shared `ClassificationBadge`** — Create `frontend/src/components/ClassificationBadge.tsx`: extract `ScoreResultCard.tsx:77-93` verbatim (props `{ classification: string }`; uses `classificationColor`/`classificationLabel` from `lib/score.ts`); modify `frontend/src/pages/ScoreResultCard.tsx` to import it and remove the private copy (−15/+2 LOC). Single source of truth — avoids a third divergent color map (design decision 5). Deps: none. **TDD**: render-identical refactor — existing `ScoreResultCard.test.tsx` (4 states) must pass unchanged; run `npm test` in `frontend/`. DoD: no duplicate classification color map in repo.

## Phase 5: Frontend Components

- [x] **5.1 — TransactionDetail: `buildScoreResponse` adapter + `ScoreResultCard` reuse** — Modify `frontend/src/pages/TransactionDetail.tsx`: add `buildScoreResponse(tx: Transaction): ScoreResponse` (rule/ml from `tx.scoring` with `?? 0`; `ensemble_score: tx.scoring?.ensemble_score ?? tx.risk_score ?? 0`; `classification: tx.scoring?.classification ?? statusToClassification(tx.status)`; `fired_rules: []` — **client-side adapter constant only, NEVER part of any GET API response**; `created_at: tx.created_at`); replace whole "Score de Riesgo" section (L228-298) with `{tx.scoring ? <ScoreResultCard result={buildScoreResponse(tx)} /> : <section>…Score no disponible para esta transacción.</section>}`; delete dead inline gauge/bar markup (L233-292). Header status badge (L163-167) unchanged. +30/−70 LOC. Deps: 4.1. **TDD**: RED — `TransactionDetail.test.tsx` (7.1) written before implementing; GREEN — implement. Acceptance: breakdown card renders when `scoring` present; fallback section when null.

- [x] **5.2 — TransactionsPage: live score + Clasificación column** — Modify `frontend/src/pages/TransactionsPage.tsx` (inline table L130-190): add "Clasificación" column between Score and Fecha rendering `<ClassificationBadge classification={tx.classification} />` when non-null, else `—`; score cell (L176-178) goes live automatically (`risk_score` now populated) — keep `toFixed(1)` + "—" fallback. +15 LOC. Deps: 4.1, 4.2. **TDD**: RED — updated assertions in `TransactionsPage.test.tsx` (7.2) written first; GREEN — implement. DoD: column renders badge/em-dash per row.

- [x] **5.3 — TransactionTable: prefer real classification** — Modify `frontend/src/components/TransactionTable.tsx` (used by DashboardPage): `const classification = tx.classification ?? getClassification(tx.status);` so the progress bar + badge reflect the true ensemble classification; dashboard gets live scores for free. +5 LOC. Deps: 4.1. **N/A — small logic change**; existing tests cover the table. DoD: dashboard badge prefers real classification when present.

## Phase 6: MSW Fixtures

- [x] **6.1 — MSW fixtures: deterministic values + new shapes** — Modify `frontend/src/tests/mocks/handlers.ts`: detail handler (L78-92) gains `risk_score: 62.0`, `classification: "review"`, nested `scoring` (rule 50, ml 55, ensemble 62, threshold 60, classification "review"); list handler (L59-76) — **replace `Math.random()` with deterministic values** (`isReview = i % 3 === 0`; `risk_score: isReview ? 62 : 15`; `classification: isReview ? "review" : "legitimate"`; `scoring: null`) so tests can assert exact scores; add `GET /api/v1/transactions/:id/report` → 404 handler (detail page polls it; without it MSW hits real network and spams warnings). +25 LOC. Deps: 4.1 (shape). **N/A — test infra**. DoD: zero `Math.random()` in handlers; report handler present; all frontend tests run against deterministic fixtures.

## Phase 7: Frontend Tests

- [x] **7.1 — Create TransactionDetail test** — Create `frontend/src/tests/TransactionDetail.test.tsx`: render `<TransactionDetail />` inside `QueryClientProvider` + `MemoryRouter` with `initialEntries=["/transactions/test-uuid"]` + `Routes`/`Route` (uses `useParams`). Scenarios: default detail fixture (has `scoring`) → `getByText("Resultado de Scoring")`, rule `50.0`, ensemble `62.0` (gauge + card), "Revisión" badge; `server.use()` override returning `scoring: null, risk_score: null` → `getByText("Score no disponible para esta transacción.")` and card absent. ~70 LOC. Deps: 5.1, 6.1. **TDD**: written as RED before 5.1; confirm GREEN. Run: `npm test` in `frontend/`.

- [x] **7.2 — Update TransactionsPage test** — Modify `frontend/src/tests/TransactionsPage.test.tsx`: existing 4 tests keep passing (fixture fields preserved); add assertions on deterministic fixture — row `Merchant 0` shows `62.0` and "Revisión" badge; row `Merchant 1` shows `15.0`. +10 LOC. Deps: 5.2, 6.1. **TDD**: assertions written as RED before 5.2; confirm GREEN. DoD: 32 frontend tests green.

## Phase 8: Full Verification

- [ ] **8.1 — Full suite + static checks** — Run backend `.\.venv\Scripts\python -m pytest tests/` (245 → all green incl. new tests), `ruff check src/`, `mypy src/` (clean); frontend `npm test` in `frontend/` (32 green), `npx tsc --noEmit`. Confirm FRD-DASH-SCORE-004: POST response unchanged (`TestCreateTransaction`/`test_integration_pipeline.py` untouched, still includes `fired_rules`). Confirm FRD-DASH-SCORE-005: no Alembic migration files added. Confirm no `fired_rules` field added to any GET response schema. Deps: all. DoD: all suites + linters green on the feature branch.

---

## Test Strategy per Task (TDD Mapping)

| Task | TDD? | RED step | GREEN step | Command |
|------|------|----------|------------|---------|
| 1.1 | Yes | `tests/unit/test_transaction_service.py` (batch, newest-wins, empty guard) | Implement helper | `.\.venv\Scripts\python -m pytest tests/unit/test_transaction_service.py -v` |
| 1.2 | Yes | `tests/unit/test_schemas.py` shape assertions | Implement schema | `.\.venv\Scripts\python -m pytest tests/unit/test_schemas.py -v` |
| 2.1 | Yes | RED tests from 3.1/3.2 | Implement detail body | `.\.venv\Scripts\python -m pytest tests/integration/test_transaction_api.py -v` |
| 2.2 | Yes | RED tests from 3.1/3.3 | Implement list body | `.\.venv\Scripts\python -m pytest tests/integration/test_transaction_api.py -v` |
| 3.1 | Yes | Written as RED for 2.1/2.2 | Confirm green | same as above |
| 3.2 | Yes | Written as RED for 2.1 | Confirm green | same as above |
| 3.3 | Yes | Written as RED for 2.2 | Confirm green | same as above |
| 4.1 | N/A | — | — | `npx tsc --noEmit` |
| 4.2 | Yes* | — | Refactor; existing 4-state card tests unchanged | `npm test` (frontend/) |
| 5.1 | Yes | RED tests from 7.1 | Implement adapter + section | `npm test` (frontend/) |
| 5.2 | Yes | RED assertions from 7.2 | Implement column | `npm test` (frontend/) |
| 5.3 | N/A | — | — | existing table tests |
| 6.1 | N/A | — | — | all frontend tests |
| 7.1 | Yes | Written as RED for 5.1 | Confirm green | `npm test` (frontend/) |
| 7.2 | Yes | Written as RED for 5.2 | Confirm green | `npm test` (frontend/) |
| 8.1 | N/A | — | — | full suites + `ruff` + `mypy` |

*\* Task 4.2 is a pure refactor — badge extraction is render-identical; regression proof is the unchanged `ScoreResultCard.test.tsx`.*

## Spec Coverage Map

| Requirement | Covered by |
|-------------|------------|
| FRD-DASH-SCORE-001 (detail nested scoring; nulls + 200 when absent; 404 unchanged) | 2.1, 3.1, 3.2 |
| FRD-DASH-SCORE-002 (list risk_score/classification; batched query; soft-delete) | 2.2, 3.1, 3.3 |
| FRD-DASH-SCORE-003 (risk_score = ensemble_score alias) | 2.1, 2.2 (asserted in 3.1) |
| FRD-DASH-SCORE-004 (POST response unchanged) | 8.1 (no-change guard) |
| FRD-DASH-SCORE-005 (no schema migration) | 8.1 (no-change guard) |

## Branch & Commit Strategy

Work lands on feature branch `feat/scoring-breakdown-in-responses` (created from `master` before 1.1); conventional commits; single PR to master.

| # | Message | Tasks |
|---|---------|-------|
| 1 | `feat(api): add get_scores_for_transactions batch helper` | 1.1 |
| 2 | `feat(api): add ScoreBreakdown schema to transaction responses` | 1.2 |
| 3 | `feat(api): return scoring breakdown from transaction detail` | 2.1, 3.2 |
| 4 | `feat(api): populate risk_score and classification in transaction list` | 2.2, 3.3 |
| 5 | `test(api): update integration tests for score-aware responses` | 3.1 |
| 6 | `feat(ui): extend Transaction type with scoring fields` | 4.1 |
| 7 | `refactor(ui): extract shared ClassificationBadge` | 4.2 |
| 8 | `feat(ui): render scoring breakdown on transaction detail` | 5.1, 7.1 |
| 9 | `feat(ui): show classification column and live scores in list` | 5.2, 5.3, 7.2 |
| 10 | `chore(test): make MSW fixtures deterministic` | 6.1 |
| 11 | `test: verify full scoring-breakdown suite` | 8.1 |

## Out of Scope (Reminder)

1. **`fired_rules` in GET responses** — non-goal; not persisted in `fraud_scores`. NO task adds it to any GET response. (Task 5.1's `fired_rules: []` is a client-side adapter constant feeding `ScoreResultCard`'s required prop, not an API field.)
2. **Re-scoring / backfilling historical transactions** — future change.
3. **ML retraining/calibration** — `ml_score` stays a plain float; no nullable handling added.
4. **Alembic migrations** — `fraud_scores` already exists; schema is `create_all` based (FRD-DASH-SCORE-005).
