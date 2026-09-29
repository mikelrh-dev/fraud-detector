---
title: Fraud Scoring Pipeline
type: concept
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - scoring
  - rules
  - ml
project: fraud-detector
sources:
  - src/services/scoring_service.py
  - src/services/ensemble.py
aliases:
  - pipeline de scoring
source_repository: .
source_revision: 44829d2
source_paths:
  - src/services/scoring_service.py
  - src/services/ensemble.py
---

# Fraud Scoring Pipeline

## Definition

Pipeline que transforma una transacción y su contexto en scores individuales, score ensemble, threshold y clasificación.

## Key facts

`ScoringService` llama a `RuleEngine`, `FeatureEngine`, `MLModelService` y `EnsembleScorer`. El resultado es `ScoringResult`.

## Flow

```mermaid
flowchart LR
    T[Transaction] --> R[RuleEngine]
    T --> F[FeatureEngine]
    H[User history] --> F
    V[VelocityStore] --> C[Context score]
    F --> M[MLModelService]
    R --> E[EnsembleScorer]
    M --> E
    C --> E
    E --> X[Classification]
```

## Interpretation

La composición permite explicar reglas, mantener ML opcional y aislar la lógica de negocio del endpoint.

## Practical application

[[entities/ml-feature-contract]], [[concepts/risk-classification]] y [[runbooks/end-to-end-debugging]].

## Uncertainty

La fórmula y los thresholds deben verificarse en `src/core/config.py` y `src/services/ensemble.py` para cada revisión.

## Related

- [[concepts/hybrid-fraud-detection]]
- [[tools/velocity-store]]
- [[tools/xgboost-serving]]
- [[synthesis/transaction-scoring-flow]]

## Sources

- `src/services/scoring_service.py`
- `src/services/ensemble.py`
