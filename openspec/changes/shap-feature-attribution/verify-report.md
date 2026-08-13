# Verify Report — shap-feature-attribution

**Status**: PASS
**Date**: 2026-08-13
**Branch**: feat/shap-attribution
**Tester**: orchestrator (inline, no subagent)

---

## Evidence

| Check | Result |
|-------|--------|
| `pytest tests/ -q` | **329 passed**, 22 warnings |
| `npm test` (frontend/) | **47 passed**, 9 test files |
| `ruff check src/` | All checks passed |
| `mypy src/` | No issues found in 53 source files |
| `tsc --noEmit` (frontend/) | Clean |

---

## Requirement Coverage

| ID | Requirement | Test(s) | Status |
|----|------------|---------|--------|
| SHP-001 | SHAP computed in worker via asyncio.to_thread | `tests/test_shap_worker.py::test_process_shap_message_success` | ✅ |
| SHP-002 | shap_values shape normalization (2D/3D, class-fraud index) | `tests/unit/test_shap_service.py::test_explain_2d / test_explain_3d` | ✅ |
| SHP-003 | Top-5 by \|contribution\| persisted with rank 1..5 | `tests/test_shap_worker.py::test_persists_top5_rows` | ✅ |
| SHP-004 | Retry + max retries + audit shap_computed/shap_failed | `tests/test_shap_worker.py::test_retry_increments / test_max_retries_drops` | ✅ |
| SHP-005 | Defensive import — worker survives without shap installed | `tests/unit/test_shap_service.py::test_shap_unavailable_graceful` | ✅ |
| SHP-006 | shap==0.46.* declared in requirements.txt | `requirements.txt` (build gate) | ✅ |
| SHP-007 | SHAP never touches decision pipeline | Grep: no shap path touches classification/score/alerts; aditivo puro | ✅ |
| FD-SHP-001 | POST enqueues fraud:shap only for fraud/review with snapshot | `tests/integration/test_transaction_api.py::test_shap_enqueued_fraud_review / test_legitimate_no_enqueue` | ✅ |
| FRD-SHP-001 | GET detail returns shap_contributions ordered by rank; list untouched | `tests/integration/test_transaction_api.py::test_detail_shap_contributions / test_list_no_shap` | ✅ |
| FRD-SHP-002 | Frontend renders "Atribución SHAP" section; hidden when null | `frontend/src/tests/TransactionDetail.test.tsx` + `ShapAttributionCard.test.tsx` | ✅ |

---

## Findings

**CRITICAL**: 0
**WARNING**: 0
**SUGGESTION**:
- S1: `shap` not installed in local venv (by design — Docker installs it via requirements.txt). Worker degrades gracefully with warning. Validate in real Docker environment before production use.
- S2: Alembic migration for `shap_attributions` table not created — project uses `create_all` (confirmed pattern). Document for any existing DB that needs manual migration.
- S3: SHAP metrics with synthetic data are perfect (1.0 PR-AUC pre-existing artifact) — validate with real transaction data.

---

## Invariant Check (XAI-001)

SHAP code path: POST → enqueue `fraud:shap` (best-effort, no await on response) → worker computes SHAP → persists `ShapAttribution` rows → GET detail reads rows → frontend displays.
The decision path (classification, score, alerts) is computed BEFORE the enqueue and is never modified by the SHAP worker. Confirmed by code read of `src/api/v1/transactions.py` (enqueue is post-scoring step 11) and `src/workers/shap_worker.py` (only reads features + writes ShapAttribution; no writes to fraud_scores/alerts/transactions).
