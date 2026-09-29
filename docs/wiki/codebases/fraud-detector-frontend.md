---
title: Fraud Detector Frontend
type: codebase
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - react
  - typescript
  - vite
project: fraud-detector
sources:
  - frontend/src/
  - frontend/package.json
  - DESIGN.md
aliases:
  - frontend
source_repository: .
source_revision: 44829d2
source_paths:
  - frontend/src/
  - frontend/package.json
  - DESIGN.md
---

# Fraud Detector Frontend

## Context

Dashboard React para analistas que presenta scores, transacciones, alertas, explicaciones y métricas.

## Stack

React 19, TypeScript, Vite, React Router, TanStack Query, Axios, Zustand, React Hook Form, Zod, Recharts y Tailwind 4.

## Structure

- `pages/`: pantallas.
- `components/`: primitives y UI.
- `api/`: cliente HTTP.
- `store/`: estado persistido.
- `hooks/`, `lib/`, `types/`: lógica reutilizable y contratos.

## Entrypoints

`frontend/src/main.tsx` y `frontend/src/App.tsx`.

## Important files

- `frontend/src/App.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/store/authStore.ts`
- `frontend/src/pages/`

## Interfaces

Axios usa `/api/v1`, adjunta el access token desde `auth-storage` y redirige a login ante `401`.

## Decisions

El frontend presenta la clasificación del backend; no replica el algoritmo de scoring.

## Failure modes

Errores HTTP, sesión expirada, reportes pending y enriquecimientos async incompletos deben representarse como estados distintos.

## How to verify

`cd frontend && npm run lint && npm run test && npm run build`.

## Related projects

[[projects/fraud-detector]].

## Sources

- `frontend/src/`
- `frontend/package.json`
- `DESIGN.md`
