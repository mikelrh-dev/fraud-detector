---
title: At-Least-Once Processing
type: concept
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - redis
  - reliability
project: fraud-detector
sources:
  - src/core/stream_publisher.py
  - src/core/stream_dlq.py
  - src/workers/
aliases:
  - entrega at-least-once
source_repository: .
source_revision: 44829d2
source_paths:
  - src/core/stream_publisher.py
  - src/core/stream_dlq.py
  - src/workers/
---

# At-Least-Once Processing

## Definition

Semántica de Redis Streams donde un mensaje entregado permanece pendiente hasta que el consumer hace `XACK`.

## Key facts

Los workers usan consumer groups, PEL, recuperación con `XAUTOCLAIM`, reintentos y DLQ.

## Interpretation

Puede haber reentregas; los efectos persistentes deben ser idempotentes o tolerantes a duplicados.

## Practical application

[[tools/redis-streams]] y [[runbooks/worker-recovery]].

## Uncertainty

La semántica exacta de cada worker puede diferir; consultar su implementación antes de operar.

## Related

- [[entities/redis-event-contracts]]
- [[concepts/scoring-degradation]]

## Sources

- `src/core/stream_publisher.py`
- `src/core/stream_dlq.py`
- `src/workers/`
