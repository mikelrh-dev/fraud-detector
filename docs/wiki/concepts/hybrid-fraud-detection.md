---
title: Hybrid Fraud Detection
type: concept
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - fraud-detection
  - machine-learning
project: fraud-detector
sources:
  - src/services/scoring_service.py
  - src/services/ensemble.py
  - src/services/llm.py
aliases:
  - sistema híbrido
source_repository: .
source_revision: 44829d2
source_paths:
  - src/services/scoring_service.py
  - src/services/ensemble.py
  - src/services/llm.py
---

# Hybrid Fraud Detection

## Definition

Arquitectura donde reglas deterministas, ML y contexto producen la decisión, mientras un LLM genera explicación.

## Key facts

`ScoringService` calcula scores y `LLMService` genera informes a partir de resultados existentes.

## Interpretation

La separación reduce el riesgo de que una salida no determinista bloquee o apruebe una transacción.

## Practical application

Empieza por [[concepts/fraud-scoring-pipeline]] y sigue [[synthesis/transaction-scoring-flow]].

## Uncertainty

Los pesos, thresholds y features son configuración/código versionado; no asumir valores de documentación histórica.

## Related

- [[projects/fraud-detector]]
- [[concepts/fraud-explainability]]
- [[decisions/fraud-detector-architecture]]

## Sources

- `src/services/scoring_service.py`
- `src/services/ensemble.py`
- `src/services/llm.py`
