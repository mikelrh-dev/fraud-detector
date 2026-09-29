---
title: Troubleshooting
type: runbook
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - operations
  - reliability
project: fraud-detector
sources:
  - docker-compose.yml
  - src/core/config.py
  - src/workers/
aliases:
  - problemas comunes
source_repository: .
source_revision: 44829d2
source_paths:
  - docker-compose.yml
  - src/core/config.py
  - src/workers/
---

# Troubleshooting

## Definition

Diagnóstico inicial de API, infraestructura, workers, modelo y frontend.

## Key facts

Usar `docker compose ps`, logs de servicio, health endpoints, estado Redis y migraciones antes de asumir un fallo de código.

## Practical application

- API: revisar `api`, PostgreSQL, Redis y `/health`.
- LLM: revisar Ollama, modelo configurado y `worker`.
- SHAP/embedding: revisar stream, PEL y worker correspondiente.
- DB: ejecutar `alembic current` y `alembic upgrade head`.
- Frontend: revisar API base `/api/v1`, sesión y build.

## Failure modes

Un servicio unhealthy puede producir síntomas secundarios en otros componentes. Separar disponibilidad, autorización, datos y procesamiento async.

## Uncertainty

No usar `docker compose down -v` salvo que se acepte perder datos locales.

## Related

- [[runbooks/local-development]]
- [[runbooks/worker-recovery]]
- [[runbooks/end-to-end-debugging]]

## Sources

- `docker-compose.yml`
- `src/core/config.py`
- `src/workers/`
