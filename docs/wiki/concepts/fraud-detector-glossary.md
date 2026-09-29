---
title: Fraud Detector Glossary
type: concept
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - glossary
project: fraud-detector
sources:
  - src/
aliases:
  - glosario
source_repository: .
source_revision: 44829d2
source_paths:
  - src/
---

# Fraud Detector Glossary

## Definition

Términos usados por el sistema y sus contratos.

## Key facts

- **Alert:** trabajo de revisión asociado a una clasificación fraudulenta.
- **Classification:** `legitimate`, `review` o `fraud`.
- **DLQ:** stream de mensajes fallidos.
- **Ensemble score:** score ponderado final.
- **PEL:** mensajes Redis entregados y no confirmados.
- **SHAP:** atribución de features del modelo.
- **Soft delete:** `deleted_at` sin borrado físico.
- **Threshold:** umbral dinámico por importe.
- **Velocity:** transacciones recientes de un usuario.
- **BOLA/IDOR:** acceso indebido a objetos ajenos.

## Interpretation

Los términos describen contratos diferentes: score decide, SHAP explica, DLQ opera fallos y auditoría conserva trazabilidad.

## Practical application

[[overview]], [[concepts/fraud-scoring-pipeline]] y [[tools/redis-streams]].

## Uncertainty

Los nombres y estados válidos deben verificarse en schemas/models para cada revision.

## Related

- [[index]]
- [[overview]]
- [[entities/fraud-detector-domain-model]]
- [[concepts/at-least-once-processing]]

## Sources

- `src/`
