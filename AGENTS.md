# Fraud Detector — Project Instructions

## Project Overview
Sistema híbrido de detección de fraude. Motor de reglas determinista + LLM local (Ollama) para informes explicativos.

## Build & Run
```bash
# Desarrollo
docker compose up -d
uvicorn src.api.main:app --reload

# Tests
pytest tests/ -v --cov=src

# Linting
ruff check src/
mypy src/
```

## Architecture Decisions
- **Async everywhere:** FastAPI + SQLAlchemy async + asyncpg
- **Motor de reglas primero:** El LLM solo genera informes, no decide
- **Redis para queue:** Las solicitudes al LLM van por cola (no bloquean la API)
- **Soft delete:** Las transacciones nunca se borran físicamente
- **Score 0-100:** Cada transacción recibe un score de riesgo

## Key Conventions
- Endpoints versionados: `/api/v1/...`
- Todos los modelos tienen `created_at` y `updated_at`
- Los scores de fraude se calculan en el servicio, no en el endpoint
- El LLM worker es asíncrono y no bloquea la API
