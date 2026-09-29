---
title: Fraud Detector Backend
type: codebase
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - python
  - fastapi
  - async
project: fraud-detector
sources:
  - src/api/
  - src/core/
  - src/services/
  - src/models/
  - src/schemas/
  - src/workers/
aliases:
  - backend
source_repository: .
source_revision: 44829d2
source_paths:
  - src/api/
  - src/core/
  - src/services/
  - src/models/
  - src/schemas/
  - src/workers/
---

# Fraud Detector Backend

## Context

Backend async que recibe transacciones y coordina cálculo, persistencia, auditoría y eventos.

## Stack

FastAPI, SQLAlchemy async, asyncpg, Pydantic, Redis async, XGBoost, SHAP, NetworkX y Ollama.

## Structure

[[tools/fraud-detector-api-contract]], [[concepts/fraud-scoring-pipeline]], [[entities/fraud-detector-domain-model]] y [[tools/redis-streams]].

## Entrypoints

`src/api/main.py`, `src/api/v1/router.py` y los módulos bajo `src/workers/`.

## Important files

- `src/api/v1/transactions.py`
- `src/services/scoring_service.py`
- `src/services/feature_engine.py`
- `src/core/dependencies.py`
- `src/core/security.py`

## Interfaces

REST, schemas Pydantic, PostgreSQL y streams `fraud:llm`, `fraud:shap`, `fraud:embeddings`.

## Decisions

La API orquesta I/O; el cálculo vive en services y el CPU-bound se delega a threads.

## Failure modes

[[concepts/scoring-degradation]], [[concepts/at-least-once-processing]], [[runbooks/worker-recovery]].

## How to verify

[[runbooks/testing-and-ci]], `ruff check src/`, `mypy src/` y `pytest tests/`.

## Related projects

[[projects/fraud-detector]].

## Sources

- `src/api/`
- `src/core/`
- `src/services/`
- `src/models/`
- `src/schemas/`
- `src/workers/`
