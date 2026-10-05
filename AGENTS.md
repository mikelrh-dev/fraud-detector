# Fraud Detector — Project Instructions

## Project Overview
Sistema de detección de fraude en 3 capas de scoring: reglas deterministas 0.60 + XGBoost 0.25 + contexto 0.15 (`src/core/config.py`, ADR-005). Encima de ese scoring hay SHAP (atribución por transacción), señales de grafo (anillos de fraude), embeddings de merchants (suplantación), velocity store, una cola de conflictos y un outbox transaccional. El LLM local (Ollama) es un éndsima capa aparte: solo escribe informes explicativos, nunca decide.

## Build & Run
```bash
# Desarrollo
docker compose up -d
pip install -r requirements-dev.txt
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
- **Outbox transaccional:** Los eventos se escriben como filas `outbox_events` DENTRO de la transacción de scoring (`src/services/outbox.py`) y los publica un relay in-process en la API. No es "Redis para queue": la cola es una tabla, y por eso el evento nunca se pierde si el worker está caído
- **Tres streams encolados:** `fraud:llm` para cada transacción puntuada (sin filtro de clasificación), `fraud:embeddings` para cada transacción, `fraud:shap` solo para `fraud`/`review`. El LLM worker no aplica ningún filtro adicional
- **Sin ADR para el outbox:** el patrón está descrito en ADR-007 y en el propio `outbox.py`, pero no tiene un ADR propio
- **Soft delete:** Las transacciones nunca se borran físicamente
- **Score 0-100:** Cada transacción recibe un score de riesgo

## Key Conventions
- Endpoints versionados: `/api/v1/...`
- Todos los modelos tienen `created_at` y `updated_at`
- Los scores de fraude se calculan en el servicio, no en el endpoint
- El LLM worker es asíncrono y no bloquea la API
