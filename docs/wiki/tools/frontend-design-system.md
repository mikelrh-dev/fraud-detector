---
title: Frontend Design System
type: tool
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - frontend
  - design-system
project: fraud-detector
sources:
  - DESIGN.md
  - frontend/src/index.css
  - frontend/src/components/
aliases:
  - design system
source_repository: .
source_revision: 44829d2
source_paths:
  - DESIGN.md
  - frontend/src/index.css
  - frontend/src/components/
---

# Frontend Design System

## Context

Sistema visual dark-first para análisis de fraude.

## Key facts

`DESIGN.md` define tokens, colores semánticos de riesgo, tipografía, motion, responsive layout, badges, meters, gauge, charts e iconografía.

## Interfaces

Primitives importantes: `Badge`, `RiskMeter`, `ScoreGauge`, `ChartTooltip`, `PageTransition` y `MotionList`.

## Interpretation

El color de acción no debe confundirse con el color semántico de fraude; las páginas deben priorizar contraste y densidad informativa.

## Practical application

Consultar [[codebases/fraud-detector-frontend]] antes de crear componentes visuales nuevos.

## Uncertainty

La fuente visual es un documento de diseño además del código; para comportamiento runtime prevalece `frontend/src/`.

## Related

- [[index]]
- [[overview]]
- [[codebases/fraud-detector-frontend]]
- [[projects/fraud-detector]]
- [[codebases/fraud-detector-frontend]]

## Sources

- `DESIGN.md`
- `frontend/src/index.css`
- `frontend/src/components/`
