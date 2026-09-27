# ADR-003: Scoring Pipeline en Servicios

**Estado:** Aceptado
**Fecha:** 2026-08-24

## Contexto

El scoring de fraude (rule engine → feature engine → ML → ensemble) debe ser reutilizable y testeable. Originalmente estaba en el endpoint de la API.

## Decisión

El pipeline de scoring vive en `ScoringService`:
- El endpoint de la API solo hace I/O (orquestación)
- `ScoringService.compute_scores()` es el punto único de verdad
- Los tests pueden probar el servicio sin HTTP

## Consecuencias

- El scoring es testeable sin HTTP
- El endpoint es delgado (solo I/O)
- El servicio puede ser reutilizado por otros componentes
