---
title: Fraud Detector API Contract
type: tool
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - api
  - fastapi
project: fraud-detector
sources:
  - src/api/v1/
  - src/schemas/
aliases:
  - API contract
source_repository: .
source_revision: 44829d2
source_paths:
  - src/api/v1/
  - src/schemas/
---

# Fraud Detector API Contract

## Context

REST API versionada bajo `/api/v1`.

## Key facts

Grupos activos: auth, transactions, alerts, reports, monitoring y audit. Los schemas Pydantic definen validaciones y formas de respuesta.

## Interfaces

- `POST /transactions`: crea y puntúa.
- `GET /transactions`: listado paginado.
- `GET /transactions/{id}`: detalle y SHAP.
- `/alerts`: acciones de revisión.
- `/transactions/{id}/report`: estado LLM.
- `/monitoring/*`: dashboard, drift, metrics y reference data.
- `/audit/*`: trail y exportación.

## Practical application

[[concepts/jwt-session-lifecycle]], [[entities/fraud-detector-domain-model]] y [[runbooks/end-to-end-debugging]].

## Uncertainty

Los permisos y códigos HTTP deben verificarse contra router y dependencias, no solo contra README.

## Related

- [[codebases/fraud-detector-backend]]
- [[entities/redis-event-contracts]]

## Sources

- `src/api/v1/`
- `src/schemas/`
