# Monitoring: no cablear, desenmascarar

## Resumen

`MonitoringService` no esta muerto ni cableado: esta a medio construir, y el
sitio donde se cablearia es un error de dominio. Antes de tocarlo conviene
aclarar que hay DOS servicios de drift, tres valores de `model_status` en
vuelo, y una tabla cuyo nombre significa otra cosa.

## Lo que se verifico

### H1 - hay dos servicios de drift y solo uno se usa

`src/services/drift_service.py::DataDriftService` es el que usa la API
(`src/api/v1/monitoring.py:41`, con persistencia en base de datos via
`load_reference_from_db` / `save_reference_to_db` y modelo `DriftReferenceData`).

`src/services/monitoring.py::MonitoringService` implementa `compute_drift` con
otro calculo de PSI distinto. **Ningun endpoint lo usa.** Dos implementaciones de
la misma idea, una viva y otra no, es exactamente la forma que el ledger de
huerfanos ha estado eliminando.

### H2 - `MonitoringService` no esta muerto: el gancho existe y nunca dispara

`src/services/scoring_service.py:93` acepta `monitoring_service: Any | None = None`.
La rama esta escrita en L172 (`if monitoring_service is not None and db is not None`)
y llama a `_track_model_run` (L196).

**Ningun sitio de produccion pasa ese argumento.** `MonitoringService()` solo se
instancia en `tests/test_monitoring.py`. La rama es inalcanzable, pero el codigo
que la implementa es real y esta documentado como ML4.

### H3 - cablearlo seria un error de dominio, no una mejora

Este es el hallazgo que cambia la recomendacion.

`src/models/ml_model_run.py:20` documenta la tabla:

> Record of an ML model **training run** with performance metrics.

y su `status` solo admite `TRAINING`, `READY`, `FAILED` (L11-16).

Si se cablea `_track_model_run`, por cada transaccion puntuada se insertaria una
fila en una tabla de *entrenamientos*, con:

- `status=MLModelStatus.READY` fijo (`monitoring.py:183`), describiendo una
  inferencia con el estado de un entrenamiento terminado
- `drift_detected=False` fijo (`scoring_service.py:207`), dejando la columna
  decorativa
- `model_version="v1"` fijo (L205), mientras el modelo real es
  `xgboost_paysim_v1`

Eso no es "conectar una pieza pendiente". Es escribir una fila por transaccion en
una tabla de otra cosa, sin politica de retencion, con dos de sus tres columnas
constantes. **El parametro es el defecto, no la ausencia de cableado.**

Ademas `compute_metrics` y `check_retraining_trigger` dependen de etiquetas
reales, y el proyecto no tiene. `compute_drift` duplica `DataDriftService`.

### H4 - `model_status` tiene tres valores en vuelo

| Sitio | Valor |
|---|---|
| `src/api/v1/monitoring.py:189` | `"operational"` literal |
| `src/schemas/monitoring.py:66` | default `"unknown"` |
| `frontend/src/tests/mocks/handlers.ts:125` | `"active"` |

El endpoint de dashboard afirma que el modelo esta operativo sin preguntarselo.
`/health` declara `not_loaded`. El panel puede mostrar "operational" mientras el
health check dice que no hay modelo. Es la misma clase de mentira que este
proyecto lleva tres work units eliminando.

### H5 - `layers_used` esta partido en dos, y solo una mitad necesita Docker

`scoring_service.py:159` lo calcula y L192 lo pasa a `ScoringResult`. Luego se
descarta: no se persiste ni se expone.

`docs/plans/2026-09-28-fix-loop.md:37` ya lo decidio:

> Needs a column and a migration. A migration cannot be tested without a live
> database.

Por tanto:

- **Persistirlo** necesita migracion -> **bloqueado por Docker**
- **Exponerlo en la respuesta** solo necesita el schema -> **se puede ahora**

## Decision recomendada

1. **No cablear `monitoring_service`.** Se recomienda **borrar** el parametro,
   `_track_model_run` y `MonitoringService`, dejando que `DataDriftService` sea el
   unico servicio de drift. Requiere actualizar la expectativa de
   `tests/test_audit_orphans.py:92`.

2. **`model_status` derivado del estado real del modelo**, no literal. Un solo
   vocabulario, compartido con el frontend.

3. **`layers_used` en la respuesta de la API**, la mitad que no necesita
   migracion. La persistencia queda pendiente de Docker.

## La bifurcacion que hay que decidir

| | |
|---|---|
| **A. Borrar** (recomendado) | Elimina un duplicado y un gancho de dominio equivocado. Dificil de revertir, y hay que revisar la expectativa del ledger de huerfanos |
| **B. Dejarlo sin cablear y documentarlo** | Nada destructivo, pero el gancho confuso sigue en la firma de `compute_scores` y el siguiente que lo lea creera que funciona |
| **C. Cablearlo** | **No recomendado.** Escribe una fila por transaccion en la tabla de entrenamientos con dos columnas constantes |

**Decidido: A.**

## Trabajo

### W1 - borrar `MonitoringService`

- Borrar `src/services/monitoring.py`.
- Borrar `tests/test_monitoring.py`.
- Actualizar la expectativa de `tests/test_audit_orphans.py:92`, que hoy documenta
  el gancho como codigo alcanzable.

Comprobar antes de borrar que nada mas lo importa. Verificado: en `src/` solo lo
importa `scoring_service.py`.

### W2 - quitar el gancho de `compute_scores`

De `src/services/scoring_service.py`: el parametro `monitoring_service` (L93), su
linea de docstring (L100), la rama `if monitoring_service is not None and db is
not None` (L172-182) y `_track_model_run` (L195-210).

Actualizar `tests/test_drift_persistence.py`, que hoy pasa `monitoring_service`
en L119 y L168 y cuyo docstring de L80 afirma que deberia llamarse.

### W3 - `model_status` derivado

`src/api/v1/monitoring.py:189` devuelve `"operational"` literal. La senal real ya
existe: `src/api/v1/health.py:68` usa `_ml_service.is_available` y produce
`"ok"` / `"not_loaded"`.

El panel no debe afirmar que el modelo esta operativo sin consultarlo, sobre todo
cuando `/health` puede decir `not_loaded` en la misma respuesta.

Ademas hay tres vocabularios en vuelo: `"operational"` (API), `"unknown"`
(default en `src/schemas/monitoring.py:66`) y `"active"` (mock del frontend,
`frontend/src/tests/mocks/handlers.ts:125`). Queda **un** vocabulario.

### W4 - `layers_used` en la respuesta

`scoring_service.py:159` lo calcula y lo pasa a `ScoringResult`; luego se
descarta. Exponerlo en el schema de respuesta (ver `src/schemas/scoring.py` y
`src/schemas/transaction.py`) es la mitad que no necesita migracion.

La persistencia sigue bloqueada por Docker, igual que decidio
`docs/plans/2026-09-28-fix-loop.md:37`.

## Fuera de alcance

- Persistencia de `layers_used`: requiere migracion, luego Docker.
- `compute_metrics` / `check_retraining_trigger`: requieren etiquetas reales.
- Smoke test del contenedor: requiere Docker.