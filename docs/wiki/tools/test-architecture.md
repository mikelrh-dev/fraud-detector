---
title: Test Architecture
type: tool
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - testing
  - pytest
  - vitest
project: fraud-detector
sources:
  - tests/
  - frontend/src/tests/
  - tests/conftest.py
aliases:
  - arquitectura de tests
source_repository: .
source_revision: 44829d2
source_paths:
  - tests/
  - frontend/src/tests/
  - tests/conftest.py
---

# Test Architecture

## Context

La verificación combina unit tests, API/integration tests, migraciones, workers y pruebas frontend.

## Key facts

`tests/conftest.py` proporciona mocks DB/Redis, usuarios y cliente ASGI. Los tests de workers verifican ACK, recovery, retries y shutdown. Frontend usa Vitest, Testing Library y MSW.

## Interfaces

Los cambios en scoring deben cubrir reglas, features, ML y clasificación; los cambios de streams deben cubrir payload, ACK, reentrega y DLQ.

## Interpretation

La suite prueba contratos de comportamiento, pero los mocks no sustituyen siempre una ejecución contra PostgreSQL/Redis reales.

## Practical application

[[runbooks/testing-and-ci]].

## Uncertainty

El inventario de tests puede crecer; ejecutar pytest y Vitest para conocer el estado de la revisión vigente.

## Related

- [[entities/ml-feature-contract]]
- [[tools/fraud-detector-api-contract]]
- [[runbooks/worker-recovery]]

## Sources

- `tests/`
- `frontend/src/tests/`
- `tests/conftest.py`
