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
docker compose exec ollama ollama pull llama3.2:1b
```

No hay paso de migraciones: `docker/entrypoint.api.sh` corre `alembic upgrade head` bajo `set -e` antes de levantar uvicorn, así que las tablas se aplican al arrancar el contenedor `api`. Comprobarlo con `docker compose logs api | head -5` (`==> Applying database migrations`) o con `curl http://localhost:3000/health/ready`, que consulta Postgres y Redis de verdad.

Compose publica un solo puerto en el host: `3000:80` de `frontend`, que es nginx y hace de proxy hacia `api:8000`. El puerto `8000` de la API es un `expose:` interno, así que `curl http://localhost:8000/...` desde el host recibe conexión rehusada. PostgreSQL (`postgres:5432`), Redis (`redis:6379`) y Ollama (`ollama:11434`) tampoco publican nada: se alcanzan con `docker compose exec <servicio> <comando>`.

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
