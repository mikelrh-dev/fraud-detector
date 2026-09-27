# ADR-001: Motor de Reglas + LLM Híbrido

**Estado:** Aceptado
**Fecha:** 2026-08-24

## Contexto

El sistema de detección de fraude necesita explicar sus decisiones. Un motor de reglas determinista es transparente pero rígido; un LLM es flexible pero no determinista.

## Decisión

Arquitectura híbrida:
- **Motor de reglas** (determinista): decide la clasificación final
- **LLM** (Ollama): solo genera informes explicativos, nunca decide

## Consecuencias

- Las decisiones son auditables y reproducibles
- El LLM puede fallar sin afectar la detección
- El LLM no bloquea la API (asíncrono vía Redis Streams)
