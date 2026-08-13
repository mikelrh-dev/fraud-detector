# Proposal: SHAP Feature Attribution for Suspicious Transactions

## Intent

Analysts see a risk score but cannot explain WHY a transaction was flagged. Compute SHAP attribution in the async slow path for suspicious transactions, persist top contributions, and surface them in the detail view. Explanation only — never touches the decision (XAI-001).

## Business Problem / Current-State Gap

- ML score is a black box: `ScoreBreakdown` exposes `ml_score` with no feature-level explanation.
- Detail view (`TransactionDetail`) shows score breakdown + LLM report, but nothing explains which features pushed the score up/down.
- Feature vector is NOT reproducible in a worker: VelocityStore windows + Query B stats shift as new transactions arrive — a late recalculation would explain a DIFFERENT vector than the one scored. The queue message must snapshot the vector in the POST.

## Target Users / Scenarios

- Fraud analysts reviewing fraud/review transactions in the dashboard detail.
- Scenario: analyst opens a flagged transaction → "Atribución SHAP" section shows top-5 features with direction (red = pushes fraud, green = legit).

## Scope

### In Scope
- Snapshot feature vector in POST; new `fraud:shap` queue, filtered to `classification in {fraud, review}`.
- `src/workers/shap_worker.py`: `shap.TreeExplainer` on `models/xgboost_paysim_v1.joblib` via `asyncio.to_thread` (CPU-bound); retry pattern; persist top-5 by |contribution|.
- `ShapAttribution` child table (uuid PK, transaction_id FK CASCADE, feature, contribution, rank, created_at/updated_at).
- API: `ShapContribution = {feature, contribution}`; `ScoreBreakdown.shap_contributions: list | None = None`; GET /transactions/{id} adds ONE query (order by rank); list endpoint untouched; backward compatible (absent → null). GET /report unchanged.
- Audit `shap_computed`/`shap_failed`.
- Frontend: "Atribución SHAP" section (top-k bars + direction, Spanish feature map); MSW fixtures + tests; hidden when null.

### Out of Scope
- Waterfall chart; SHAP fed into the LLM prompt (good follow-up); backfill/on-demand endpoint; SHAP in list view.

## Capabilities

### New Capabilities
- `shap-attribution`: async SHAP computation, persistence, API exposure, frontend rendering.

### Modified Capabilities
- `fraud-detection`: POST /transactions enqueues `fraud:shap` with a snapshot feature vector when classification ∈ {fraud, review}.
- `fraud-dashboard`: transaction detail renders the SHAP attribution section (top-k, direction) when present, hidden when null.

## Approach

- POST: after scoring, enqueue `{transaction_id, features: vector.tolist()}` to `fraud:shap` (mirrors LLM enqueue; best-effort).
- Worker: BRPOP loop; TreeExplainer init cold (100-500ms) inside `to_thread`; handle 2D/3D `shap_values` (keep class-fraud index 1); persist + audit + retry_count (LLM pattern).
- API: extend `ScoreBreakdown`; detail performs one `select ... order_by rank`; no changes to list/`risk_score`.
- Frontend: extend `Transaction.scoring` type; render bars with direction; Spanish labels via feature map.

## Open Decisions

- Snapshot vs recalc → **snapshot** (explains the scored vector; recalc is misleading).
- Child table vs JSONB → **child table** (mirrors LLMReport; queryable, auditable).
- Migration: `create_all` (project default) vs Alembic → confirm with maintainers.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/api/v1/transactions.py` | Modified | Enqueue `fraud:shap`; detail query + `shap_contributions` |
| `src/schemas/transaction.py` | Modified | `ShapContribution`, `ScoreBreakdown.shap_contributions` |
| `src/workers/shap_worker.py` | New | SHAP computation worker |
| `src/models/shap_attribution.py` | New | `ShapAttribution` ORM model |
| `src/services/shap_service.py` | New | Explainer, top-5, persistence |
| `src/audit/` / enums | Modified | `shap_computed`/`shap_failed` |
| `requirements.txt`, `docker-compose.yml` | Modified | `shap==0.46.*` (+numba) |
| `frontend/src/**` | Modified | Detail section, types, MSW fixtures |
| `tests/**` | Modified/New | Worker, service, API, frontend tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| shap/numba image weight (~100-150MB) | High | Pin `shap==0.46.*`; numba is transitive; acceptable for Docker |
| Explainer init + inference blocks worker loop | High | `asyncio.to_thread`; separate worker from LLM loop |
| `shap_values` shape 2D/3D across versions | Med | Normalize; keep class-fraud index 1; unit-test both shapes |
| Cold-start nulls in UI | Med | 200 with null; section hidden |
| Queue growth | Med | Filtered to fraud/review only |
| Model drift | Low | Log model fingerprint in audit v1 |

## Rollback Plan

`git revert` the merge commit(s). Change is additive (new optional field, new table, new queue). If DB migration used, roll it back; with `create_all`, drop `shap_attributions`. Stop worker, let `fraud:shap` drain; API returns null and UI hides the section — no consumer breakage.

## Dependencies

- `shap==0.46.*` in `requirements.txt` (numba transitive; xgboost 2.1.4 + numpy 1.26 compatible).

## Success Criteria

- [ ] POST enqueues `fraud:shap` ONLY for fraud/review, with snapshot vector.
- [ ] Worker persists top-5 `ShapAttribution` rows (ranked, signed) for a fraud transaction; audit entries written.
- [ ] GET /transactions/{id} returns `scoring.shap_contributions` (ordered); null when absent; list + report endpoints unchanged.
- [ ] Detail view renders "Atribución SHAP" with direction; hidden when null.
- [ ] `pytest tests/ -v --cov=src` (strict TDD), `ruff check src/`, `mypy src/`, `npm test` pass.
