---
title: Fraud Detector
type: project
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - fraud-detection
  - fintech
project: fraud-detector
sources:
  - README.md
  - src/api/main.py
aliases:
  - Fraud Detector Hybrid
source_repository: .
source_revision: 44829d2
source_paths:
  - README.md
  - README.es.md
  - src/api/main.py
  - docker-compose.yml
---

# Fraud Detector

## Context

Proyecto de portfolio y sistema demostrativo para detección de fraude financiero.

## Purpose

Puntuar transacciones con reglas deterministas, ML y contexto, y proporcionar explicaciones operativas mediante SHAP y Ollama.

## Architecture

[[codebases/fraud-detector]] es el mapa global. Sus componentes son [[codebases/fraud-detector-backend]], [[codebases/fraud-detector-frontend]], [[tools/redis-streams]] y [[tools/xgboost-serving]].

## Current status

La revisión `44829d2` contiene API, dashboard, tres workers, PostgreSQL, Redis, modelo XGBoost opcional, auditoría y monitorización. La wiki considera activo solo lo respaldado por el código de esa revisión.

## Important decisions

[[decisions/fraud-detector-architecture]] documenta las decisiones observables.

## Risks and failure modes

Las integraciones LLM, Redis y modelos son dependencias con fallos diferenciados. [[comparisons/current-vs-historical-contracts]] registra documentación histórica contradictoria.

## How to verify

[[runbooks/local-development]] y [[runbooks/testing-and-ci]].

## Related codebases

- [[codebases/fraud-detector]]
- [[codebases/fraud-detector-backend]]
- [[codebases/fraud-detector-frontend]]

## Sources

- `README.md`
- `README.es.md`
- `src/api/main.py`
- `docker-compose.yml`
