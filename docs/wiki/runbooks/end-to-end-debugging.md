---
title: End-to-End Debugging
type: runbook
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - debugging
  - operations
project: fraud-detector
sources:
  - src/api/v1/transactions.py
  - src/services/scoring_service.py
  - src/core/stream_publisher.py
  - src/models/
aliases:
  - debugging transacción
source_repository: .
source_revision: 44829d2
source_paths:
  - src/api/v1/transactions.py
  - src/services/scoring_service.py
  - src/core/stream_publisher.py
  - src/models/
---

# End-to-End Debugging

## Definition

Seguimiento de una transacción desde request hasta persistencia y outputs de workers.

## Key facts

La correlación primaria es `transaction_id`. La secuencia esperada es `Transaction → FraudScore → Alert/audit → stream → worker output`.

## Practical application

1. Revisar respuesta: scores, threshold, clasificación, reglas y friction.
2. Comprobar tablas `transactions`, `fraud_scores`, `fraud_alerts`, `audit_entries`, `shap_attributions` y `llm_reports`.
3. Buscar el id en `fraud:llm`, `fraud:shap` y `fraud:embeddings`.
4. Revisar `XPENDING` y `fraud:dlq`.
5. Si el score sorprende, repetir rules, features, ML, ensemble y threshold.

## Failure modes

Ausencia temporal de SHAP, embedding o reporte puede ser `pending`. Fallos de Redis, Ollama o modelo deben distinguirse de fallos de PostgreSQL.

## Uncertainty

No imprimir tokens, contraseñas ni números completos de tarjeta en logs.

## Related

- [[concepts/fraud-scoring-pipeline]]
- [[runbooks/worker-recovery]]
- [[entities/fraud-detector-domain-model]]

## Sources

- `src/api/v1/transactions.py`
- `src/services/scoring_service.py`
- `src/core/stream_publisher.py`
- `src/models/`
