---
title: Redis Streams
type: tool
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - redis
  - workers
project: fraud-detector
sources:
  - src/core/stream_publisher.py
  - src/core/stream_manager.py
  - src/core/stream_dlq.py
  - src/workers/
aliases:
  - Redis Streams
source_repository: .
source_revision: 44829d2
source_paths:
  - src/core/stream_publisher.py
  - src/core/stream_manager.py
  - src/core/stream_dlq.py
  - src/workers/
---

# Redis Streams

## Context

Infraestructura de eventos con consumer groups para desacoplar scoring de enriquecimientos.

## Key facts

Streams: `fraud:llm`, `fraud:shap`, `fraud:embeddings`, `fraud:dlq`. El publisher usa `XADD`, trim aproximado hasta 100.000 eventos y timestamp de publicación.

## Flow

```mermaid
flowchart LR
    API[API] --> LLM[fraud:llm]
    API --> SHAP[fraud:shap]
    API --> EMB[fraud:embeddings]
    LLM --> LW[llm-workers]
    SHAP --> SW[shap-workers]
    EMB --> EW[embedding-workers]
    LW --> DB1[(LLMReport)]
    SW --> DB2[(ShapAttribution)]
    EW --> R[(Embedding result)]
    LW -. failure .-> DLQ[fraud:dlq]
    SW -. failure .-> DLQ
```

## Interfaces

Los workers usan `XGROUP CREATE` con `MKSTREAM`, `XREADGROUP`, `XACK` y `XAUTOCLAIM`.

## Interpretation

La semántica es at-least-once; los mensajes pueden reentregarse.

## Practical application

[[entities/redis-event-contracts]], [[runbooks/worker-recovery]] y [[concepts/at-least-once-processing]].

## Uncertainty

La política de retry puede variar por worker; revisar cada implementación.

## Related

- [[tools/velocity-store]]
- [[concepts/scoring-degradation]]
- [[concepts/at-least-once-processing]]

## Sources

- `src/core/stream_publisher.py`
- `src/core/stream_manager.py`
- `src/core/stream_dlq.py`
- `src/workers/`
