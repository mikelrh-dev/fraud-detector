---
title: Fraud Detector Domain Model
type: entity
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - domain-model
  - postgresql
project: fraud-detector
sources:
  - src/models/
aliases:
  - modelo de dominio
source_repository: .
source_revision: 44829d2
source_paths:
  - src/models/
---

# Fraud Detector Domain Model

## Definition

Entidades persistentes que representan identidad, transacciones, decisiones, alertas, explicaciones, runs ML y auditoría.

## Key facts

- `User`: identidad, credenciales y rol.
- `Transaction`: importe, merchant, tarjeta parcial, usuario, estado y soft delete.
- `FraudScore`: scores, threshold y clasificación.
- `FraudAlert`: estado de revisión y actor.
- `LLMReport`: informe y estado de generación.
- `ShapAttribution`: contribución rankeada por transacción.
- `MLModelRun`: versión, métricas y drift.
- `RuleMetadata`: catálogo de reglas.
- `AuditEntry`: trail append-only.

La mayoría hereda de `BaseModel` con timestamps; `AuditEntry` usa `Base` y omite `updated_at`.

## Interpretation

La separación entre decisión (`FraudScore`), operación (`FraudAlert`) y explicación (`LLMReport`, `ShapAttribution`) evita mezclar autoridad con enriquecimiento.

## Practical application

[[tools/postgresql-and-alembic]], [[concepts/immutable-audit-trail]] y [[synthesis/transaction-scoring-flow]].

## Uncertainty

Relaciones físicas y restricciones deben comprobarse en migraciones además del ORM.

## Related

- [[projects/fraud-detector]]
- [[entities/ml-feature-contract]]

## Sources

- `src/models/`
