---
title: Transaction Scoring Flow
type: synthesis
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - scoring
  - flow
project: fraud-detector
sources:
  - src/api/v1/transactions.py
  - src/services/scoring_service.py
  - src/core/stream_publisher.py
  - src/models/
aliases:
  - flujo de transacción
source_repository: .
source_revision: 44829d2
source_paths:
  - src/api/v1/transactions.py
  - src/services/scoring_service.py
  - src/core/stream_publisher.py
  - src/models/
---

# Transaction Scoring Flow

## Definition

Síntesis del recorrido desde la petición HTTP hasta los outputs persistentes y asíncronos.

## Key facts

```text
request
  → auth/validation
  → Transaction
  → VelocityStore/history/graph
  → ScoringService
  → FraudScore
  → Alert/status/audit
  → Redis events
  → workers
```

## Flow

```mermaid
sequenceDiagram
    participant C as Cliente
    participant API as FastAPI
    participant V as VelocityStore
    participant S as ScoringService
    participant DB as PostgreSQL
    participant R as Redis Streams
    participant W as Workers

    C->>API: POST /api/v1/transactions
    API->>DB: Crear Transaction
    API->>V: Registrar y leer velocity
    API->>S: Calcular scores
    S-->>API: ScoringResult
    API->>DB: FraudScore / Alert / AuditEntry
    API->>R: Publicar LLM/SHAP/Embedding
    API-->>C: ScoreResponse
    R->>W: Consumir eventos
    W->>DB: Persistir explicaciones
```

## Interpretation

La respuesta API contiene la decisión; los workers producen explicaciones y enriquecimientos posteriores.

## Practical application

Para detalle de cada contrato, consultar [[tools/fraud-detector-api-contract]], [[entities/ml-feature-contract]], [[entities/redis-event-contracts]] y [[runbooks/end-to-end-debugging]].

## Uncertainty

La disponibilidad de reportes, SHAP y embeddings es eventual. Un resultado pending no implica fallo de scoring.

## Related

- [[concepts/fraud-scoring-pipeline]]
- [[concepts/fraud-explainability]]
- [[entities/fraud-detector-domain-model]]
- [[projects/fraud-detector]]

## Sources

- `src/api/v1/transactions.py`
- `src/services/scoring_service.py`
- `src/core/stream_publisher.py`
- `src/models/`
