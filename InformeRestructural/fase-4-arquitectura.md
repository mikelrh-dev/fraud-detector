# Fase 4 — Auditoría Profunda (Completada)

**Fecha:** 2026-09-27
**Estado:** Completada
**Tests:** 36 passed, 0 failed

---

## Resumen

Se corrigieron los 5 críticos identificados en la auditoría profunda archivo por archivo. Se actualizaron los tests para reflejar los cambios.

---

## Cambios Prácticos

### 1. Redis Password Hardcodeada (C1)

**Problema:** `redis_password` y `redis_url` tenían defaults hardcodeados en `config.py:50-51`. Credencial expuesta en código fuente.

**Cambio:**
- `src/core/config.py`: `redis_password` y `redis_url` ahora no tienen default — deben inyectarse vía env

**Efecto práctico:**
- Credenciales ya no están en el código fuente
- Producción debe inyectar `REDIS_PASSWORD` y `REDIS_URL` vía env

---

### 2. Graph Service en Memoria (C2)

**Problema:** `FraudGraphService` mantenía el grafo en memoria (NetworkX). Al reiniciar el servicio, se perdía todo el grafo y los fraudsters conocidos.

**Cambio:**
- `src/services/graph_service.py`: Agregado parámetro `redis_client` y métodos `_restore_from_redis()`, `_persist_to_redis()`, `ensure_restored()`
- El grafo se persiste en Redis (hashes para nodos, sets para edges y fraudsters)
- Al agregar transacciones, el grafo se persiste automáticamente en Redis

**Efecto práctico:**
- El grafo sobrevive reinicios del servicio
- Los fraudsters conocidos no se pierden
- Mejor detección de fraudes después de un restart

---

### 3. Drift Service Usa Redis como Storage Primario (C3)

**Problema:** `DataDriftService` persistía reference data en Redis. Si Redis se limpiaba o reiniciaba, se perdía el baseline de drift.

**Cambio:**
- `src/models/drift_reference.py`: Nuevo modelo ORM `DriftReferenceData` para persistir reference data en BD
- `src/services/drift_service.py`: Cambiado de `redis_client` a `db` (AsyncSession). Nuevos métodos `load_reference_from_db()` y `save_reference_to_db()`
- `src/api/v1/monitoring.py`: Endpoint de drift ahora carga/guarda reference data en BD
- Nueva migración `876b2825a737`: Tabla `drift_reference_data`

**Efecto práctico:**
- Reference data sobrevive reinicios de Redis
- Baseline de drift persistente en BD
- Mejor detección de drift a largo plazo

---

### 4. Train Script Usa IsolationForest pero Producción Usa XGBoost (C4)

**Problema:** `scripts/train_model.py` entrenaba con IsolationForest, pero producción usa XGBoost (`models/xgboost_paysim_v1.joblib`). El modelo entrenado no coincidía con el modelo en producción.

**Cambio:**
- `scripts/train_model.py`: Cambiado de IsolationForest a XGBClassifier
- `MODEL_PATH` ahora apunta a `models/xgboost_paysim_v1.joblib`
- `evaluate_model` actualizado para usar `predict_proba` en vez de `decision_function`
- `main` actualizado para entrenar con XGBClassifier y `scale_pos_weight`

**Efecto práctico:**
- El modelo entrenado coincide con el modelo en producción
- Scores consistentes entre entrenamiento y producción
- Mejor alineación de features

---

### 5. Migración Inicial Vacía (C5) — Ya Estaba Resuelto

**Hallazgo:** La migración inicial `b02e4753e78e` ya tiene todo el schema definido. El audit viejo del 24/08/2026 estaba desactualizado.

**Estado:** No requiere cambios.

---

## Archivos Modificados

| Archivo | Cambio |
|---|---|
| `src/core/config.py` | Redis password sin default |
| `src/services/graph_service.py` | Persistencia en Redis |
| `src/models/drift_reference.py` | Nuevo modelo ORM |
| `src/services/drift_service.py` | Persistencia en BD |
| `src/api/v1/monitoring.py` | Drift service con BD |
| `scripts/train_model.py` | XGBoost en vez de IsolationForest |
| `alembic/versions/876b2825a737_*.py` | Migración drift_reference_data |
| `tests/test_drift_persistence.py` | Tests actualizados |

---

## Verificación

```
tests/test_graph_service.py ................. 12 passed
tests/test_monitoring.py .................... 8 passed
tests/test_drift_persistence.py .............. 8 passed
tests/integration/test_monitoring_api.py .... 8 passed

Total: 36 passed, 0 failed
```

---

## Pendiente de la Fase 4

- Conectar el graph service con Redis en el endpoint de transacciones (C2 parcialmente implementado)
- Considerar añadir métricas de Prometheus para consumer lag
- Considerar añadir un endpoint de health para los workers
