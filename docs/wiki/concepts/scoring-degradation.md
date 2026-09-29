---
title: Scoring Degradation
type: concept
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - reliability
  - scoring
project: fraud-detector
sources:
  - src/services/ml_model.py
  - src/services/scoring_service.py
  - src/services/velocity_store.py
aliases:
  - degradación del scoring
source_repository: .
source_revision: 44829d2
source_paths:
  - src/services/ml_model.py
  - src/services/scoring_service.py
  - src/services/velocity_store.py
---

# Scoring Degradation

## Definition

Comportamiento controlado cuando una dependencia secundaria no está disponible.

## Key facts

- modelo ausente → `ml_score = 0.0`;
- shape ML incompatible → warning y score ML neutro;
- Redis de velocity no disponible → fallback PostgreSQL;
- publicación de eventos falla → se registra y no invalida automáticamente la respuesta.

## Interpretation

Las degradaciones preservan la decisión principal cuando es posible, pero deben observarse y corregirse.

## Practical application

Usa [[runbooks/end-to-end-debugging]] y [[runbooks/troubleshooting]].

## Uncertainty

Los fallos de persistencia primaria no deben interpretarse como best-effort: requieren tratamiento crítico en el endpoint.

## Related

- [[concepts/fraud-scoring-pipeline]]
- [[tools/velocity-store]]
- [[concepts/at-least-once-processing]]

## Sources

- `src/services/ml_model.py`
- `src/services/scoring_service.py`
- `src/services/velocity_store.py`
