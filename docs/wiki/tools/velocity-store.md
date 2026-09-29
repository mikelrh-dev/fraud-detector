---
title: VelocityStore
type: tool
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - redis
  - velocity
project: fraud-detector
sources:
  - src/services/velocity_store.py
aliases:
  - velocity
source_repository: .
source_revision: 44829d2
source_paths:
  - src/services/velocity_store.py
---

# VelocityStore

## Context

Contador deslizante por usuario para ventanas de 5 minutos y 1 hora.

## Key facts

Usa `velocity:{user_id}:tx`, ZSET, timestamp epoch-ms, trim de 24h, TTL de 90.000s y una pipeline por lectura/escritura.

## Interfaces

`record_transaction` escribe best-effort. `get_counts` devuelve `5min` y `1h`, con fallback PostgreSQL o flag de desactivación.

## Interpretation

Velocity alimenta reglas, contexto y features ML; por eso es un contrato de scoring, no solo una optimización.

## Practical application

[[entities/ml-feature-contract]], [[concepts/fraud-scoring-pipeline]] y [[runbooks/end-to-end-debugging]].

## Uncertainty

Redis puede conservar temporalmente soft deletes hasta el trim; PostgreSQL los excluye.

## Related

- [[tools/redis-streams]]
- [[concepts/scoring-degradation]]

## Sources

- `src/services/velocity_store.py`
