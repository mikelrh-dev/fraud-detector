---
title: Fraud Detector Overview
type: project
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - fraud-detection
  - architecture
project: fraud-detector
sources:
  - src/api/main.py
  - src/services/scoring_service.py
  - docker-compose.yml
aliases:
  - overview
source_repository: .
source_revision: 44829d2
source_paths:
  - src/api/main.py
  - src/services/scoring_service.py
  - docker-compose.yml
---

# Fraud Detector Overview

## Context

Fraud Detector recibe transacciones, calcula una decisión de riesgo reproducible y entrega herramientas de análisis a un analista.

## Key facts

- API: FastAPI async.
- Persistencia: PostgreSQL mediante SQLAlchemy async.
- Mensajería: Redis Streams.
- Scoring: reglas + ML + contexto.
- Explicación: SHAP y LLM local mediante Ollama.
- UI: React 19 + TypeScript + Vite.

## Architecture

[[codebases/fraud-detector]] conecta [[codebases/fraud-detector-backend]], [[codebases/fraud-detector-frontend]], [[tools/redis-streams]], [[tools/xgboost-serving]] y [[runbooks/worker-recovery]].

## Current status

El código actual implementa scoring, ownership, JWT con revocación, soft delete, auditoría, workers Redis y monitorización. El estado debe comprobarse siempre contra [[sources/code-revision-44829d2]].

## Important decisions

- [[decisions/fraud-detector-architecture]]
- [[concepts/immutable-audit-trail]]
- [[concepts/fraud-detector-glossary]]
- [[tools/frontend-design-system]]
- [[sources/repository-documentation]]
- [[concepts/at-least-once-processing]]

## Risks and failure modes

- Dependencias externas pueden fallar; scoring y enriquecimientos tienen degradaciones diferentes.
- Los contratos de features y streams son sensibles al orden y nombres.
- [[comparisons/current-vs-historical-contracts]] contiene divergencias históricas.

## How to verify

- [[runbooks/local-development]]
- [[runbooks/testing-and-ci]]
- [[runbooks/end-to-end-debugging]]

## Related codebases

- [[codebases/fraud-detector]]
- [[codebases/fraud-detector-backend]]
- [[codebases/fraud-detector-frontend]]

## Sources

- `src/api/main.py`
- `src/services/scoring_service.py`
- `docker-compose.yml`
