---
title: Fraud Detector Wiki
type: synthesis
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - fraud-detection
  - software-engineering
project: fraud-detector
sources:
  - src/
  - frontend/src/
aliases:
  - wiki
source_repository: .
source_revision: 44829d2
source_paths:
  - src/
  - frontend/src/
  - tests/
---

# Fraud Detector Wiki

## Definition

Wiki técnica Frontier del proyecto Fraud Detector. El código de la revisión `44829d2` es la fuente primaria de verdad.

## Key facts

- [[projects/fraud-detector]] describe el producto y su estado.
- [[codebases/fraud-detector]] describe el sistema completo.
- [[codebases/fraud-detector-backend]] y [[codebases/fraud-detector-frontend]] describen sus aplicaciones.
- [[synthesis/transaction-scoring-flow]] explica el recorrido de una transacción.
- [[comparisons/current-vs-historical-contracts]] registra divergencias sin resolverlas silenciosamente.

## Practical application

### Empezar por el modelo mental

1. [[concepts/hybrid-fraud-detection]]
2. [[synthesis/transaction-scoring-flow]]
3. [[concepts/fraud-scoring-pipeline]]

### Operar el sistema

- [[runbooks/local-development]]
- [[runbooks/worker-recovery]]
- [[runbooks/end-to-end-debugging]]
- [[runbooks/troubleshooting]]

### Cambiar el sistema

- [[tools/fraud-detector-api-contract]]
- [[entities/ml-feature-contract]]
- [[entities/redis-event-contracts]]
- [[runbooks/testing-and-ci]]

## Uncertainty

Esta wiki reemplaza una estructura temática anterior. Las páginas históricas no deben considerarse vigentes si contradicen `src/` o `frontend/src/`.

## Related

- [[overview]]
- [[concept-table]]
- [[sources/code-revision-44829d2]]
- [[concepts/fraud-detector-glossary]]
- [[tools/frontend-design-system]]
- [[sources/repository-documentation]]
- [[decisions/fraud-detector-architecture]]

## Sources

- Primary source: `src/`, revision `44829d2`.
- Frontend source: `frontend/src/`, revision `44829d2`.
- Tests: `tests/`, revision `44829d2`.
