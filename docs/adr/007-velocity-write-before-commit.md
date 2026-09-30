# ADR-007: La escritura de velocidad precede al commit, y se acepta

**Estado:** Aceptado (riesgo aceptado, sin cambio de comportamiento)
**Fecha:** 2026-09-30
**Hallazgo:** F-07, fix loop 2 (`docs/plans/2026-09-28-fix-loop-2.md`)

## Contexto

`create_and_score_transaction` escribe la transacción en la sesión, y a
continuación escribe en Redis antes de que exista commit alguno:

- `src/api/v1/transactions.py:180` — `create_transaction(...)` (`db.add` + `flush`)
- `src/api/v1/transactions.py:197` — `velocity_store.record_transaction(...)` → `ZADD`
- `src/api/v1/transactions.py:198` — `velocity_store.get_counts(...)`
- el **commit real ocurre en el teardown de `get_db`**, después de que el handler
  devuelve

Un commit fallido deja entonces una entrada de velocidad para una transacción que
no existe. Esa entrada no apunta a ninguna fila: `transactions.id` es la clave
del ZSET y esa clave no está en la base de datos.

## Por qué la escritura NO puede moverse después del commit

Porque `get_counts` en la línea 198 es una **entrada del scoring de esta misma
petición**. Los conteos de velocidad entran en el vector de features que puntúa
la transacción que se está creando. La entrada tiene que ser visible antes de
que el handler devuelva, y el commit está después de que el handler devuelva.

Mover la escritura después del commit exige mover el commit dentro del handler.
Eso **sí** es reestructurar el ciclo de vida de la petición, que es
precisamente lo que este ADR evita. No es un cambio local: cambia quién es
responsable de la transacción y qué pasa con el rollback.

El patrón outbox que ya usa el repositorio (`:344-356`, A19) **no aplica aquí**,
y conviene dejarlo escrito porque es la objeción natural. El outbox sirve para
eventos que otro proceso consume *después*. La entrada de velocidad se consume
*ahora*, dentro de la misma petición. Encolar un evento y leerlo medio segundo
más tarde no es un refactor, es cambiar el scorer's input.

## Decisión

**Se acepta el riesgo. No se cambia el comportamiento de la aplicación.**

El hallazgo es real y no se cierra por código. Se registra.

## Por qué el error falla en la dirección correcta

Una entrada fantasma **infla** el conteo de velocidad del usuario. Velocidad más
alta significa:

- la regla `velocity_burst` (30 puntos) se dispara con más facilidad;
- las features de velocidad (`tx_count_last_5min`, `tx_count_last_1h`) suben.

Más velocidad es más riesgo. El sistema falla hacia **más sospechoso**, es decir
hacia falsos positivos y nunca hacia falsos negativos. En un detector de fraude
ésa es la dirección correcta para un residuo de este tamaño: un cliente legítimo
ve unos segundos de scoring elevado, no un fraude real clasificado como
legítimo.

## Compensaciones

- **Autolimitación en el tiempo.** `record_transaction` renueva `EXPIRE` con
  `VELOCITY_TTL_SECONDS` (90.000 s) y hace `ZREMRANGEBYSCORE` con
  `TRIM_SECONDS` (86.400 s). La entrada fantasma desaparece sola en ≤ 24 h sin
  ninguna tarea de limpieza. No hay que arreglar nada: se deshace.
- **Volumen acotado.** El residuo es de una entrada por commit fallido, para un
  usuario, y dura menos de un día. Un fallo de commit sostenido es un incidente
  de disponibilidad, no un drift de scoring.
- **`record_transaction` nunca lanza** (VEL-STORE-001). La escritura es
  best-effort por diseño, así que el orden no introduce un modo de fallo nuevo.

## Condición que cambia la decisión

Válida **mientras el conteo de velocidad se lea dentro de la misma petición que
lo escribe**. Revisarla si ocurre cualquiera de estas:

1. El scoring se mueve a un worker y la petición sólo encola.
2. `get_db` deja de hacer el commit en el teardown y el commit pasa a ser
   explícito en el handler.
3. Aparece un segundo consumidor de `velocity:{user_id}:tx` para el que un
   conteo inflado sea caro — por ejemplo, si una decisión de bloqueo dependiera
   del conteo y no sólo del score.

En ese momento hay que mover la escritura a después del commit, y hacerlo
usando el outbox que ya existe en el repositorio, no con un `commit()` suelto.

## Consecuencias

- El hallazgo queda **registrado, no cerrado**. No hay test que proteste por la
  entrada fantasma, porque no hay forma de observing el commit fallido sin
  contenedor; y un test que fallara permanentemente no sería un guard, sería una
  queja.
- `tests/integration/test_scoring_pipeline.py::TestVelocityWriteOrdering` fija el
  **orden** `record` → `counts` y que el conteo llega de verdad al vector de
  features. Pasa hoy: es un guard de la restricción que hace necesaria esta
  divergencia, no una reproducción. Si alguien mueve la escritura, el test
  falla y su mensaje apunta a este ADR.
- El orden de la sección 2 del handler no es libre de cambiar sin leer esto.

## Verificación

- `pytest tests/integration/test_scoring_pipeline.py` sin contenedor — 8 pasan
- El guard tiene poder discriminante: invirtiendo las dos líneas en
  `transactions.py:197-198` el test falla con
  `velocity calls were ['counts', 'record'], expected ['record', 'counts']`
- `mypy src/` limpio
- **No verificable sin contenedor**: que un commit fallido deje efectivamente la
  entrada en Redis. Eso exige un Postgres real y un Redis real. La dirección del
  error y la autolimitación se razonan desde el código de `velocity_store.py`,
  no se han observado.
