---
title: Fraud Detector Codebase
type: codebase
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - python
  - typescript
  - fastapi
  - react
project: fraud-detector
sources:
  - src/
  - frontend/src/
  - docker-compose.yml
aliases:
  - system map
source_repository: .
source_revision: 44829d2
source_paths:
  - src/
  - frontend/src/
  - docker-compose.yml
---

# Fraud Detector Codebase

## Context

Monorepo con backend FastAPI y frontend React, más infraestructura y procesos worker.

## Stack

Python async, FastAPI, SQLAlchemy/asyncpg, PostgreSQL, Redis Streams, Ollama, XGBoost, SHAP, NetworkX, sentence-transformers, React 19, TypeScript y Vite.

## Structure

- `src/api/`: HTTP y dependencias.
- `src/core/`: infraestructura.
- `src/models/`: ORM.
- `src/schemas/`: contratos.
- `src/services/`: dominio.
- `src/workers/`: procesamiento asíncrono.
- `frontend/src/`: UI.
- `tests/`: verificación.

## Entrypoints

- API: `src/api/main.py`.
- Router: `src/api/v1/router.py`.
- Frontend: `frontend/src/main.tsx`.
- Compose: `docker-compose.yml`.

## Important files

- [[codebases/fraud-detector-backend]]
- [[codebases/fraud-detector-frontend]]
- [[concepts/fraud-scoring-pipeline]]
- [[tools/redis-streams]]

## Interfaces

REST versionada bajo `/api/v1`; Redis Streams entre API y workers; PostgreSQL para datos persistentes.

## Decisions

[[decisions/fraud-detector-architecture]].

## Failure modes

[[concepts/scoring-degradation]], [[concepts/at-least-once-processing]] y [[runbooks/troubleshooting]].

## How to verify

[[runbooks/local-development]] y [[runbooks/testing-and-ci]].

## Related projects

[[projects/fraud-detector]].

## Sources

- `src/`
- `frontend/src/`
- `docker-compose.yml`
