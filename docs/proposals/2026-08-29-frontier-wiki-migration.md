---
title: Migrar wiki de Fraud Detector a estructura Frontier
type: proposal
status: approved
risk: critical
created: 2026-08-29
updated: 2026-08-29
project: fraud-detector
sources:
  - src/
  - frontend/src/
  - tests/
  - scripts/
  - docker-compose.yml
  - pyproject.toml
  - frontend/package.json
  - .github/workflows/ci.yml
aliases:
  - frontier-wiki-migration
---

# Migrar wiki de Fraud Detector a estructura Frontier

## Intent

Reorganizar la documentación técnica existente desde una taxonomía temática no canónica hacia la estructura Frontier definida por `wiki-agent-protocol`, conservando el conocimiento útil, añadiendo frontmatter y wikilinks, y declarando el código actual como fuente de verdad primaria.

## Evidence

La implementación fue inspeccionada en la revisión:

- Repository: `.`
- Revision: `44829d2`
- Branch: `master`
- Código primario: `src/`, `frontend/src/`, `tests/`, `scripts/`
- Contratos/configuración: `pyproject.toml`, `frontend/package.json`, `docker-compose.yml`, `.github/workflows/ci.yml`

El protocolo canónico está en el vault externo `wiki-agent-protocol/`, especialmente `SCHEMA.md`, `workflows/bootstrap.md`, `workflows/apply.md` y `workflows/lint.md`.

## Planned changes

### Create

```text
docs/wiki/index.md
docs/wiki/overview.md
docs/wiki/concept-table.md
docs/wiki/concepts/*.md
docs/wiki/projects/*.md
docs/wiki/codebases/*.md
docs/wiki/decisions/*.md
docs/wiki/runbooks/*.md
docs/wiki/tools/*.md
docs/wiki/entities/*.md
docs/wiki/people/*.md
docs/wiki/sources/*.md
docs/wiki/comparisons/*.md
docs/wiki/synthesis/*.md
docs/wiki/_backlinks.json
docs/wiki/_absorb_log.json
docs/outputs/bootstrap/bootstrap-report-fraud-detector.md
docs/outputs/lint/wiki-lint-report.md
```

### Update

- `README.md`: enlace a `docs/wiki/index.md`.
- `README.es.md`: enlace a `docs/wiki/index.md`.

### Move / retire

Las páginas actuales de `docs/wiki/00-orientacion/` a `docs/wiki/09-contribucion/` se migrarán a las páginas Frontier equivalentes. No se borrará conocimiento sin registrar el mapeo. Los directorios antiguos se retirarán solo después de comprobar que todos sus contenidos tienen destino y que no quedan enlaces entrantes.

## Canonical structure

```text
docs/wiki/
├── index.md
├── overview.md
├── concept-table.md
├── concepts/
├── projects/
├── codebases/
├── decisions/
├── runbooks/
├── tools/
├── entities/
├── people/
├── sources/
├── comparisons/
├── synthesis/
├── _backlinks.json
└── _absorb_log.json
```

## Content mapping

| Existing page | Frontier destination | Type |
|---|---|---|
| `00-orientacion/que-es-el-sistema.md` | `concepts/hybrid-fraud-detection.md` | concept |
| `00-orientacion/glosario.md` | `concepts/fraud-detector-glossary.md` | concept |
| `01-arquitectura/mapa-del-sistema.md` | `codebases/fraud-detector.md` | codebase |
| `01-arquitectura/flujo-de-una-transaccion.md` | `synthesis/transaction-scoring-flow.md` | synthesis |
| `01-arquitectura/decisiones-clave.md` | `decisions/fraud-detector-architecture.md` | decision |
| `02-backend/estructura-del-codigo.md` | `codebases/fraud-detector-backend.md` | codebase |
| `02-backend/api-y-autenticacion.md` | `tools/fraud-detector-api.md` | tool |
| `02-backend/contratos-api.md` | `tools/fraud-detector-api-contract.md` | tool |
| `02-backend/autenticacion-y-sesiones.md` | `concepts/jwt-session-lifecycle.md` | concept |
| `02-backend/persistencia-y-migraciones.md` | `tools/postgresql-and-alembic.md` | tool |
| `03-scoring/pipeline-de-scoring.md` | `concepts/fraud-scoring-pipeline.md` | concept |
| `03-scoring/reglas-y-clasificacion.md` | `concepts/risk-classification.md` | concept |
| `03-scoring/degradacion-y-fallos.md` | `concepts/scoring-degradation.md` | concept |
| `04-pipelines/redis-streams-y-workers.md` | `tools/redis-streams.md` | tool |
| `04-pipelines/entrega-reintentos-y-dlq.md` | `concepts/at-least-once-processing.md` | concept |
| `04-pipelines/runbook-de-workers.md` | `runbooks/worker-recovery.md` | runbook |
| `05-ml/modelo-y-feature-engineering.md` | `tools/xgboost-serving.md` | tool |
| `05-ml/shap-embeddings-y-grafos.md` | `concepts/fraud-explainability.md` | concept |
| `05-ml/drift-y-monitorizacion.md` | `tools/model-monitoring.md` | tool |
| `05-ml/contrato-de-monitorizacion.md` | `entities/model-monitoring-contract.md` | entity |
| `06-datos/modelos-y-ciclo-de-vida.md` | `entities/fraud-detector-domain-model.md` | entity |
| `06-datos/contrato-de-features.md` | `entities/ml-feature-contract.md` | entity |
| `06-datos/eventos-y-contratos.md` | `entities/redis-event-contracts.md` | entity |
| `06-datos/auditoria.md` | `concepts/immutable-audit-trail.md` | concept |
| `07-frontend/arquitectura-y-flujo-de-analista.md` | `codebases/fraud-detector-frontend.md` | codebase |
| `07-frontend/design-system.md` | `tools/frontend-design-system.md` | tool |
| `08-operaciones/desarrollo-local.md` | `runbooks/local-development.md` | runbook |
| `08-operaciones/velocity-store.md` | `tools/velocity-store.md` | tool |
| `08-operaciones/troubleshooting.md` | `runbooks/troubleshooting.md` | runbook |
| `08-operaciones/debugging-end-to-end.md` | `runbooks/end-to-end-debugging.md` | runbook |
| `09-contribucion/testing-ci-y-checklist.md` | `runbooks/testing-and-ci.md` | runbook |
| `09-contribucion/arquitectura-de-tests.md` | `tools/test-architecture.md` | tool |

Additional pages:

- `projects/fraud-detector.md`: identity, purpose and current status.
- `sources/code-revision-44829d2.md`: source snapshot and revision metadata.
- `comparisons/current-vs-historical-contracts.md`: explicit historical/code divergences.

## Page contract

Every migrated page will include:

```yaml
---
title: ...
type: ...
status: active|needs-review
created: 2026-08-29
updated: 2026-08-29
tags: []
project: fraud-detector
sources: []
aliases: []
source_repository: .
source_revision: 44829d2
source_paths: []
---
```

Facts will be separated from interpretation and uncertainty. The code, not older README/OpenSpec claims, controls current behavior.

## Wikilinks

Internal relationships will use canonical wikilinks, for example:

- `[[projects/fraud-detector]]`
- `[[codebases/fraud-detector]]`
- `[[concepts/fraud-scoring-pipeline]]`
- `[[tools/redis-streams]]`
- `[[runbooks/worker-recovery]]`

Markdown links may remain only for external resources or paths where Obsidian resolution is not appropriate.

## Historical contradictions

The migration will not silently resolve contradictions. They will be recorded in `comparisons/current-vs-historical-contracts.md` with `status: needs-review` where relevant:

- current code uses XGBoost while an older OpenSpec mentions Isolation Forest;
- current thresholds and rule weights differ from historical documentation;
- monitoring has separate `MonitoringService` and `DataDriftService` paths;
- current worker retry/recovery behavior supersedes older audit findings.

## Risks and uncertainty

- Moving pages changes paths and can break external bookmarks.
- The repository does not currently contain the protocol's own `raw/` vault; code paths are cited directly as primary evidence.
- Generated backlinks and absorb logs are derived artifacts and must be reproducible.
- No semantic claim should be marked active if it is supported only by historical documentation.

## Validation

1. Validate every page has required frontmatter.
2. Validate `type` and `status` values.
3. Validate all `[[wikilinks]]` resolve.
4. Validate all cited source paths exist.
5. Validate source revision is `44829d2` unless explicitly marked historical.
6. Detect orphan pages and duplicate concepts.
7. Verify Frontier directories contain no untyped legacy pages.
8. Verify README links point to `docs/wiki/index.md`.
9. Produce `docs/outputs/lint/wiki-lint-report.md`.
10. Review historical contradictions manually.

## Approval

- Status: applied
- Approved: 2026-08-29
- Approved by: user
- Applied: 2026-08-29
