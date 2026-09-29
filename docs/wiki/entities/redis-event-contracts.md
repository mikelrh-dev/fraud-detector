---
title: Redis Event Contracts
type: entity
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - redis
  - events
project: fraud-detector
sources:
  - src/api/v1/transactions.py
  - src/core/stream_publisher.py
  - src/workers/
aliases:
  - contratos de eventos
source_repository: .
source_revision: 44829d2
source_paths:
  - src/api/v1/transactions.py
  - src/core/stream_publisher.py
  - src/workers/
---

# Redis Event Contracts

## Definition

Payloads que conectan el endpoint de scoring con los workers Redis Streams.

## Key facts

- `fraud:llm`: transaction id, breakdown y datos de transacción.
- `fraud:shap`: transaction id, clasificación, vector, nombres y fingerprint.
- `fraud:embeddings`: transaction id y merchant name.
- `published_at` se añade por el publisher.

## Interpretation

Los payloads llevan snapshots para desacoplar workers de cambios de contexto del request.

## Practical application

[[tools/redis-streams]], [[runbooks/worker-recovery]] y [[concepts/at-least-once-processing]].

## Uncertainty

La idempotencia concreta debe revisarse en cada worker antes de cambiar un campo.

## Related

- [[entities/ml-feature-contract]]
- [[concepts/fraud-explainability]]

## Sources

- `src/api/v1/transactions.py`
- `src/core/stream_publisher.py`
- `src/workers/`
