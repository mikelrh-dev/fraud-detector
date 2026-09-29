---
title: Bootstrap report — Fraud Detector
type: bootstrap-report
status: draft
created: 2026-08-29
updated: 2026-08-29
project: fraud-detector
source_repository: .
source_revision: 44829d2
---

# Bootstrap report — Fraud Detector

## Scope inspected

Se inspeccionaron los entrypoints, configuración, dependencias, modelos, schemas, servicios, workers, frontend, scripts, tests, CI y documentación existente. No se inspeccionaron dependencias generadas ni binarios como fuente de conocimiento.

## Project identity

- Name: Fraud Detector Hybrid
- Purpose: detección híbrida de fraude financiero con reglas deterministas, ML y explicación LLM local
- Language: Python 3.10/3.11 en backend; TypeScript en frontend
- Framework: FastAPI async; React 19 + Vite
- Package manager: pip/requirements en backend; npm en frontend

## Structure

- `src/api/`: FastAPI, routers, auth, rate limit y endpoints de negocio.
- `src/core/`: configuración, PostgreSQL, Redis, seguridad y streams.
- `src/models/`: SQLAlchemy ORM.
- `src/schemas/`: contratos Pydantic.
- `src/services/`: lógica de reglas, scoring, ML, monitorización, auditoría y enriquecimiento.
- `src/workers/`: consumidores Redis Streams para LLM, SHAP y embeddings.
- `frontend/`: dashboard React.
- `tests/`: pruebas unitarias, API, integración, migraciones y workers.
- `scripts/`: inicialización, datos sintéticos y entrenamiento.

## Entrypoints

- Backend: `src/api/main.py`.
- API versionada: `src/api/v1/router.py`.
- Scoring: `src/services/scoring_service.py`.
- LLM worker: `src/workers/llm_worker.py`.
- SHAP worker: `src/workers/shap_worker.py`.
- Embedding worker: `src/workers/embedding_worker.py`.
- Frontend: `frontend/src/main.tsx` y `frontend/src/App.tsx`.

## Commands

- Development backend: `uvicorn src.api.main:app --reload`.
- Development frontend: `cd frontend && npm run dev`.
- Build frontend: `cd frontend && npm run build`.
- Test backend: `pytest tests/ -v --cov=src`.
- Lint backend: `ruff check src/`.
- Typecheck backend: `mypy src/`.
- Lint frontend: `cd frontend && npm run lint`.
- Test frontend: `cd frontend && npm run test`.
- Infrastructure: `docker compose up -d`.
- Migration: `alembic upgrade head`.

## Main modules

- Rules: `src/services/rule_engine.py`.
- Feature contract: `src/services/feature_engine.py`.
- ML serving: `src/services/ml_model.py`.
- Ensemble: `src/services/ensemble.py`.
- Velocity: `src/services/velocity_store.py`.
- Audit: `src/services/audit.py`.
- Monitoring: `src/services/monitoring.py` y `src/services/drift_service.py`.
- Streams: `src/core/stream_publisher.py`, `stream_manager.py`, `stream_dlq.py`.

## External integrations

- PostgreSQL 16 mediante SQLAlchemy async/asyncpg.
- Redis 7 mediante redis-py async.
- Ollama para informes locales.
- XGBoost, SHAP, Evidently, sentence-transformers y NetworkX.

## Existing documentation

- `README.md` y `README.es.md`.
- `QUICK_START.md`.
- `OPERATIONAL_GUIDE.md`.
- `DESIGN.md`.
- `case-study/`.
- `openspec/`.
- `docs/audit-2026-08-24.md`.
- Wiki no canónica previa en `docs/wiki/00-orientacion/` a `docs/wiki/09-contribucion/`.

## Observed decisions

- Las reglas y ML producen la decisión; el LLM solo explica.
- El score final combina rules, ML y context.
- Redis Streams desacopla el trabajo asíncrono.
- PostgreSQL conserva el registro persistente.
- Las transacciones usan soft delete.
- El audit trail es append-only y lleva checksum.
- El scoring CPU-bound se ejecuta fuera del event loop.

## Risks and unknowns

- La documentación histórica no siempre coincide con el código actual.
- OpenSpec contiene referencias antiguas a Isolation Forest; el serving actual usa XGBoost.
- Hay dos servicios de monitorización con contratos diferentes.
- La estructura anterior de la wiki no cumple `SCHEMA.md`.
- La revisión actual debe considerarse la referencia temporal del código; cambios posteriores requieren actualizar `source_revision`.

## Proposed initial pages

La propuesta actual amplía la recomendación mínima del protocolo porque la wiki anterior ya contiene conocimiento que debe conservarse:

- `wiki/projects/fraud-detector.md`
- `wiki/codebases/fraud-detector.md`
- `wiki/codebases/fraud-detector-backend.md`
- `wiki/codebases/fraud-detector-frontend.md`
- `wiki/index.md`
- `wiki/overview.md`
- páginas de conceptos, entidades, herramientas, decisiones y runbooks según el mapeo de la propuesta.

## Evidence

- Revision: `44829d2`
- Primary paths: `src/`, `frontend/src/`, `tests/`, `scripts/`
- Configuration paths: `pyproject.toml`, `frontend/package.json`, `docker-compose.yml`, `.github/workflows/ci.yml`
- No secrets or `.env` contents were copied.
