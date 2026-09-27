# ADR-004: Soft Delete

**Estado:** Aceptado
**Fecha:** 2026-08-24

## Contexto

Las transacciones nunca deben borrarse físicamente por razones de auditoría y compliance.

## Decisión

Soft delete con `deleted_at`:
- `BaseModel` incluye `deleted_at` (nullable)
- Todas las queries filtran `deleted_at IS NULL`
- El admin puede "borrar" transacciones (soft delete)

## Consecuencias

- Las transacciones nunca se pierden físicamente
- Las queries deben incluir el filtro (riesgo de olvido)
- El soft delete es reversible
