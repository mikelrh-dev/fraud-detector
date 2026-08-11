# Proposal: Scoring Breakdown in Transaction Responses

## Overview

`GET /api/v1/transactions` and `GET /api/v1/transactions/{id}` return `TransactionResponse` with `risk_score` always `null` because neither read endpoint queries the persisted `fraud_scores` table. The scoring pipeline computes and persists a `FraudScore` on POST (`rule_score`, `ml_score`, `ensemble_score`, `threshold`, `classification`) but both reads ignore it. The dashboard detail page shows "Score no disponible para esta transacción." even when a score exists; the list score column and dashboard charts see only nulls. `openspec/specs/fraud-dashboard/spec.md` **already mandates** this behavior — list rows show ensemble score + classification (L13-18), sort by `ensemble_score` (L26-30), detail shows the full scoring breakdown (L41-48). This change completes a specified requirement, not a new one.

## Problem Statement

- `TransactionResponse.risk_score: float | None = None` (`src/schemas/transaction.py:30`) exists but is never populated.
- Detail endpoint (`src/api/v1/transactions.py:289-313`) builds the response from the transaction row only; no `FraudScore` lookup.
- List endpoint (`src/api/v1/transactions.py:225-286`) runs an inline query and ignores scores; the `list_transactions` service function exists but is unused.
- `FraudScore` has no ORM back-reference on `Transaction` (`src/models/fraud_score.py:21-37`); `grep relationship(` returns zero hits — score lookup requires an explicit query (pattern already used in `src/api/v1/monitoring.py:48-53`).
- Frontend renders dead data: detail "Score de Riesgo" section (`frontend/src/pages/TransactionDetail.tsx:229-298`), list score column with "—" fallback (`frontend/src/components/TransactionTable.tsx:175-194`, `frontend/src/pages/TransactionsPage.tsx:176-178`), and dashboard charts (`DashboardPage.tsx:76`, `ScoreTrendChart.tsx`) all consume `risk_score` that is always null.

## Goals

- `GET /transactions/{id}` returns a nested `scoring` breakdown: `rule_score`, `ml_score`, `ensemble_score`, `threshold`, `classification` (from `fraud_scores`).
- `GET /transactions` returns `risk_score = ensemble_score` for each row (one batched `IN` query — **no N+1**), plus a `classification` field on list rows.
- Frontend detail page renders the full breakdown reusing `ScoreResultCard` (fed `fired_rules: []`).
- List score column + existing client-side sort become live (already built, currently dead).
- No breaking changes to existing consumers; POST response untouched.
- All backend tests (245) and frontend tests (32) updated and passing.

## Non-Goals

- `fired_rules` in the detail breakdown — NOT persisted in `fraud_scores` (only in audit trail + queue message); requires an audit-trail read, deferred to a future change.
- Re-scoring or backfilling historical transactions.
- ML retraining/calibration — `ml_score` is always a float (`predict()` returns `0.0` when model missing; column `nullable=False`); the frontend null branch is dead code, do NOT add nullable handling.
- Alembic migrations — `fraud_scores` table already exists; schema is `create_all` based.

## Capabilities (contract with sdd-spec)

**New capabilities**: None — the change fits within the existing `fraud-dashboard` capability.

**Modified capabilities**:
- `fraud-dashboard`: The existing "Transaction List View" and "Transaction Detail View" requirements already mandate ensemble score + classification in list rows and a full scoring breakdown in detail. No new requirement text is strictly needed — this change makes the backend actually deliver the specified data. An optional delta spec may make the API response-shape contract explicit (nested `scoring` object; list `risk_score = ensemble_score`) to keep it testable/verifiable.

## Proposed Approach

- **Detail** (`src/api/v1/transactions.py:289-313`): after `get_transaction(db, id)`, one query `select(FraudScore).where(transaction_id == id)` → build nested `scoring` object. Keep `risk_score` as an alias of `ensemble_score` for compatibility.
- **List** (`src/api/v1/transactions.py:225-286`): single batch query `WHERE transaction_id IN (page ids)`, map by `transaction_id`, populate `risk_score`/`classification` per row. Never query per row.
- **Schema** (`src/schemas/transaction.py`): add nested `scoring` model to `TransactionResponse` mirroring `ScoreResponse` minus `transaction_id`/`created_at`/`fired_rules`; add `classification` string field to list rows.
- **Frontend**:
  - `frontend/src/api/transactions.ts` — extend `Transaction` interface with optional nested `scoring` + `classification`.
  - `frontend/src/pages/TransactionDetail.tsx` — reuse `ScoreResultCard` fed with the nested object mapped to `ScoreResponse` shape + `fired_rules: []`.
  - `frontend/src/pages/TransactionsPage.tsx` + `frontend/src/components/TransactionTable.tsx` — render real `risk_score` and a `classification` badge; sort becomes live.
- **Tests**:
  - `tests/integration/test_transaction_api.py` — `test_get_existing_transaction_returns_200` (L116-133) currently returns the same mock for all `execute` calls → must return a `FraudScore` on the second call; `test_list_transactions_returns_paginated` (L153-183) has exactly 2 `side_effect` entries → must add the batch query result.
  - New `frontend/src/tests/TransactionDetail.test.tsx`; extend MSW fixtures in `frontend/src/tests/mocks/handlers.ts` (detail L78-92, list L59-76) with the new shape.

## Alternative Approaches

- **A — Minimal** (`risk_score = ensemble_score` only, no breakdown object): lowest effort, but fails the fraud-dashboard detail requirement (full breakdown) — rejected.
- **Nested `scoring` object vs flat extra fields**: nested chosen — matches the existing `ScoreResponse` contract, enables `ScoreResultCard` reuse, cleaner API surface.
- **ORM one-to-one relationship + lazy/joined load**: cleanest call sites, but async lazy-loading pitfalls, `selectinload` discipline, larger model change — not required by spec — rejected.

## Impact Assessment

| Area | Impact | Files |
|------|--------|-------|
| Backend API + schema | Modified | `src/api/v1/transactions.py`, `src/schemas/transaction.py` (2 files) |
| Backend tests | Modified | `tests/integration/test_transaction_api.py` (1 file) |
| Frontend | Modified/New | `api/transactions.ts`, `pages/TransactionDetail.tsx`, `pages/TransactionsPage.tsx`, `components/TransactionTable.tsx`, `tests/mocks/handlers.ts` (5 files) |
| Frontend tests | New | `frontend/src/tests/TransactionDetail.test.tsx` (1 file) |

- **Estimate**: ~200-320 changed lines. **Review workload**: below the 400-line budget — single PR.
- **No migration, no infra, no dependencies.**

## Rollback Plan

`git revert` the merge commit. The change is additive (new nested `scoring` field; `risk_score` was always null, so no consumer depends on the old value). Frontend degrades gracefully to the existing "Score no disponible"/"—" states if backend is reverted. No data migration involved.

## Success Criteria

- [ ] Detail GET returns nested `scoring` with rule/ml/ensemble/threshold/classification; `risk_score` equals `ensemble_score`.
- [ ] List GET returns `risk_score` + `classification` per row from a single batched query (no N+1 — verified in code review).
- [ ] `ScoreResultCard` renders the breakdown on the detail page; list shows real scores + classification badge.
- [ ] `pytest tests/ -v` passes (245 tests); `npm test` passes (32 tests); `ruff check src/` + `mypy src/` clean.

## Dependencies

None.
