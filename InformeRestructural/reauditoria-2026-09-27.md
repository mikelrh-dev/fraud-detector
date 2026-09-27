# Reauditoría Completa — 27/09/2026

**Alcance:** backend (scoring), seguridad, fiabilidad/infra, frontend (visual + funcional).
**Método:** 4 auditorías paralelas con ejecución de código, + verificación personal de todos los críticos.
**Estado del repo:** 500 tests passing, 84.45% coverage, `ruff` limpio, `mypy` limpio, 164 tests frontend.

> **Contraste importante:** la suite está verde y los gates son honestos, y aun así
> los 5 críticos de abajo son invisibles para ella. Coverage mide cuántas líneas
> corrieron, no si la rama de fallo hace lo correcto.

---

## 🔴 CRÍTICOS — Verificados personalmente por mí

### C1 · `API_ENV` es una variable muerta: toda la postura de producción es inalcanzable
**`src/core/config.py:40`** · `.env.example:19` · `.env:20`

El campo de Settings se llama `environment`, así que pydantic lee `ENVIRONMENT`.
Ambos ficheros de entorno shippean `API_ENV=development`, que **nunca se lee**.

```
.env.example:19  API_ENV=development
.env:20          API_ENV=development
```

Todo lo que cuelga de `settings.environment == "production"` falla en silencio:
- `config.py:20-21` — el guard de secretos R1-005 **nunca se ejecuta**
- `config.py:116-120` — CORS se queda en `["*"]` con `allow_credentials=True`
- `main.py:38-39` — `/docs` y `/redoc` siguen públicos

**Escenario:** un operador copia `.env.example`, pone `API_ENV=production` y cree
que la caja está endurecida. No lo está: los secretos efímeros
(`secrets.token_urlsafe(32)`, regenerados por proceso) llegan a producción, CORS
es abierto y la documentación interactiva es pública.

**Fix (una línea):**
```python
environment: str = Field("development", validation_alias=AliasChoices("ENVIRONMENT", "API_ENV"))
```
Y corregir `.env.example` a `ENVIRONMENT=development` + `JWT_SECRET_KEY=`.

---

### C2 · Un NaN en el score ensemble se clasifica `legitimate` (fail-open)
**`src/services/ensemble.py:61, 89-93`** — verificado ejecutando:

```
combine(rule=35, ml=0.012, ctx=NaN) -> nan
classify(nan, 40)                   -> 'legitimate'
```

`min(max(nan, 0.0), 100.0)` devuelve `nan` (Python devuelve el primer operando
cuando la comparación es False), y todo `nan > t` es False → cae en
`legitimate`. El productor alcanzable es `scoring_service.py:101`
(`min(float(recent_txns)/10.0*100, 100.0)`), el único punto del pipeline que
**no** pasa por `_to_float`.

**Escenario:** una transacción de $60k con `high_amount` disparo queda
blanqueada porque un número upstream fue NaN.

**Fix:** en `combine()`, si algún score no es finito → devolver un valor
conservador; en `classify()`, `if math.isnan(score): return "fraud"`. Y pasar
`recent_txns` por `_to_float`.

---

### C3 · `amount = inf` lo acepta la API y se puntúa como legítimo
**`src/schemas/transaction.py:12`** · `src/services/ensemble.py:75,77` · `config.py:86`

Verificado ejecutando:
```
TransactionCreate(amount=inf)  -> ACEPTADO
TransactionCreate(amount=nan)  -> ValidationError
get_threshold(inf)             -> 70.0   (cae al default, no al tier 40)
rule_engine(inf)               -> 35.0 ['high_amount']  (no crashea)
```
El último tier tiene `max_amount = math.inf` pero el test es `amount < max`, así
que `inf` nunca casa y cae al `70.0` hardcodeado. No hay cota superior pese a
que la columna es `Numeric(12,2)`.

**Fix:** `amount: float = Field(..., gt=0, le=9_999_999_999.99, allow_inf_nan=False)`.

---

### C4 · `llm_worker` abandona los poison-pills: `UnboundLocalError` en el `except`
**`src/workers/llm_worker.py:167, 185, 146`** — verificado por lectura

```
146: await asyncio.gather(*tasks, return_exceptions=True)
167:     message_data = json.loads(data_json)      # dentro del try
185:     await _handle_failed_report(..., message_data)   # dentro del except
```

Si `.decode()` o `json.loads()` fallan, `message_data` nunca se asignó →
`UnboundLocalError` que `gather(..., return_exceptions=True)` **se traga en
silencio**. Resultado: ni ack, ni requeue, ni DLQ. El mensaje queda en el PEL,
`XAUTOCLAIM` lo reclama cada 60s, y el ciclo se repite para siempre.

**Fix:** `message_data: dict[str, Any] = {}` antes del `try`.

---

### C5 · Un fallo de API se renderiza como "cero riesgo" y "cero alertas"
**`frontend/src/pages/DashboardPage.tsx:46,53`** · `AlertsPage.tsx:45,117` · `ScoreTrendChart.tsx:134`

Verificado:
```
AlertsPage.tsx:45    const { data, isLoading } = useQuery(...)   ← sin isError
AlertsPage.tsx:117   {data?.total || 0} alertas                  ← "0 alertas"
DashboardPage.tsx:46 const { data: metrics, isLoading: metricsLoading } = useQuery(...)
ScoreTrendChart.tsx:134  result.push({ date: key, avgScore: 0 })
ScoreTrendChart.tsx:138  return result                            ← siempre 7 entradas
```

`buildDailyAverages` **nunca** devuelve `[]`: rellena los días sin datos con
`avgScore: 0`. Así que ante un 500 o un corte de red, el dashboard pinta una
línea plana en 0 en "Tendencia de Score Promedio" y cinco barras de altura 0,
sin ningún texto de error. Y `AlertsPage` muestra **"0 alertas"** — un falso
negativo sobre la superficie de alertas de fraude.

El detalle que lo hace aún más corrigible: **`TransactionsPage.tsx:42` sí tiene
`isError`**. Es inconsistencia interna, no limitación.

**Fix:** `isError` en ambas queries, panel de error antes del check de longitud,
y que `buildDailyAverages` devuelva `[]` (o `null` por hueco) en vez de ceros
fabricados.

---

## 🔴 CRÍTICOS — Afirmados por auditoría, NO verificados por mí

Ejecutados por el agente con evidencia `file:line`, pero no los reproduje yo.
Requieren confirmación antes de actuar.

| # | Hallazgo | Ubicación | Nota |
|---|---|---|---|
| C6 | `embedding-worker` **no arranca**: `sentence-transformers==2.2.2` + `huggingface_hub` 0.36.2 → `ImportError: cached_download`. Y `tests/workers/conftest.py:14-17` **mockea el módulo**, así que la suite está verde con producción caída | `requirements.txt`, `embedding_worker.py:18` | La peor clase de verde |
| C7 | `maxmemory-policy allkeys-lru` **evicta las colas y el DLQ** — un pico de memoria borra entradas en PEL y el DLQ, que es la única evidencia de fallo | `docker-compose.yml:21` | Debería ser `noeviction` |
| C8 | `alembic revision --autogenerate` emitiría `drop_table('drift_reference_data')` y `drop_constraint('uq_llm_reports_transaction_id')`. **Verifiqué la causa:** `DriftReferenceData` no está en `src/models/__init__.py.__all__` ni importado en `alembic/env.py` | `src/models/__init__.py`, `alembic/env.py:10-13` | Causa verificada por mí |
| C9 | Con el unique constraint, un report redelivered lanza `IntegrityError` → cae en el swallow de C4 → **nunca drena**. El report no se pierde; el mensaje sí | `llm_worker.py:71-95` | Falta `ON CONFLICT` |
| C10 | Redis caído → **500 en todos los endpoints autenticados** (falla cerrado, correcto, pero opaco) y añade 2s por request si Redis va lento | `dependencies.py:78` | Debería ser 503 explícito |

---

## 🟠 ALTOS

### Seguridad
| # | Hallazgo | Ubicación |
|---|---|---|
| A1 | **El path de token nunca lee la BD**: desactivar una cuenta o degradar un rol no cambia nada hasta 24h. Un refresh token de un usuario desactivado sigue minteando access | `dependencies.py:85`, `auth.py:106-107` |
| A2 | **Rotación de refresh es TOCTOU**: `is_token_blacklisted` y `blacklist_token` son dos awaits separados → N replays concurrentes pasan todos | `auth.py:110,122` |
| A3 | **Bypass de rate limit**: `docker-compose.yml:51-52` publica `8000:8000`, así que nginx (que sí sanea las cabeceras) es opcional y se salta. Con `X-Real-IP` fresco por request → credential stuffing ilimitado | `rate_limit.py:47-53` |
| A4 | **5 rutas sin limiter**: `audit/transactions/{id}`, `audit/analysts/{id}`, `audit/export`, `transactions/{id}/report`, `auth/logout`. `check_rate_limit` es dependencia **por router** | `audit.py:20`, `reports.py:14` |
| A5 | **Oráculo de timing de 303ms** en login: el bcrypt solo se paga si el usuario existe | `services/auth.py:95-99` |
| A6 | **Health endpoints filtran excepciones crudas** sin auth: username de BD, SQLSTATE, IP de contenedor | `health.py:40,47,84` |
| A7 | Agregados cross-tenant legibles por cualquier analyst (`/monitoring/dashboard`, `/monitoring/drift`, `/transactions/graph/stats`) | `monitoring.py:60-78` |
| A8 | `require_role("analyst")` es igualdad exacta → **un admin recibe 403** en `/monitoring/metrics` | `monitoring.py:206` |
| A9 | `ENVIRONMENT=production` deja `/openapi.json` en 200 (33KB de enumeración de rutas) | `main.py:38-39` |

### Scoring
| # | Hallazgo | Ubicación |
|---|---|---|
| A10 | **El ensemble no puede alcanzar `fraud` por debajo de $1000.01**: la capa de reglas topa en 100 → ×0.60 = 60.0 máximo, y el umbral de fraud es 70. En la práctica la detección bajo $1000 es solo-ML | `ensemble.py:50-61` vs `:63-77` |
| A11 | **Sin escalado por magnitud + umbrales que *bajan* con el monto**: $1,001 y $10.000M producen el mismo rule score, pero el umbral cae de 50 a 40. La transacción ballena — el caso para el que existe la regla — es el peor detectado | `rule_engine.py:52-55`, `config.py:70-90` |
| A12 | `rule_engine` crashea con `amount` no numérico o `merchant_name` no-str. No alcanzable por HTTP, pero cualquier consumidor futuro (batch, replay) hereda el 500 | `rule_engine.py:53-71` |
| A13 | `feature_engine` emite vectores no finitos y un `float()` sin guard | `feature_engine.py:81,89,96` |
| A14 | Un solo campo categórico dispara 3 reglas hasta 75/100 puntos; `money_transfer` y `pharmacy` están como "alto riesgo" → 20 puntos de falsos positivos de base en toda una clase de comercio | `rule_engine.py:66,72,90` |
| A15 | Capas con score 0 **consumen peso igual**: con el modelo ausente se pierden 25 puntos en cada score, en silencio | `ensemble.py:50` |

### Fiabilidad
| # | Hallazgo | Ubicación |
|---|---|---|
| A16 | **La API nunca corre migraciones** y `/health` no chequea la BD. Deploy contra BD no migrada → contenedor "healthy" y el primer request 500 | `Dockerfile.api:42`, `main.py:19-23` |
| A17 | `models/` no está en la imagen; solo funciona por el bind-mount. Sin el mount → `ml_score = 0` en todo, sin log de error | `Dockerfile.api:30-33` |
| A18 | `ShapUnavailableError` → ACK con cero atribuciones, y `/health/workers` reporta `ok`. Un shap worker mal configurado parece sano | `shap_worker.py:97-103` |
| A19 | **Publicación sin outbox**: los 3 `publish_event` son fire-and-forget. Un blip de Redis = miles de transacciones con score y **sin** report, sin SHAP, sin embedding, invisible | `transactions.py:331-383` |
| A20 | `send_to_dlq` traga sus propias excepciones y el worker LLM hace ACK igual → pérdida total sin evidencia | `stream_dlq.py:70-71`, `llm_worker.py:214-223` |
| A21 | El pruning del grafo nunca es durable (`persist()` solo hace `hset`/`sadd`, nunca `hdel`/`srem`) → los nodos podados resucitan en cada restart y las aristas crecen sin límite | `graph_service.py:180-191` |
| A22 | Snapshot de **todo** el grafo por transacción → O(V+E) por request | `transactions.py:304` |
| A23 | El healthcheck de Redis no manda contraseña → api/worker/shap/embedding pueden no arrancar nunca | `docker-compose.yml:21,24-28` |
| A24 | Postgres **sin timeouts**: ni `command_timeout`, ni `pool_size`, ni `pool_pre_ping`. Redis sí está defendido a 2s | `core/database.py:11-14` |

### Frontend — funcional
| # | Hallazgo | Ubicación |
|---|---|---|
| A25 | `useCountUp` **siempre anima desde 0** y el dashboard refresca cada 30s → los KPIs se rebobinan desde cero en bucle | `useCountUp.ts:33-59` |
| A26 | **No hay error boundary** en toda la app: un throw en render deja la página en blanco | `App.tsx:22-69` |
| A27 | **Tokens en `localStorage` en claro**, incluido el refresh token | `authStore.ts:19-53` |
| A28 | `refresh()` y `logout()` **existen y nunca se llaman** → al expirar el token se recarga toda la SPA y el logout del servidor nunca blacklistea | `api/auth.ts:50-70` |
| A29 | `ScoreHistogram` **descarta scores en los huecos float** entre buckets (20.5, 40.5, 60.5, 80.5) → el gráfico subreporta y las barras no cuadran | `ScoreHistogram.tsx:24-25,44` |
| A30 | `CreateTransactionPage` muestra esqueleto **antes de cualquier submit**; y un `user_id` oculto vacío deja el botón **permanentemente deshabilitado** sin diagnóstico | `CreateTransactionPage.tsx:164`, `21,37-41` |
| A31 | `fetchReport` traga los 500 → "No hay reporte disponible" cuando el worker está caído | `TransactionDetail.tsx:27-63` |

---

## 🟡 MEDIOS —.resumen

**Scoring:** un timestamp roto tiene dos fallbacks distintos y el de "ausente" es medianoche (el bucket de mayor riesgo) · `combine()` con dict parcial de pesos → الانسان de una sola capa · docstrings de `ml_model` describen un "smoothing" que el código no hace · tests con comentarios que contradicen el código.

**Seguridad:** el rate limiter **falla abierto** · BOLA inconsistente (404 en transactions/alerts, 403 en reports/audit → confirma existencia) · `POST /register` es oráculo de enumeración (`409`) · el limiter agrupa a todos los clientes sin IP en el bucket `"unknown"`.

**Fiabilidad:** los 7 índices de performance viven solo en la migración · drift de `ondelete` en 5 FKs · `settings.ollama_timeout` es config muerta · `save_reference_to_db` hace flush pero nunca commit · DLQ con `maxlen` exacto (descarta la evidencia más antigua justo cuando se desborda) · CI nunca corre migraciones pese a que el docstring del test afirma lo contrario · los servicios Postgres/Redis de CI no los usa ningún test · `mypy` excluye `alembic/`.

**Visual:** jerarquía tipográfica aplanada (H2/H3 nunca se usan; `<h1>` del dashboard no existe) · 5 paddings y 2 radios de card contra un valor specificado · 3 tratamientos de fondo de input · `space-y-6` en dos páginas y `space-y-4` en otra · ~15 colores de paleta Tailwind cruda saltándose los tokens semánticos · `DESIGN.md` se contradice a sí mismo en el hover del CTA y en el color de Review.

---

## 🎨 VISUALES — Los que más importan

### V-01 · Cuatro mapas de clasificación→color, y **ya divergieron** (no hipotético)
| Ubicación | Estados |
|---|---|
| `RiskMeter.tsx:8-12` | RiskTone → bg |
| `ScoreResultCard.tsx:34-38` | RiskTone → stroke |
| `TransactionTable.tsx:25-30` | bg + text + border |
| `TransactionDetail.tsx:78-83` | **strings byte-idénticos al anterior** |
| `AlertsPage.tsx:18-22` | solo texto, **sin `pending`** |

**Drift ya visible:** el Dashboard renderiza **dos pastillas verdes distintas** para el mismo estado "legítimo" en la misma tabla — `bg-fraud-legitimate-bg` (#052e16, verde opaco) en Clasificación vs `bg-status-approved/10` (#22c55e al 10%) en Estado. Mismo tono, tratamiento de superficie completamente diferente.

### V-02 · El estado `pending`/desconocido se pinta **verde** en el medidor de riesgo
`RiskMeter.tsx:18-24` — `return "clean"` es el fallback de *todo* lo no reconocido.
Un arco verde de 270° con "Pendiente" en el centro: un color que dice "seguro"
alrededor de un estado desconocido. `Badge.tsx:17` ya define un tono `neutral`
para esto.

### V-03 · El histograma contradice al medidor, al gauge y a su propia leyenda
`RISK_THRESHOLDS` (lib/risk.ts) dice warn 45 / critical 60. El histograma pinta
ámbar en `41-60` **y** `61-80`, reservando rojo para `81-100`. Un score 65 es
**rojo** en el gauge y el medidor, pero **ámbar** en el histograma — cuya leyenda
dice "Revisión (41-80)". Consistente consigo mismo, inconsistente con toda la app.

### V-04 · Tres renderizados de moneda distintos para el mismo número
`1234.56` se muestra como `$1234.56` (punto, sin separador) en la móvil, y
`$1.235` (**centavos descartados**) en la tabla y en el detalle. En una herramienta
de investigación de fraude, ocultar los centavos del monto en revisión es un
defecto de fidelidad de datos, no cosmético. Y el `$` está hardcodeado aunque
`tx.currency` viaja en el payload.

### V-05 · ~~Filas de tabla y cards móviles solo funcionan con ratón~~ RESUELTO
`<tr onClick>` sin `tabIndex`/`role`/`onKeyDown` → un usuario de teclado **no podía
abrir una transacción**. Resuelto con un `<Link>` real en la celda del comercio, no
con un parche de tabindex: eso además hace funcionar cmd-click, clic central y
"copiar dirección del enlace" para todo el mundo. El `onClick` de la fila se
conserva como comodidad de ratón y **descarta** los clics originados dentro del
enlace para no empujar dos entradas de historial. Aplicado en `TransactionTable` y
en la tabla y la card móvil de `TransactionsPage`. La fila gana
`focus-within:` para que el foco de teclado resalte la fila completa.

### V-06 · ~~El modal de confirmación no es un diálogo ni atrapa el foco~~ RESUELTO
Overlay `<div>` sin `role="dialog"`, sin `aria-modal`, sin foco inicial, sin
trampa, sin Escape, sin restaurar foco. Extraído a `components/ConfirmDialog.tsx`:
`role="dialog"` + `aria-modal` + `aria-labelledby`, foco al primer control al
abrir, Tab contenido (con envoltura en ambos sentidos), Escape para descartar,
foco devuelto al control que lo abrió, y `role="alert"` para el error inline.

> **Bug encontrado y corregido durante la implementación:** la trampa de foco
> filtraba los controlables con `offsetParent !== null`, que es `null` para todo
> elemento `position: fixed` en un navegador real. El filtro dejaba **un solo**
> control y la trampa no envolvía. Corregido para filtrar por marcado
> (`hidden` / `aria-hidden`) en lugar de layout.

### V-07 · ~~El hover del CTA aclara el botón~~ RESUELTO
`--color-accent` es #dc2626 y el hover era `bg-red-500` = #ef4444, **más claro**,
y `--color-action-hover` (#b91c1c, red-700) estaba **definido y sin usar**. Los 5
CTAs que quedaban (`CreateTransactionPage`, `LoginPage`, `RegisterPage` ×2,
`TransactionsPage`) ahora usan `hover:bg-action-hover`; el token pasa a estar vivo.
`DESIGN.md` sigue contradiciéndose en `:45` (red-500) frente a `:148` (red-700):
pendiente de corregir el documento.

### Lo que está bien hecho (y merece decirse)
El sistema de motion es lo más fuerte del repo: cap de stagger enforcing en *código* (`MotionList.tsx:18-25`, ~480ms máximo sin importar el largo de la lista), `PageTransition` keyed solo en `pathname` para que filtros y paginación no re-disparen, y el reduced-motion está completo (un guard CSS global + los tres paths JS optan explícitamente). **No hay librería de animación instalada**, exactamente como manda `DESIGN.md`. La deduplicación de la paleta de charts está documentada *y* testeada con un test que lee el source y falla ante cualquier hex literal. `Color nunca es el único signal`: cada badge combina color + texto + icono. La regresión desktop↔móvil está pineada por tests.

---

## 🔧 CÓMO LO VERIFICARÍA (lección de proceso)

Los 3 ingredientes que faltan y que habrían atrapado **todos** los críticos:

1. **Afirmar en la rama de fallo.** Hay tests para el camino feliz de cada
   worker, ninguno para payload malformado, DLQ fallido, o redelivery tras commit.
2. **Correr el diff de migraciones como test.** `EXPECTED_TABLES` derivado de
   `Base.metadata` no detecta que la tabla no esté *registrada* — hay que
   comprobar que todo modelo está en `__init__` y en `alembic/env.py`.
3. **Borrar el shim de `sentence_transformers`.** mockeando el módulo que
   rompe en producción, la suite no puede estar verde por accidente.

Y una cuarta, la más barata: un test que afirme que la variable de entorno de
producción es la que el código realmente lee.

---

# REMEDIACIÓN — 5 waves, spec → build → verify

Todo lo verificado con `ruff`, `mypy`, `pytest --cov-fail-under=80`, `tsc`,
`eslint` y `vitest` en la frontera de cada wave. Ninguna wave avanzó sin pasar
los gates.

| Wave | Commits | Qué |
|---|---|---|
| W1 | `4db8533` | C1, A8, A9 |
| W2 | `2b6b8c8` | C2, C3, A13 |
| W3 | `f9899ab` | C4, C9, A20 |
| W4 | `0dbc2a0` | C5, A29, + 2 errores de lint que rompían CI |
| W5 | `a8d0f6d` | C8 (y el drift que el test destapó) |

## Estado final

```
Backend   ruff ✅   mypy ✅ (64 files)   pytest 573 passed   coverage 86.07% (gate 80%)
Frontend  eslint ✅ 0 errors   tsc ✅   vitest 181 passed   vite build ✅
```

**Tests añadidos: 78** (15 production-posture, 33 non-finite, 18 worker
failure-path, 12 honest-data, 5 alerts-error) — todos sobre ramas que antes no
tenían ninguna cobertura.

## Críticos resueltos

| # | Resuelto en | Cómo |
|---|---|---|
| C1 `API_ENV` muerta | W1 | Alias `ENVIRONMENT` + test que prueba que el guard dispara por **ambos** nombres |
| C2 NaN → `legitimate` | W2 | `combine()` y `classify()` fallan cerrados; productor (`recent_transactions`) arreglado en origen |
| C3 `amount=inf` aceptado | W2 | `le` + `allow_inf_nan=False`; `get_threshold` no elige tier por accidente |
| C4 `UnboundLocalError` | W3 | `message_data` ligado antes del `try`; JSON no-dict coercionado |
| C5 fallo de API = riesgo 0 | W4 | `isError` en las 3 queries del dashboard y en alertas; `ErrorState` compartido |
| C8 autogenerate destructivo | W5 | Modelo registrado + **test de drift de migraciones** |

## Lo que el test de drift destapó al escribirlo

Escribí `test_migration_drift.py` esperando que pasara. Falló inmediatamente:
**7 índices de performance y `uq_llm_reports_transaction_id` existían solo en
las migraciones**, así que `autogenerate` habría emitido `drop_constraint` sobre
justo la constraint de la que depende la idempotencia del worker LLM (C9). Eso
no lo había detectado nadie porque el test anterior comparaba el conjunto
derivado consigo mismo.

## Un defecto que-metí-y-corregí

Al delegar `_process_message_with_retry` en `_process_message_safe` (para matar
el `except` que se tragaba todo), **rompí temporalmente la ruta de reintento**:
`_process_message_safe` no tenía rama para `success=False`, así que el mensaje
quedaba sin ACK **y** sin requeue. Lo detectó un test que ya existía
(`test_recovery_loop_reroutes_failing_to_dlq`). La lección: delegar para
eliminar duplicación también cambia comportamiento, y el test existente fue el
que me detuvo.

## Pendiente (no tocado, por decisión)

- **C6/C7** (embedding-worker no arranca, `allkeys-lru` evicta las colas) —
  requieren tocar `requirements.txt` y `docker-compose.yml`; C6 necesita
  desinstalar el shim de `sentence_transformers` en `tests/workers/conftest.py`,
  lo que hará fallar la suite hasta reinstalar la dependencia.
- **A1–A3** (token path sin BD, rotación TOCTOU, bypass de rate limit) —
  cambios de diseño en el flujo de auth, no parches. **Decisión tomada: A1 va
  después de los visuales de alto impacto.** La forma elegida es leer `User` en
  `/auth/refresh` (no en cada request), lo que baja la ventana de 24 h a los
  15 min del access token sin acoplar toda request autenticada a Postgres.
  Motivo de la prioridad: no existe ningún endpoint de gestión de usuarios, así
  que la única forma de desactivar una cuenta hoy es editar la BD a mano.
- **A10/A11** (el ensemble no alcanza `fraud` bajo $1000; umbrales que bajan con
  el monto) — requieren **recalibrar el modelo**, y eso cambia scores en
  producción. Decisión de negocio, no mía.
- **V-01 a V-04, V-08 a V-25** (visuales restantes) — tipografía aplanada, paddings
  y gaps inconsistentes, tokens saltados, jerarquía de headings y el error boundary
  global. V-05, V-06 y V-07 están cerrados. El siguiente paso de mayor impacto es
  la jerarquía de headings, porque `h1` falta en varias páginas y rompe la
  navegación por headings de cualquier lector de pantalla.
