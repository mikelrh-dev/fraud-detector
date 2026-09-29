---
title: Wiki Lint Report — Frontier Knowledge Loop
type: source
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - lint
  - validation
project: fraud-detector
sources:
  - docs/wiki/
  - docs/wiki/sources/source-manifest-44829d2.json
  - docs/proposals/2026-08-29-frontier-wiki-migration.md
aliases:
  - wiki lint
source_repository: .
source_revision: 44829d2
source_paths:
  - docs/wiki/
  - docs/wiki/sources/source-manifest-44829d2.json
  - docs/proposals/2026-08-29-frontier-wiki-migration.md
---

# Wiki Lint Report — Frontier Knowledge Loop

## Scope

Loop completo de calidad documental tras la migración Frontier: metadatos, fuentes, hashes, relaciones, gráficos y artefactos derivados.

## Results

- Frontier directories present: pass.
- Legacy directories removed: pass.
- Required frontmatter fields: pass.
- Allowed page types/statuses: pass.
- `source_revision` declared: pass.
- Source paths exist: pass.
- SHA-256 source manifest generated: pass.
- Internal wikilinks resolve: pass.
- Backlinks regenerated from the relationship graph: pass.
- Absorb log retained: pass.
- Mermaid diagrams added to high-value flows: pass.
- README links target `docs/wiki/index.md`: pass.
- Secrets and `.env` excluded: pass.

## Relationship review

- Project hub links to overview, codebases, decisions, source and synthesis.
- Scoring links to features, velocity, ML, classification and end-to-end flow.
- Streams link to event contracts, at-least-once semantics and worker runbook.
- Features link to XGBoost, SHAP, monitoring and tests.
- Runbooks link back to the tools and concepts they operate.
- Historical comparison links to primary code source and repository documentation.

## Semantic review

- Código de `src/` y `frontend/src/` prevalece sobre README/OpenSpec históricos.
- Contradicciones se conservan en `comparisons/current-vs-historical-contracts.md`.
- No se inventan hashes: el manifest se genera desde bytes locales de las rutas declaradas.
- Los diagramas representan únicamente flujos respaldados por la revisión `44829d2`.

## Remaining uncertainty

El manifest representa el working tree local de las fuentes declaradas en el momento de generación; la revisión Git sigue siendo la referencia de versión. Los archivos `.obsidian/` detectados como no trackeados son externos a esta migración y no fueron modificados.
