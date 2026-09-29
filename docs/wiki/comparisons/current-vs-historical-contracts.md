---
title: Current vs Historical Contracts
type: comparison
status: needs-review
created: 2026-08-29
updated: 2026-08-29
tags:
  - history
  - contracts
  - uncertainty
project: fraud-detector
sources:
  - src/
  - openspec/
  - docs/audit-2026-08-24.md
  - README.md
aliases:
  - divergencias históricas
source_repository: .
source_revision: 44829d2
source_paths:
  - src/
  - openspec/
  - docs/audit-2026-08-24.md
  - README.md
---

# Current vs Historical Contracts

## Definition

Registro explícito de contradicciones entre el código actual y artefactos históricos.

## Key facts

| Tema | Código actual | Histórico | Fuente de verdad |
|---|---|---|---|
| modelo serving | XGBoost en `MLModelService` | OpenSpec menciona Isolation Forest | código actual |
| thresholds | `src/core/config.py` | README/auditorías pueden contener valores previos | código actual |
| reglas | pesos en `RuleEngine.WEIGHTS` | documentación puede reflejar pesos antiguos | código actual |
| monitorización | `MonitoringService` + `DataDriftService` | descripciones simplificadas | código actual |
| workers | retries/recovery implementados en workers actuales | auditoría previa describe gaps ya corregidos | código actual |

## Interpretation

Las páginas activas describen la revisión `44829d2`. Los documentos históricos conservan contexto, pero no deben usarse como contrato runtime sin comprobar el código.

## Practical application

[[sources/code-revision-44829d2]], [[tools/xgboost-serving]], [[entities/model-monitoring-contract]].

## Uncertainty

El estado de cada divergencia debe revisarse cuando cambie el código o se actualicen las especificaciones.

## Related

- [[decisions/fraud-detector-architecture]]
- [[projects/fraud-detector]]

## Sources

- `src/`
- `openspec/`
- `docs/audit-2026-08-24.md`
- `README.md`
