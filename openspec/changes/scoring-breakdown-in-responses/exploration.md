# Exploration: Scoring breakdown in transaction detail & list responses

## Current State

The scoring pipeline (`POST /api/v1/transactions`, `src/api/v1/transactions.py:56-222`) computes
rule/ML/ensemble scores, persists a `FraudScore` row (`src/models/fraud_score.py:21-38`), and returns
a full `ScoreResponse` breakdown (`src/schemas/scoring.py:9-21`). The `fraud_scores` table is created
via `Base.metadata.create_all` (`scripts/init_db.py:26`); the Alembic initial migration is a no-op
(`alembic/versions/b02e4753e78e_initial.py`).

Neither read endpoint queries `fraud_scores`:

- `GET /api/v1/transactions/{id}` (`src/api/v1/transactions.py:289-313`) — builds
  `TransactionResponse` from the transaction row only; `risk_score` stays `None`.
- `GET /api/v1/transactions` (`src/api/v1/transactions.py:225-286`) — same; list rows have
  `risk_score = None`. The `list_transactions` service function exists
  (`src/services/transaction.py:45-57`) but the endpoint does NOT use it (inline query at
  `src/api/v1/transactions.py:239-262`).

`TransactionResponse` already declares `risk_score: float | None = None`
(`src/schemas/transaction.py:30`) — field exists, never populated.

**ORM relationships: none.** `FraudScore` has only an FK to `transactions.id`
(`src/models/fraud_score.py:26-30`); `Transaction` has no back-reference. `grep relationship(` in
`src/` returns zero hits. Any score lookup requires an explicit query (pattern already used in
`src/api/v1/monitoring.py:48-53`).

The frontend renders scores in three places:

1. **Detail** (`frontend/src/pages/TransactionDetail.tsx:229-298`) — "Score de Riesgo" section reads
   only `tx.risk_score`; shows "Score no disponible para esta transacción." when null (L294-296).
2. **List** (`frontend/src/pages/TransactionsPage.tsx:176-178` and
   `frontend/src/components/TransactionTable.tsx:175-194`) — Score column shows `risk_score.toFixed(1)`
   or "—"; `TransactionTable` also renders a mini progress bar.
3. **Post-create** (`frontend/src/pages/ScoreResultCard.tsx:131-166`) — full 5-state breakdown
   (gauge + Reglas/ML/Ensemble cards + fired rules), fed by `ScoreResponse`. Already tested in
   `frontend/src/tests/ScoreResultCard.test.tsx`.

Note: `openspec/specs/fraud-dashboard/spec.md` ALREADY mandates this behavior — list rows show
ensemble score + classification (L13-18) and detail shows the full scoring breakdown (L41-48). This
change completes a specified requirement.

## Affected Areas

- `src/api/v1/transactions.py` — both GET endpoints: add `fraud_scores` query and populate response.
- `src/schemas/transaction.py` — `TransactionResponse`: add scoring breakdown (or alias
  `risk_score = ensemble_score`).
- `frontend/src/api/transactions.ts` — `Transaction` interface + optional nested scoring type.
- `frontend/src/pages/TransactionDetail.tsx` — replace/augment the risk score section.
- `frontend/src/pages/TransactionsPage.tsx`, `frontend/src/components/TransactionTable.tsx` — list
  score column (risk_score = ensemble at minimum).
- `frontend/src/pages/ScoreResultCard.tsx` — candidate for reuse in detail (needs `fired_rules`).
- `tests/integration/test_transaction_api.py` — `test_get_existing_transaction_returns_200` (L116-133)
  and `test_list_transactions_returns_paginated` (L153-183) mock a fixed number of `db.execute`
  calls; both break if a new query is added.
- `frontend/src/tests/mocks/handlers.ts` — GET detail (L78-92) and GET list (L59-76) fixtures need
  the new shape.

## Approaches

1. **Nested `scoring` object in `TransactionResponse`** (detail + list, matching `ScoreResponse`)
   - Pros: full breakdown everywhere per spec; matches existing `ScoreResponse` contract; list can
     carry `risk_score = ensemble_score` for backward compat; no schema rename risk.
   - Cons: list payload grows; must batch the score lookup to avoid N+1; `fired_rules` is NOT
     persisted in `fraud_scores` (only in audit + queue message), so nested object cannot include it.
   - Effort: Medium

2. **Flat fields + `risk_score = ensemble_score` only**
   - Pros: minimal change.
   - Cons: does not satisfy detail breakdown requirement; spec explicitly wants rule/ML/ensemble in
     detail.
   - Effort: Low

3. **ORM relationship** (`Transaction.fraud_score` one-to-one) + lazy/joined load
   - Pros: cleanest code at call sites.
   - Cons: async lazy loading pitfalls; needs `selectinload` discipline; larger model change; spec
     does not require it.
   - Effort: Medium-High

## Recommendation

Option 1 (nested breakdown, batched in list, `risk_score = ensemble_score` in list). Detail gets the
full breakdown reusing the visual language of `ScoreResultCard`; list gets a real score immediately.
Backfill `risk_score` from `ensemble_score` keeps existing UI/tests/Dashboard (`DashboardPage.tsx:76`,
`ScoreTrendChart.tsx`) working. Reuse `ScoreResultCard` by feeding it the nested object mapped to
`ScoreResponse` shape with `fired_rules: []` (or refactor its props to a narrower type).

## Risks

- **N+1 in list**: fetch scores with one `IN` query keyed by transaction ids and map in Python; do
  NOT query per row.
- **Backend tests break**: both GET tests mock `db.execute` with a fixed side_effect; they need
  additional mock results (or the test DB fixture must return a FraudScore).
- **MSW fixtures**: detail fixture (handlers.ts:78-92) and list fixture (handlers.ts:59-76) must gain
  the new shape; `risk_score` is already present in both, so list tests are low-risk.
- **`fired_rules` not persisted**: `fraud_scores` stores only rule/ml/ensemble/threshold/classification
  (`src/models/fraud_score.py:31-37`). Detail cannot show fired rules unless read from audit trail.
- **Contract mismatch (pre-existing)**: backend `ml_score` is always a float (`predict()` returns
  `0.0` when model missing, `ml_model.py:70-71`; column `nullable=False`), but the frontend treats
  `ml_score: number | null` with an "ML: no entrenado" state (`score.ts:42-44`, handlers fixture
  `ml_not_trained`). A detail breakdown should keep `ml_score` non-nullable to match the DB.
- **No TransactionDetail test exists** (`frontend/src/tests/` has only TransactionsPage, Sidebar,
  ScoreResultCard, CreateTransactionPage) — new detail tests are net-new, nothing breaks there.

## Ready for Proposal

Yes. Tell the user: the diagnosis is confirmed (risk_score always null on GET; FraudScore persisted
on POST only); the fraud-dashboard spec already requires this behavior; recommend Option 1 (nested
scoring breakdown + ensemble as list risk_score) with a batched lookup to avoid N+1, and note that
fired_rules cannot be included from fraud_scores alone.
