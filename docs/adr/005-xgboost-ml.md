# ADR-005: XGBoost para ML

**Estado:** Aceptado
**Fecha:** 2026-09-27

## Contexto

El modelo ML debe ser ligero, rápido y compatible con el feature contract de 10 features. Originalmente se usaba IsolationForest pero producción usa XGBoost.

## Decisión

XGBClassifier con `scale_pos_weight`:
- 10 features (FeatureEngine)
- `predict_proba` escalado a 0-100
- `scale_pos_weight` para balance de clases
- Shape check explícito en `predict()`

## Consecuencias

- El modelo es rápido y ligero
- Las probabilidades son calibradas
- El shape check previene errores de feature contract
- El train script coincide con producción
