---
title: Fraud Explainability
type: concept
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - shap
  - llm
  - explainability
project: fraud-detector
sources:
  - src/services/shap_service.py
  - src/services/llm.py
  - src/workers/shap_worker.py
  - src/workers/llm_worker.py
aliases:
  - explicabilidad
source_repository: .
source_revision: 44829d2
source_paths:
  - src/services/shap_service.py
  - src/services/llm.py
  - src/workers/shap_worker.py
  - src/workers/llm_worker.py
---

# Fraud Explainability

## Definition

Conjunto de explicaciones que acompaña a la decisión: reglas disparadas, atribuciones SHAP e informe LLM.

## Key facts

SHAP recibe el vector exacto de scoring y produce atribuciones top-k. Ollama recibe el desglose ya calculado y redacta un informe técnico asíncrono.

## Interpretation

Explicar no equivale a decidir: una atribución o informe no cambia la clasificación persistida.

## Practical application

[[entities/ml-feature-contract]], [[entities/redis-event-contracts]] y [[runbooks/end-to-end-debugging]].

## Uncertainty

Los informes dependen de la disponibilidad del worker y Ollama; el resultado puede ser pending o failed.

## Related

- [[concepts/hybrid-fraud-detection]]
- [[tools/xgboost-serving]]

## Sources

- `src/services/shap_service.py`
- `src/services/llm.py`
- `src/workers/shap_worker.py`
- `src/workers/llm_worker.py`
