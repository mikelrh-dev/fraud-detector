---
title: Testing and CI
type: runbook
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - testing
  - ci
project: fraud-detector
sources:
  - pyproject.toml
  - frontend/package.json
  - .github/workflows/ci.yml
  - tests/
aliases:
  - testing
source_repository: .
source_revision: 44829d2
source_paths:
  - pyproject.toml
  - frontend/package.json
  - .github/workflows/ci.yml
  - tests/
---

# Testing and CI

## Definition

Procedimiento de validación del backend, frontend y builds.

## Key facts

Backend: ruff, mypy y pytest con coverage. Frontend: ESLint, Vitest y build TypeScript/Vite. CI además levanta PostgreSQL/Redis y ejecuta smoke builds Docker en pull requests.

## Practical application

```bash
ruff check src/
mypy src/
pytest tests/ -v --cov=src --cov-report=term
cd frontend
npm ci
npm run lint
npm run test
npm run build
```

## Failure modes

Warnings de tests async, mocks o librerías deben reportarse aunque no fallen el job. Los cambios de contratos requieren tests de producers, consumers y API.

## Uncertainty

La cobertura de mocks no prueba necesariamente integración real; cambios de migraciones y SQL deben validarse con infraestructura.

## Related

- [[tools/test-architecture]]
- [[entities/ml-feature-contract]]
- [[tools/fraud-detector-api-contract]]

## Sources

- `pyproject.toml`
- `frontend/package.json`
- `.github/workflows/ci.yml`
- `tests/`
