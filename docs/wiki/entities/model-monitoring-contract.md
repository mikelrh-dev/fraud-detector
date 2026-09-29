---
title: Model Monitoring Contract
type: entity
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - ml
  - monitoring
project: fraud-detector
sources:
  - src/services/monitoring.py
  - src/services/drift_service.py
  - src/api/v1/monitoring.py
aliases:
  - monitoring contract
source_repository: .
source_revision: 44829d2
source_paths:
  - src/services/monitoring.py
  - src/services/drift_service.py
  - src/api/v1/monitoring.py
---

# Model Monitoring Contract

## Definition

Conjunto de métricas, referencias y endpoints para observar drift y runs de modelo.

## Key facts

`MonitoringService` calcula PSI, precision, recall, F1 y AUC-ROC; `DataDriftService` compara DataFrames contra referencia y puede persistirla en Redis.

## Interpretation

No existe un único número universal: `drift_score` y `drift_share` pertenecen a caminos distintos.

## Practical application

[[tools/model-monitoring]], [[tools/fraud-detector-api-contract]] y [[runbooks/troubleshooting]].

## Uncertainty

Una referencia inicial puede derivarse de datos recientes si no se ha cargado explícitamente; esto debe revisarse antes de usarla como baseline de producción.

## Related

- [[entities/ml-feature-contract]]
- [[concepts/fraud-scoring-pipeline]]

## Sources

- `src/services/monitoring.py`
- `src/services/drift_service.py`
- `src/api/v1/monitoring.py`
