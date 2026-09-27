# Fase 3 — Fiabilidad (Completada)

**Fecha:** 2026-09-27
**Estado:** Completada
**Tests:** 50 passed, 0 failed

---

## Resumen

Se corrigieron los fallos de fiabilidad en los workers y la cola Redis. El LLM worker ahora procesa mensajes con concurrencia, las excepciones se enrutan a DLQ correctamente, y el model-run tracking funciona.

---

## Cambios Prácticos

### 1. LLM Service: Excepciones en vez de Strings (C4)

**Problema:** `generate_report` capturaba errores y retornaba strings como `"Error: No se pudo conectar..."`. El worker detectaba el error con `startswith("Error:")` y marcaba como éxito → ACK. Sin retry, sin DLQ.

**Cambio:**
- `src/services/llm.py`: `generate_report` ahora lanza excepciones (`ConnectError`, `TimeoutException`, etc.) en vez de retornar strings

**Efecto práctico:**
- El worker puede detectar fallos reales y aplicar retry/DLQ
- Ollama caído → excepción → retry → DLQ (antes: ACK silencioso)

---

### 2. LLM Worker: Concurrencia y Manejo de Excepciones (C5/C12/C13)

**Problema:**
- `count=1` + await inline = 1 mensaje a la vez
- `asyncio.sleep(backoff)` dentro del loop serial = 60s de stall total
- Excepciones no se enrutaban a DLQ → poison-pill infinite loop

**Cambio:**
- `src/workers/llm_worker.py`:
  - `count=10` para procesar hasta 10 mensajes en paralelo
  - `_process_message_safe()` con `asyncio.gather()` para concurrencia
  - Excepciones enrutadas a `_handle_failed_report()` → retry/DLQ
  - Backoff fuera del read path (en el retry handler, no en el consume loop)

**Efecto práctico:**
- Throughput: ~10 reportes en paralelo (antes: 1 a la vez)
- Un mensaje tóxico no bloquea el worker completo
- Poison pills terminan en DLQ en vez de loop infinito

---

### 3. Unique Constraint en llm_reports (C6)

**Problema:** Sin unique constraint en `transaction_id`. El recovery loop podía insertar duplicados. `GET /report` retornaba 500 con `MultipleResultsFound`.

**Cambio:**
- Nueva migración `b81e3031f84b`: `uq_llm_reports_transaction_id` unique constraint

**Efecto práctico:**
- La base de datos previene reports duplicados
- El recovery loop no puede crear duplicados
- `GET /report` nunca retorna 500 por duplicados

---

### 4. Model-Run Tracking Funcional (C7)

**Problema:** `compute_scores` usaba `asyncio.create_task` desde un thread sin loop → `RuntimeError` → swallow silencioso. `GET /monitoring/metrics` siempre retornaba `{"runs": []}`.

**Cambio:**
- `src/services/scoring_service.py`: `compute_scores` ahora es `async`, con `await asyncio.to_thread()` para CPU-bound steps y `await` directo para tracking
- `src/api/v1/transactions.py`: `await _scoring_service.compute_scores(...)` en vez de `asyncio.to_thread`

**Efecto práctico:**
- `MLModelRun` records ahora se persisten
- `GET /monitoring/metrics` retorna datos reales
- El tracking es awaited, no fire-and-forget

---

### 5. Consumer Lag Alert (C14)

**Problema:** Si la cola se saturaba, no había alerta. El stream trimming podía eliminar trabajo no consumido sin que nadie se enterara.

**Cambio:**
- `src/workers/llm_worker.py`: `_recovery_loop` ahora monitorea `XLEN` y `XPENDING`, y loguea warning si `stream_len > 50000` o `pending > 100`

**Efecto práctico:**
- Operadores pueden detectar saturación de la cola
- El stream trimming es visible antes de que pierda trabajo

---

## Archivos Modificados

| Archivo | Cambio |
|---|---|
| `src/services/llm.py` | `generate_report` lanza excepciones |
| `src/workers/llm_worker.py` | Concurrencia, manejo de excepciones, consumer lag alert |
| `src/services/scoring_service.py` | `compute_scores` async con await tracking |
| `src/api/v1/transactions.py` | `await compute_scores` directo |
| `alembic/versions/b81e3031f84b_*.py` | Unique constraint en llm_reports |
| `tests/test_llm_service.py` | Tests actualizados para excepciones |
| `tests/test_llm_worker.py` | Tests actualizados para nuevo comportamiento |

---

## Verificación

```
tests/test_llm_service.py ................. 12 passed
tests/test_llm_worker.py .................. 18 passed
tests/unit/test_transaction_service.py .... 8 passed
tests/integration/test_transaction_api.py .. 12 passed

Total: 50 passed, 0 failed
```

---

## Impacto en el Sistema

### Antes de la Fase 3
- LLM caído → ACK silencioso, sin retry, sin DLQ
- 1 mensaje a la vez, 60s backoff bloqueaba todo
- Poison pills → loop infinito
- Reports duplicados → 500 en GET /report
- Model-run tracking nunca ejecutaba
- Sin alerta de consumer lag

### Después de la Fase 3
- LLM caído → excepción → retry → DLQ
- 10 mensajes en paralelo, backoff no bloquea
- Poison pills → DLQ
- Unique constraint previene duplicados
- Model-run tracking funcional
- Alerta de consumer lag

---

## Pendiente de la Fase 3

- Verificar que la migración `b81e3031f84b` se aplica correctamente en producción
- Considerar añadir métricas de Prometheus para consumer lag
- Considerar añadir un endpoint de health para el worker
