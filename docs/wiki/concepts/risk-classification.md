---
title: Risk Classification
type: concept
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - scoring
  - risk
project: fraud-detector
sources:
  - src/services/ensemble.py
  - src/api/v1/transactions.py
aliases:
  - clasificación de riesgo
source_repository: .
source_revision: 44829d2
source_paths:
  - src/services/ensemble.py
  - src/api/v1/transactions.py
---

# Risk Classification

## Definition

Conversión del ensemble score en `legitimate`, `review` o `fraud` comparándolo con el threshold del importe.

## Key facts

- `score > threshold` → `fraud`.
- `score >= threshold * 0.75` → `review`.
- resto → `legitimate`.
- El score se limita a 0–100.

## Interpretation

El threshold dinámico hace más estricta la decisión para importes altos.

## Practical application

La clasificación alimenta estado de transacción, alertas y friction level. Ver [[entities/fraud-detector-domain-model]].

## Uncertainty

Los tiers actuales son los de `src/core/config.py`, no los de documentos históricos.

## Related

- [[concepts/fraud-scoring-pipeline]]
- [[concepts/scoring-degradation]]

## Sources

- `src/services/ensemble.py`
- `src/api/v1/transactions.py`
