---
title: Local Development
type: runbook
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - development
  - docker
project: fraud-detector
sources:
  - docker-compose.yml
  - .env.example
  - README.es.md
aliases:
  - desarrollo local
source_repository: .
source_revision: 44829d2
source_paths:
  - docker-compose.yml
  - .env.example
  - README.es.md
---

# Local Development

## Definition

Procedimiento para levantar infraestructura, backend y frontend localmente.

## Key facts

```bash
cp .env.example .env
docker compose up -d
docker compose exec ollama ollama pull qwen2.5:0.5b
docker compose exec api alembic upgrade head
```

API en `http://localhost:8000`, frontend en `http://localhost:3000`, Redis en `6379`, PostgreSQL en `5432` y Ollama en `11434`.

## Interpretation

Compose proporciona el entorno integrado; el modelo ML es opcional y Ollama necesita descargar el modelo.

## Practical application

Para desarrollo separado: instalar requirements, levantar infraestructura y ejecutar `uvicorn`; en frontend usar `npm ci` y `npm run dev`.

## Uncertainty

Los comandos deben mantenerse sincronizados con README, Compose y scripts reales.

## Related

- [[runbooks/troubleshooting]]
- [[runbooks/testing-and-ci]]

## Sources

- `docker-compose.yml`
- `.env.example`
- `README.es.md`
