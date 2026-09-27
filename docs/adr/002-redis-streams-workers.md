# ADR-002: Redis Streams para Workers

**Estado:** Aceptado
**Fecha:** 2026-08-24

## Contexto

Los workers (LLM, SHAP, embeddings) necesitan procesar tareas asíncronas sin bloquear la API. Se requiere escalabilidad horizontal y tolerancia a fallos.

## Decisión

Redis Streams con consumer groups:
- **Streams**: `fraud:llm`, `fraud:shap`, `fraud:embeddings`
- **Consumer groups**: `llm-workers`, `shap-workers`, `embedding-workers`
- **DLQ**: Dead-letter queue para mensajes que fallan después de MAX_RETRIES

## Consecuencias

- Los workers pueden escalar horizontalmente
- Los mensajes no se pierden (at-least-once)
- Los mensajes tóxicos van a DLQ en vez de loop infinito
- Redis es un componente adicional en la infraestructura
