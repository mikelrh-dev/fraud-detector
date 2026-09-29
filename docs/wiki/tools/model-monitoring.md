---
title: Model Monitoring
type: tool
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - monitoring
  - evidently
  - psi
project: fraud-detector
sources:
  - src/services/monitoring.py
  - src/services/drift_service.py
  - src/api/v1/monitoring.py
aliases:
  - monitorización ML
source_repository: .
source_revision: 44829d2
source_paths:
  - src/services/monitoring.py
  - src/services/drift_service.py
  - src/api/v1/monitoring.py
---

# Model Monitoring

## Context

Observabilidad del modelo y de las distribuciones de datos.

## Key facts

El código contiene `MonitoringService` para PSI/métricas/triggers y `DataDriftService` para referencias DataFrame/Evidently. La API expone dashboard, drift, metrics y reference-data.

## Interfaces

[[entities/model-monitoring-contract]] define los outputs y límites de cada camino.

## Interpretation

El drift es señal para investigar/reentrenar, no una decisión transaccional inmediata.

## Practical application

[[runbooks/troubleshooting]], [[runbooks/testing-and-ci]].

## Uncertainty

La referencia puede ser cargada por admin o inicializada a partir de datos recientes; verificar baseline antes de producción.

## Related

- [[tools/xgboost-serving]]
- [[entities/ml-feature-contract]]

## Sources

- `src/services/monitoring.py`
- `src/services/drift_service.py`
- `src/api/v1/monitoring.py`
