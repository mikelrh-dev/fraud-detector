# Design: Scoring Breakdown in Transaction Responses

## 1. Context

Both read endpoints return `risk_score: null` because neither queries the persisted `fraud_scores` table — `POST` writes a `FraudScore` row, but `GET /transactions` and `GET /transactions/{id}` never read it (`src/api/v1/transactions.py:225-313`). The `fraud-dashboard` spec already mandates list rows with ensemble score + classification and a full detail breakdown. This change makes the reads deliver the persisted data.

**Locked-in decisions** (do not re-litigate):
- Nested `scoring` object on `TransactionResponse` (mirrors `ScoreResponse` minus `transaction_id`/`created_at`/`fired_rules`) — chosen in proposal
- `risk_score` stays an alias of `ensemble_score` on both read endpoints (FRD-DASH-SCORE-003); `POST` response untouched (FRD-DASH-SCORE-004)
- No ORM relationship between `Transaction` and `FraudScore` (zero `relationship(` in `src/`); explicit `select(FraudScore)` queries only, matching `src/api/v1/monitoring.py:48-53`
- No migration — `fraud_scores` already exists (FRD-DASH-SCORE-005)
- `fired_rules` NOT included in GET responses (not persisted in `fraud_scores`)
- `ml_score` stays a plain float everywhere (column `nullable=False`); no frontend null branch for it in the nested object

## 2. Architecture Overview

```
GET /transactions/{id}                        GET /transactions
        │                                          │
        │ get_transaction(db, id)                  │ inline query (filters/page/count — unchanged)
        │   (1 execute)                            │   (2 executes: count + page)
        ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│          get_scores_for_transactions(db, ids) → dict[UUID, FraudScore]│
│          src/services/transaction.py (NEW helper, one IN query)      │
└─────────────────────────────────────────────────────────────────────┘
        │ dict lookup by id                          │ dict lookup per row
        ▼                                            ▼
TransactionResponse(risk_score=ensemble_score,      per-row risk_score + classification
  classification, scoring=ScoreBreakdown)           (risk_score = ensemble_score)
```

**Key property**: the score lookup is exactly **one** additional query per request — `WHERE transaction_id IN (page ids)`. The detail endpoint reuses the same helper with a single-element id list, so there is no second query shape to maintain.

## 3. Architecture Decisions

### Decision: Score fetch helper location

| Option | Tradeoff | Decision |
|---|---|---|
| Helper `get_scores_for_transactions(db, ids) -> dict[UUID, FraudScore]` in `src/services/transaction.py` | One query shape reused by both endpoints; unit-testable without HTTP layer; consistent with `get_transaction`/`list_transactions` living in services; `transaction.py` is the established DB-access layer | **CHOSEN** |
| Inline `select(FraudScore).where(...)` in each endpoint | Zero new service code, but duplicates the same query in two files; not unit-testable at service level | Rejected — duplication across two endpoints for no benefit |

**Rationale**: The list endpoint keeps its inline filter/pagination loop (no refactor of `list_transactions` — minimal diff), but both endpoints call the one new helper. Hexagonal layering: DB access lives in services, endpoints stay thin.

### Decision: Batch map semantics — latest score wins

`FraudScore.transaction_id` has **no unique constraint** (verified in `src/models/fraud_score.py:26-30`), so duplicate rows per transaction are schema-possible. The batch query orders by `created_at DESC` and builds the dict with `setdefault`, so the **newest row wins deterministically** for both endpoints.

| Option | Tradeoff | Decision |
|---|---|---|
| `order_by(created_at.desc())` + `setdefault` (keep first = newest) | Deterministic; one code path; detail and list agree | **CHOSEN** |
| Plain dict comprehension | One line, but keeps the **oldest** row (last in iteration order) — silently wrong if duplicates exist | Rejected — subtle correctness trap |
| `scalar_one_or_none` per transaction | Raises `MultipleResultsFound` if duplicates exist; N+1 in list | Rejected |

### Decision: `classification` as top-level field on `TransactionResponse`

| Option | Tradeoff | Decision |
|---|---|---|
| Add `classification: str \| None = None` to `TransactionResponse` | List rows expose it per FRD-DASH-SCORE-002; detail sets it too (harmless, consistent with FRD-DASH-SCORE-003 risk_score alias) | **CHOSEN** |
| Only nested `scoring.classification` | List rows would have no classification without reading the nested object; violates the spec's list contract | Rejected |

### Decision: Frontend classification badge — extract `ClassificationBadge`

`ScoreResultCard`'s `ClassificationBadge` (L77-93) is private and there is already a second, divergent color map in `TransactionTable.tsx:18-23`. Extract the badge to `frontend/src/components/ClassificationBadge.tsx` and use it from both `ScoreResultCard` and `TransactionsPage`.

| Option | Tradeoff | Decision |
|---|---|---|
| Extract shared `ClassificationBadge` component | Single source of truth; third color map avoided; follows `components/` convention (Sidebar, Toaster) | **CHOSEN** |
| Inline a new badge in `TransactionsPage` | No new file, but a third copy of the classification color map | Rejected |
| Export `ScoreResultCard`'s private badge | Importing from a `pages/` module is a layering smell | Rejected |

## 4. Data Flow — List endpoint (batched)

```
Client ──GET /api/v1/transactions?page=1&page_size=20──→ list_transactions_endpoint
                                                          │
                                                          ├─ (1) count query → total
                                                          ├─ (2) page query  → transactions[0..N]
                                                          ├─ (3) get_scores_for_transactions(db, ids)
                                                          │        └─ SELECT * FROM fraud_scores
                                                          │             WHERE transaction_id IN (ids)
                                                          │             ORDER BY created_at DESC
                                                          │        └─ dict[UUID → FraudScore] (newest wins)
                                                          └─ per row: risk_score=ensemble_score,
                                                                     classification, (scoring omitted in list)
```

Detail: same helper, `ids=[transaction_id]`, then `scoring = ScoreBreakdown.model_validate(score) if score else None`.

## 5. Backend Design

### 5.1 Schema — `src/schemas/transaction.py`

```python
class ScoreBreakdown(BaseModel):
    """Scoring breakdown nested in transaction responses.

    Mirrors ScoreResponse minus transaction_id/created_at/fired_rules
    (fired_rules is not persisted in fraud_scores).
    """

    rule_score: float
    ml_score: float
    ensemble_score: float
    threshold: float
    classification: str

    model_config = {"from_attributes": True}   # enables model_validate(FraudScore)


class TransactionResponse(BaseModel):
    ...
    risk_score: float | None = None
    classification: str | None = None
    scoring: ScoreBreakdown | None = None
    ...
```

`ScoreBreakdown` is validated from the ORM object via `model_validate(score)` — `FraudScore` exposes all five attributes (`src/models/fraud_score.py:31-37`). No changes to `TransactionCreate` or `TransactionListResponse`.

### 5.2 Service — `src/services/transaction.py` (new helper)

```python
from src.models.fraud_score import FraudScore

async def get_scores_for_transactions(
    db: AsyncSession, transaction_ids: list[UUID]
) -> dict[UUID, FraudScore]:
    """Fetch fraud scores for a batch of transaction ids — one query, no N+1.

    Newest row wins per transaction (no unique constraint on transaction_id).
    """
    if not transaction_ids:
        return {}
    result = await db.execute(
        select(FraudScore)
        .where(FraudScore.transaction_id.in_(transaction_ids))
        .order_by(FraudScore.created_at.desc())
    )
    scores: dict[UUID, FraudScore] = {}
    for score in result.scalars().all():
        scores.setdefault(score.transaction_id, score)  # keep newest
    return scores
```

### 5.3 Endpoints — `src/api/v1/transactions.py`

Small module helper to normalize the `str`-enum column (mirrors the existing status pattern at L274/309):

```python
def _classification_str(value: FraudClassification | str) -> str:
    """Normalize FraudClassification to its string value."""
    return value.value if hasattr(value, "value") else value
```

**Detail** (replaces L296-313 body):

```python
    txn = await get_transaction(db, transaction_id)
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    scores = await get_scores_for_transactions(db, [transaction_id])
    score = scores.get(transaction_id)
    return TransactionResponse(
        id=txn.id,
        amount=float(txn.amount),
        currency=txn.currency,
        merchant_name=txn.merchant_name,
        merchant_category=txn.merchant_category,
        card_last4=txn.card_last4,
        status=txn.status.value if hasattr(txn.status, "value") else txn.status,
        user_id=txn.user_id,
        risk_score=score.ensemble_score if score else None,
        classification=_classification_str(score.classification) if score else None,
        scoring=ScoreBreakdown.model_validate(score) if score else None,
        created_at=txn.created_at,
        updated_at=txn.updated_at,
    )
```

**List** (inserts after L262, before the items loop):

```python
    transactions = list(result.scalars().all())
    scores = await get_scores_for_transactions(db, [t.id for t in transactions])

    items = []
    for t in transactions:
        score = scores.get(t.id)
        items.append(
            TransactionResponse(
                ...existing fields...,
                risk_score=score.ensemble_score if score else None,
                classification=_classification_str(score.classification) if score else None,
            )
        )
```

The 404 branch still fires before the score query, so `test_get_nonexistent_transaction_returns_404` needs no change. `get_transaction` intentionally includes soft-deleted rows (docstring) — detail behavior unchanged; the list query's `deleted_at.is_(None)` filter (L239) already excludes soft-deleted transactions **and** their scores (scores are only fetched for ids that survived the page query).

## 6. Frontend Design

### 6.1 Types — `frontend/src/api/transactions.ts`

```ts
export interface Transaction {
  ...existing fields...;
  risk_score: number | null;
  classification: string | null;
  scoring?: {
    rule_score: number;
    ml_score: number;          // backend guarantees non-nullable float
    ensemble_score: number;
    threshold: number;
    classification: string | null;  // defensive; backend non-null
  } | null;
}
```

`ScoreResponse` stays untouched (still powers the POST result card).

### 6.2 `ClassificationBadge` — `frontend/src/components/ClassificationBadge.tsx` (NEW)

Extract `ScoreResultCard.tsx:77-93` verbatim (props: `{ classification: string }`; uses `classificationColor`/`classificationLabel` from `lib/score.ts`). `ScoreResultCard` imports it from the new location; its existing tests (4 states) keep passing unchanged because rendering is identical.

### 6.3 Detail page — `frontend/src/pages/TransactionDetail.tsx`

Adapter mapping the fetched transaction into `ScoreResponse`-shaped props (the card only consumes rule/ml/ensemble/threshold/classification/fired_rules; `created_at` is required by the type):

```tsx
function buildScoreResponse(tx: Transaction): ScoreResponse {
  return {
    transaction_id: tx.id,
    rule_score: tx.scoring?.rule_score ?? 0,
    ml_score: tx.scoring?.ml_score ?? 0,
    ensemble_score: tx.scoring?.ensemble_score ?? tx.risk_score ?? 0,
    threshold: tx.scoring?.threshold ?? 0,
    classification:
      tx.scoring?.classification ?? statusToClassification(tx.status),
    fired_rules: [],
    created_at: tx.created_at,
  };
}
```

Replace the whole "Score de Riesgo" section (L228-298). `ScoreResultCard` renders its own container (`bg-slate-950 rounded-xl p-6 mt-6`), so the section wrapper is only kept for the fallback:

```tsx
{/* Scoring breakdown */}
{tx.scoring ? (
  <ScoreResultCard result={buildScoreResponse(tx)} />
) : (
  <section className="bg-slate-900 rounded-lg border border-slate-800 p-5">
    <h2 className="text-sm font-semibold text-slate-300 mb-4">Score de Riesgo</h2>
    <p className="text-sm text-slate-500">
      Score no disponible para esta transacción.
    </p>
  </section>
)}
```

The dead inline gauge/bar markup (L233-292) is deleted. The header status badge (L163-167) keeps using `statusToClassification(tx.status)` — unchanged.

### 6.4 List — `frontend/src/pages/TransactionsPage.tsx` + `TransactionTable.tsx`

- **TransactionsPage** (inline table, L130-190): add a "Clasificación" column between Score and Fecha rendering `<ClassificationBadge classification={tx.classification} />` when non-null, else `—`. Score cell (L176-178) becomes live automatically — `risk_score` is now populated; keep the `toFixed(1)` + "—" fallback.
- **TransactionTable** (used by DashboardPage): `getClassification` (L31-33) prefers the real value: `const classification = tx.classification ?? getClassification(tx.status);` — the existing progress bar and badge then reflect true ensemble classification; no other changes (DashboardPage gets live scores for free).

## 7. MSW Fixtures — `frontend/src/tests/mocks/handlers.ts`

**Detail** (L78-92) gains `scoring` + `classification`:

```ts
http.get("*/api/v1/transactions/:id", ({ params }) => {
  return HttpResponse.json({
    id: params.id,
    amount: 1500,
    currency: "USD",
    merchant_name: "Test Merchant",
    merchant_category: "retail",
    card_last4: "1234",
    status: "flagged",
    risk_score: 62.0,
    classification: "review",
    scoring: {
      rule_score: 50,
      ml_score: 55,
      ensemble_score: 62,
      threshold: 60,
      classification: "review",
    },
    user_id: "00000000-0000-0000-0000-000000000001",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
});
```

**List** (L59-76) — replace `Math.random()` with **deterministic** values so tests can assert exact scores, and add per-row `classification`/`scoring: null`:

```ts
const items = Array.from({ length: 10 }, (_, i) => {
  const isReview = i % 3 === 0;
  return {
    id: `tx-${page}-${i}`,
    amount: 100 + i * 500,
    currency: "USD",
    merchant_name: `Merchant ${i}`,
    merchant_category: "retail",
    card_last4: "1234",
    status: isReview ? "flagged" : "approved",
    risk_score: isReview ? 62 : 15,
    classification: isReview ? "review" : "legitimate",
    scoring: null,
    user_id: "00000000-0000-0000-0000-000000000001",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
});
```

**New** report handler (TransactionDetail polls `/transactions/:id/report` in a `useEffect`; without a handler MSW hits the real network and spams warnings):

```ts
http.get("*/api/v1/transactions/:id/report", () =>
  HttpResponse.json({ detail: "Report not found" }, { status: 404 }),
);
```

## 8. Test Strategy

### 8.1 Backend — `tests/integration/test_transaction_api.py`

New mock-score factory mirroring `_make_mock_transaction`:

```python
def _make_mock_score(**overrides) -> MagicMock:
    score = MagicMock(spec=FraudScore)
    score.transaction_id = overrides.get("transaction_id", uuid4())
    score.rule_score = overrides.get("rule_score", 45.0)
    score.ml_score = overrides.get("ml_score", 60.0)
    score.ensemble_score = overrides.get("ensemble_score", 52.0)
    score.threshold = overrides.get("threshold", 70.0)
    score.classification = overrides.get("classification", FraudClassification.REVIEW)
    return score
```

| Test | Mock shape | Assertions |
|---|---|---|
| `test_get_existing_transaction_returns_200` (update) | `mock_db.execute = AsyncMock(side_effect=[txn_result, score_result])` where `score_result.scalars().all.return_value = [score]` (score's `transaction_id == txn.id`) | Existing fields **plus** `risk_score == 52.0`, `scoring.rule_score == 45.0`, `scoring.ml_score == 60.0`, `scoring.ensemble_score == 52.0`, `scoring.threshold == 70.0`, `scoring.classification == "review"`, top-level `classification == "review"` |
| `test_get_nonexistent_transaction_returns_404` | **No change** — 404 raises before the score query; single mock still valid | — |
| `test_list_transactions_returns_paginated` (update) | `side_effect = [count_result, list_result, score_result]` — **order matters**: count → page → batched scores (third position) | Existing pagination assertions plus `items[0].risk_score == 52.0`, `items[0].classification == "review"` |
| **NEW** `test_get_transaction_without_score_returns_nulls` | `side_effect = [txn_result, empty_score_result]` (`all.return_value = []`) | 200, `risk_score is None`, `scoring is None`, `classification is None` |
| **NEW** `test_list_batches_score_queries_no_n_plus_1` | N=2 transactions, 2 scores, `side_effect = [count_result, list_result, score_result]` | `mock_db.execute.call_count == 3` — exactly one batched score query for 2 rows; proves no per-row queries (FRD-DASH-SCORE-002 scenario 3) |

### 8.2 Frontend

**NEW `frontend/src/tests/TransactionDetail.test.tsx`** — render `<TransactionDetail />` inside `QueryClientProvider` + `MemoryRouter` with `initialEntries=["/transactions/test-uuid"]` + a `Routes`/`Route` entry (uses `useParams`). Scenarios:

| Scenario | Setup | Assertions |
|---|---|---|
| Renders breakdown when `scoring` present | Default detail handler (has `scoring`) | `getByText("Resultado de Scoring")`, rule score `50.0`, ensemble `62.0` (gauge + card), "Revisión" badge |
| Renders fallback when `scoring` null | `server.use()` override returning `scoring: null, risk_score: null` | `getByText("Score no disponible para esta transacción.")`; card not present |

**`TransactionsPage.test.tsx`** (update): existing 4 tests keep passing (fixture fields preserved). Add assertions on the now-deterministic fixture: row `Merchant 0` shows score `62.0` and a "Revisión" badge; row `Merchant 1` shows `15.0`.

**No-change tests**: `tests/integration/test_auth_api.py` (no transaction reads), `test_integration_pipeline.py` + `TestCreateTransaction` (POST untouched — FRD-DASH-SCORE-004), `TestDeleteTransaction` (DELETE untouched), `test_get_nonexistent_transaction_returns_404`, frontend `ScoreResultCard.test.tsx` (badge extraction is render-identical), `Sidebar.test.tsx`, `CreateTransactionPage.test.tsx`.

## 9. Edge Cases

| Case | Behavior |
|---|---|
| No `FraudScore` row (detail) | `scoring` null, `risk_score` null, `classification` null, HTTP 200 — FRD-DASH-SCORE-001 scenario 2 |
| No `FraudScore` row (list) | `risk_score`/`classification` null per row — FRD-DASH-SCORE-002 scenario 2; helper returns `{}` for empty ids (early return) |
| `ml_score` | Always float (column `nullable=False`); nested type `ml_score: number`; no null branch added (frontend `isMLTrained`/"ML: no entrenado" stays dead on detail — per contract) |
| Soft-deleted transactions | Excluded from list by existing `deleted_at.is_(None)` filter; their scores never fetched (ids never in page set). Detail by direct id still returns them (pre-existing `get_transaction` behavior) |
| Pagination | Unchanged — count/page/limit logic untouched; score query is purely additive |
| Multiple `FraudScore` rows per transaction | Schema has no unique constraint (verified); helper's `order_by(created_at.desc())` + `setdefault` keeps the newest deterministically on both endpoints |
| Empty page / all filters zero results | `get_scores_for_transactions(db, [])` returns `{}` before any SQL |

## 10. File Changes

| File | Action | Change summary | ~Lines | Tests |
|---|---|---|---|---|
| `src/schemas/transaction.py` | Modify | Add `ScoreBreakdown` model; add `classification` + `scoring` to `TransactionResponse` | +20 | `tests/unit/test_schemas.py` (optional shape assertions) |
| `src/services/transaction.py` | Modify | Add `get_scores_for_transactions` helper + `FraudScore` import | +15 | optional unit test in `tests/unit/test_transaction_service.py` |
| `src/api/v1/transactions.py` | Modify | `_classification_str` helper; detail: score fetch + populate 3 fields; list: batched fetch + per-row population | +25 | `tests/integration/test_transaction_api.py` |
| `tests/integration/test_transaction_api.py` | Modify | `_make_mock_score`; update 2 tests; add no-score detail test + N+1 guard test | +60 | — |
| `frontend/src/api/transactions.ts` | Modify | `classification`, nested `scoring` on `Transaction` | +12 | type-check |
| `frontend/src/components/ClassificationBadge.tsx` | Create | Extracted badge (from `ScoreResultCard`) | ~30 | existing `ScoreResultCard.test.tsx` |
| `frontend/src/pages/ScoreResultCard.tsx` | Modify | Import `ClassificationBadge` from new location; remove private copy | −15/+2 | unchanged |
| `frontend/src/pages/TransactionDetail.tsx` | Modify | `buildScoreResponse` adapter; replace L228-298 section | +30/−70 | NEW `TransactionDetail.test.tsx` |
| `frontend/src/pages/TransactionsPage.tsx` | Modify | Add Clasificación column with badge | +15 | `TransactionsPage.test.tsx` |
| `frontend/src/components/TransactionTable.tsx` | Modify | Prefer `tx.classification` over status-derived | +5 | — |
| `frontend/src/tests/mocks/handlers.ts` | Modify | Detail `scoring`; list deterministic scores + `classification`; report 404 handler | +25 | all frontend tests |
| `frontend/src/tests/TransactionDetail.test.tsx` | Create | 2 scenarios (breakdown present / null fallback) | ~70 | — |
| `frontend/src/tests/TransactionsPage.test.tsx` | Modify | Score + classification badge assertions | +10 | — |

**Total ~ +260/−90** — within the 400-line PR budget; single PR.

## 11. Migration / Rollout

No migration required — `fraud_scores` already exists (FRD-DASH-SCORE-005). The change is additive: new optional `scoring`/`classification` fields; `risk_score` was always null, so no consumer depends on the old value. Rollback = `git revert` the merge commit; the frontend degrades gracefully to the existing "Score no disponible" / "—" states.

## 12. Open Questions

- [ ] None blocking. Minor: `TransactionTable`'s dashboard badge now prefers `tx.classification` — confirm the dashboard's status-based badge visual is acceptable when classification differs from status (rare, but possible).
