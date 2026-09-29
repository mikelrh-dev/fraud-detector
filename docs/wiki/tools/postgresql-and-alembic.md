---
title: PostgreSQL and Alembic
type: tool
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - postgresql
  - alembic
  - sqlalchemy
project: fraud-detector
sources:
  - src/core/database.py
  - src/models/
  - alembic/
aliases:
  - persistencia
source_repository: .
source_revision: 44829d2
source_paths:
  - src/core/database.py
  - src/models/
  - alembic/
---

# PostgreSQL and Alembic

## Context

PostgreSQL es el registro persistente de usuarios, transacciones, decisiones, alertas, informes, atribuciones, runs y auditoría.

## Key facts

SQLAlchemy usa engine y sesiones async. Alembic mantiene migraciones. Las transacciones usan soft delete y deben conservar timestamps.

## Interfaces

[[entities/fraud-detector-domain-model]] describe las entidades. [[runbooks/local-development]] describe la ejecución de migraciones.

## Interpretation

La base de datos contiene la decisión durable; Redis y workers son soporte operativo/enriquecimiento.

## Practical application

Ejecutar `alembic upgrade head` antes de usar una base nueva.

## Uncertainty

Las relaciones efectivas deben revisarse conjuntamente en ORM y migraciones.

## Related

- [[concepts/immutable-audit-trail]]
- [[runbooks/troubleshooting]]

## Sources

- `src/core/database.py`
- `src/models/`
- `alembic/`
