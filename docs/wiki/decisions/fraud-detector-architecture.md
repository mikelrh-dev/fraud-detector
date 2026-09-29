---
title: Fraud Detector Architecture Decisions
type: decision
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - architecture
  - decisions
project: fraud-detector
sources:
  - src/services/scoring_service.py
  - src/services/ensemble.py
  - src/core/stream_publisher.py
  - src/models/audit_entry.py
  - docker-compose.yml
aliases:
  - decisiones de arquitectura
source_repository: .
source_revision: 44829d2
source_paths:
  - src/services/scoring_service.py
  - src/services/ensemble.py
  - src/core/stream_publisher.py
  - src/models/audit_entry.py
  - docker-compose.yml
---

# Fraud Detector Architecture Decisions

## Definition

Decisiones observables que estructuran el sistema actual.

## Key facts

1. Rules + ML + context producen el score.
2. El LLM solo genera explicación.
3. PostgreSQL es persistencia primaria.
4. Redis Streams desacopla workers.
5. Transacciones usan soft delete.
6. Auditoría es append-only con checksum.
7. Trabajo CPU-bound se ejecuta fuera del event loop.

## Interpretation

El diseño prioriza determinismo, auditabilidad y degradación controlada frente a una decisión única dependiente de un LLM.

## Practical application

[[overview]], [[synthesis/transaction-scoring-flow]] y [[concepts/hybrid-fraud-detection]].

## Uncertainty

El roadmap de concurrencia del grafo es futuro; no se trata como decisión vigente.

## Related

- [[tools/redis-streams]]
- [[concepts/immutable-audit-trail]]
- [[concepts/at-least-once-processing]]

## Sources

- `src/services/scoring_service.py`
- `src/services/ensemble.py`
- `src/core/stream_publisher.py`
- `src/models/audit_entry.py`
- `docker-compose.yml`
