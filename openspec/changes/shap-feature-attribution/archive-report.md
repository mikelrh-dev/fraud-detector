# Archive Report — shap-feature-attribution

**Status**: ARCHIVED
**Date**: 2026-08-13
**Verify**: PASS (329 backend + 47 frontend, 0 critical findings)

---

## Intent

Expose SHAP feature attribution for suspicious transactions: explain WHY the ML model scored high for each fraud/review transaction, persisting top-5 contributions and showing them in the dashboard detail.

---

## What Shipped

| Component | Detail |
|-----------|--------|
| `src/services/shap_service.py` | Lazy defensive shap import, TreeExplainer, top-5 by \|contribution\|, shape normalization (2D/3D), model fingerprint |
| `src/workers/shap_worker.py` | BRPOP loop on `fraud:shap`, asyncio.to_thread, delete-then-insert idempotent, retry + max retries, audit shap_computed/shap_failed |
| `src/models/shap_attribution.py` | ShapAttribution ORM: uuid PK, transaction_id FK CASCADE, feature, contribution, rank, created_at/updated_at |
| `src/core/redis.py` | Shared `enqueue_for_retry` helper |
| `src/schemas/transaction.py` | ShapContribution schema; ScoreBreakdown.shap_contributions (list\|None) |
| `src/api/v1/transactions.py` | POST enqueues fraud:shap (fraud/review only, feature snapshot); GET detail +1 query ordered by rank |
| `frontend/src/lib/shap.ts` | Spanish label map + direction helpers |
| `frontend/src/components/ShapAttributionCard.tsx` | Direction bars (red=fraud, green=legit), hidden when null |
| `frontend/src/pages/TransactionDetail.tsx` | "Atribución SHAP" section |
| `docker-compose.yml` | shap-worker service |
| `requirements.txt` | shap==0.46.* |

---

## Requirements Implemented

SHP-001..007, FD-SHP-001, FRD-SHP-001, FRD-SHP-002 — all covered by tests.

---

## Test Evidence

- Backend: 329 passed (294 baseline + 35 new)
- Frontend: 47 passed (35 baseline + 12 new)
- ruff + mypy + tsc: clean

---

## Known Risks / Limitations

- `shap` not in local venv (by design); Docker image installs via requirements.txt (~100-150MB with numba)
- Cold start: pre-deploy transactions return null — UI hides section (200 OK)
- Alembic migration for `shap_attributions` not created; project uses create_all pattern
- Synthetic ML metrics (1.0 PR-AUC) are distribution artifact — validate with real data

---

## Deferred Items

- Waterfall chart for SHAP contributions
- Feed SHAP top features into the LLM prompt for richer narratives
- On-demand / backfill endpoint for SHAP computation
- SHAP in list view
- Alembic migration for existing DBs
- ZREM on soft-delete for VelocityStore (from FT-001)
