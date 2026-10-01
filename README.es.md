# 🛡️ Fraud Detector Hybrid

[![CI](https://github.com/mikelrh-dev/fraud-detector/actions/workflows/ci.yml/badge.svg)](https://github.com/mikelrh-dev/fraud-detector/actions/workflows/ci.yml)

[English](README.md) | **Español**

> 📖 **Lee el [caso de estudio técnico](case-study/es/index.html)** — un recorrido en 11 capítulos de cómo funciona este sistema, cada número trazado a un artefacto real.
>
> 🧭 **Wiki técnica:** consulta la [wiki para desarrolladores](docs/wiki/index.md), con el modelo del sistema, arquitectura, scoring, workers, ML y operación.

Sistema híbrido de detección de fraude en transacciones financieras. Un **motor de reglas determinista** (7 reglas), un **modelo ML supervisado** (XGBoost) y un **LLM local** (Ollama) que redacta informes explicativos para analistas — el LLM nunca decide, solo explica.

> **Sobre el modelo ML, sin rodeos:** está entrenado sobre un **corpus sintético** de arquetipos de fraude generado en este repositorio — no con PaySim, ni con datos bancarios. Las reglas deciden; la capa ML aporta un 25% calibrado. Las cifras medidas y los límites conocidos están en [Qué hace el modelo y qué no](#qué-hace-el-modelo-y-qué-no).

Cada transacción recibe un score de riesgo 0–100, una clasificación (`legitimate | review | fraud`), atribuciones SHAP de sus features y, cuando se marca como sospechosa, un informe técnico generado asíncronamente por el LLM.

## Características destacadas

- **Scoring ensemble de 3 capas**: reglas 60% + ML 25% + contexto 15%, con umbrales de fraude dinámicos por tier de monto
- **7 reglas deterministas**: importe, velocidad, riesgo de merchant, patrones nocturnos y proximidad a redes de fraude
- **XGBoost** con 10 features engineered, degradación elegante (el sistema funciona con `ml_score = 0` si no hay modelo)
- **Explicabilidad SHAP**: top-5 contribuciones de features persistidas por transacción
- **Detección de redes de fraude**: grafo dirigido (NetworkX), marca usuarios a ≤ 2 saltos de un defraudador conocido
- **Detección de suplantación de merchant**: embeddings sentence-transformers + similitud coseno (detecta `AMAZ0N_STORE` → `Amazon`)
- **Redis Streams** con consumer groups, recuperación de mensajes pendientes (`XAUTOCLAIM`) y dead-letter queue
- **Monitoreo del modelo**: drift con PSI propio, triggers automáticos de reentrenamiento (F1 < 0.7 o drift > 30) — implementados, aún no ejercitados contra una referencia poblada
- **Audit trail inmutable** con checksums SHA-256 en cada decisión de scoring y acción de analista
- **Auth JWT** (access + refresh + blacklist), acceso por roles (user/admin), rate limiting por ruta
- **Dashboard React 19** con tendencias de score, tarjetas SHAP y flujo de trabajo de alertas
- **1210 tests de backend** (unitarios + integración) y 789 tests de frontend, CI con 5 jobs (ruff, mypy, pytest, ESLint, vitest, build smoke de Docker)

## Arquitectura

```mermaid
flowchart TB
    FE["Dashboard React 19"] -->|"REST + JWT"| API["FastAPI (async)"]

    API --> RE["Capa 1 · Rule Engine<br/>7 reglas deterministas"]
    API --> ML["Capa 2 · XGBoost<br/>10 features engineered"]
    API --> CTX["Capa 3 · Contexto<br/>historial · geo · tiempo"]

    RE --> ENS["Ensemble Scorer<br/>0.60 / 0.25 / 0.15"]
    ML --> ENS
    CTX --> ENS

    ENS --> DB[("PostgreSQL 16")]
    ENS -->|"review / fraud"| PUB["Stream Publisher"]

    PUB --> Q1["fraud:llm"] --> W1["LLM Worker<br/>informe Ollama (ES)"]
    PUB --> Q2["fraud:shap"] --> W2["SHAP Worker<br/>top-5 atribuciones"]
    PUB --> Q3["fraud:embeddings"] --> W3["Embedding Worker<br/>chequeo de spoofing"]

    W1 -. "3 reintentos fallidos" .-> DLQ["DLQ · fraud:dlq"]
    W2 -. "3 reintentos fallidos" .-> DLQ
```

**Stack:** Python 3.11 · FastAPI · PostgreSQL 16 (asyncpg) · Redis 7 (Streams) · XGBoost · SHAP · NetworkX · sentence-transformers · Ollama · React 19 + TypeScript + Vite + Tailwind 4 · Docker Compose (8 servicios)

## Cómo se puntúa una transacción

```
risk_score = 0.60 × rule_score + 0.25 × ml_score + 0.15 × context_score
```

La clasificación se compara contra un umbral dinámico que se endurece con montos mayores:

| Tier de monto | Umbral de fraude |
|---|---|
| $0 – $1,000 | > 70 |
| $1,001 – $10,000 | > 50 |
| $10,001 – $50,000 | > 45 |
| $50,001+ | > 40 |

La puntuación debe ser **estrictamente mayor** que el umbral del tier para ser `fraud`; los
tiers son semiabiertos `[min, max)`, así que no hay huecos en un límite. La banda `review`
arranca al 75% del umbral del tier (`>=`, porque ese es el comienzo de la banda). Por debajo,
la transacción es `legitimate`.

### Capa 1 — Motor de Reglas (determinista, tope 100)

| Regla | Peso | Disparador |
|---|---|---|
| `high_amount` | 35 | importe > $1,000 |
| `velocity_burst` | 30 | > 1 txn en 5 min en categoría de riesgo |
| `high_velocity` | 25 | > 3 txns en 5 minutos |
| `off_hours_crypto` | 25 | horario nocturno (0–6) **y** categoría adversarial |
| `unusual_merchant` | 20 | merchant en blacklist **o** categoría adversarial **o** categoría regulada con corroboración |
| `near_fraud` | 15 | usuario a ≤ 2 saltos de un defraudador (grafo) |
| `unusual_hours` | 10 | txn entre 00:00–06:00 |

El total es la suma de los pesos disparados, con tope 100.

Las categorías de merchant están jerarquizadas, y el nivel decide cuánto vale la categoría por
sí sola (`src/core/ml_constants.py`):

- **Adversarial** — la categoría es en sí misma evidencia de riesgo, así que `off_hours_crypto`
  y `unusual_merchant` se disparan con ella sola: `cryptocurrency`, `gambling`, `casino`, `adult`
  (`crypto` y `btc` son grafías alias que se normalizan a `cryptocurrency`).
- **Regulada** — es normal para el negocio, así que solo cuenta como *corroboración*:
  `unusual_merchant` se dispara con `pharmacy` o `money_transfer` solo cuando va acompañada de
  velocidad, una hora nocturna o un merchant en blacklist.
- **Conjunto de riesgo** (`MERCHANT_RISK_CATEGORIES`, 8 grafías — la unión de ambos niveles) — lo
  que comprueban `velocity_burst` y el feature engine.

La división es deliberada. Una única lista plana de "riesgo" cobraba 20 puntos de regla a cada
compra en una farmacia y a cada remesa sin ninguna evidencia.

### Capa 2 — Modelo ML (XGBoost)

10 features: `amount`, `amount_vs_user_avg`, `amount_vs_user_std`, `tx_count_last_5min`, `tx_count_last_1h`, `hour_of_day`, `is_weekend`, `merchant_risk_level`, `is_crypto`, `amount_round_number`.

La salida de `predict_proba` se escala directamente a 0–100 (`probability * 100.0`) y se calibra con `CalibratedClassifierCV(method="sigmoid", cv=5)` contra la prevalencia real del 1,00% del corpus — 502 fraudes en 50.000 transacciones, que el calibrador registra como `calibration_prior=0.010050` — de modo que la puntuación es una probabilidad contra esa tasa base, no un margen bruto. Si no hay archivo de modelo, la API sigue funcionando con `ml_score = 0`.

### Capa 3 — Contexto

Señales a nivel de usuario (velocidad de transacciones recientes) aportan el 15% restante, calculadas en `scoring_service.py` como `min(recent_txns / 10 × 100, 100)` y pasadas explícitamente al ensemble.

### Qué hace el modelo y qué no

Todas las cifras de esta sección las imprime `python scripts/evaluate_model.py`, sobre el split de test de 10.000 filas que queda retenido tanto del entrenamiento como de SMOTE. Las filas provienen del bloque de salida de ese split, no de un total mantenido a mano.

| | |
|---|---|
| ROC-AUC / PR-AUC en test retenido | 0,9181 / 0,7728 |
| En el umbral de producción | precisión 0,8353 · recall 0,7100 · F1 0,7676 |
| Matriz de confusión en ese umbral | TP=71 · FP=14 · FN=29 · TN=9886 |
| Falsos positivos | 14 de 9.900 legítimos |
| Fraudes no detectados | 29 de 100 |
| Error de calibración (ECE) | 0,0026 |

**Toda tasa aquí lleva intervalo, porque el split de test contiene 100 fraudes.** Una estimación puntual sin intervalo es una afirmación, no una medición. `evaluate_model.py` los imprime junto a las estimaciones puntuales:

| | Puntual | IC 95% (Wilson) | Amplitud |
|---|---|---|---|
| Precisión | 0,8353 | 0,742 – 0,899 | 15,7 pts |
| Recall | 0,7100 | 0,615 – 0,790 | 17,5 pts |

Estrechar el intervalo del recall es un problema de datos, no de modelado: con una prevalencia de alrededor del 1%, un intervalo de ±3 puntos necesita unos 3.600 fraudes en el split de test, **36× lo que contiene este corpus**. Cualquier proyecto que afirme un recall preciso a esta prevalencia o está midiendo otra cosa o te está enseñando un número que no puede sostener.

Es un clasificador real con poder discriminativo real, y está acotado. Cuatro límites, enunciados como lo que son:

1. **Los datos de entrenamiento son sintéticos.** Nunca hubo datos bancarios disponibles, así que el corpus se genera a partir de arquetipos de fraude (`everyday`, `burst`, `high_value_wire`, `card_testing`, …) diseñados para ser difíciles a propósito. El corpus y las features los escribió la misma persona, así que las cifras de arriba miden autoconsistencia, no detección.
2. **La transferencia a un benchmark independiente no está medida aquí.** Los corpora públicos de fraude como PaySim dan un usuario por transacción, lo que degenera las cuatro features de historial por usuario (`amount_vs_user_avg`, `amount_vs_user_std`, `tx_count_last_5min`, `tx_count_last_1h`): 4 de las 10 entradas dejan de aportar señal por usuario. Este repositorio **no afirma** cómo puntúa el modelo sobre un corpus de ese tipo, porque nada en él calcula eso.
3. **Ambas tasas principales descansan sobre 100 fraudes.** Un intervalo de recall de 17,5 puntos de amplitud no es un detalle de redondeo: es la resolución de esta medición. El desglose de errores por arquetipo que imprime el script es el corte más informativo: `low_signal` se pierde el 100% de las veces y `high_value_wire` el 39%, y ambas son clases que el generador escribe a propósito.
4. **El recall es 0,7100 en el umbral actual.** 29 de 100 fraudes no se marcan en ese punto de operación; el umbral es una compensación de costes, no un parámetro libre.

### Cuánto cuesta — y quién decide

Una cifra de precisión no es una decisión. Es un número al que se le ha quitado el coste de los dos lados, y un umbral compensa una falsa alarma contra un fraude no detectado — así que la compensación no se puede leer en ninguna de las dos cifras por separado. `scripts/evaluate_cost.py` le pone precio.

```
python scripts/evaluate_cost.py
```

**Ninguna de las dos cifras de coste está medida, y el script no finge lo contrario.** Lo que cuesta una falsa alarma es el tiempo de analista para descartarla; lo que cuesta un fraude no detectado es tu pérdida real. Ambas son hechos de negocio sobre *tu* operación. Por eso el script le asigna un precio arbitrario de 1.0 a una falsa alarma y barre el ratio `C_fn/C_fp`, porque solo el ratio mueve una decisión.

Sobre el mismo split retenido (TP=71 · FP=14 · FN=29 · TN=9886), en unidades donde una falsa alarma cuesta 1.0:

| Política | Coste esperado por transacción @ `C_fn/C_fp = 10` |
|---|---|
| No marcar nada (sin modelo) | 0,1000 |
| Marcar todo (sin modelo) | 0,9900 |
| **Este modelo en el punto por tramos actual** | **0,0304** |
| Este modelo en el mejor umbral plano (31,00) | 0,0291 |

De esa tabla salen dos cosas. Primera: **el umbral óptimo en coste no es una constante del modelo** — entre ratios de 1 a 500 se mueve de 74,00 a 0,25, dos órdenes de magnitud, así que cada creencia sobre el coste recibe un punto de operación distinto. Por eso el script imprime un barrido en lugar de una recomendación. El punto de producción por tramos está a menos de 0,0013 del óptimo barrido en este ratio, y el barrido es más barato en todos los ratios probados.

Segunda, el modelo tiene que superar *ambas* políticas sin modelo, y en este corpus lo hace en todos los ratios que prueba el script — 0,0291 contra un suelo de 0,1000 en el ratio 10, y todavía 0,8052 contra la barra de 0,9900 de "marcar todo" a 500×. Ningún AUC te dice eso; lo dice la aritmética de costes.

`breakeven_cost_ratio` es **99,0** — por encima de eso, marcar cada transacción sale tan barato como no marcar ninguna, porque con una prevalencia de alrededor del 1% un fallo tiene que ser mucho más caro que el tiempo de analista desperdiciado. Es una propiedad de la tasa base sola: el mismo número tanto si el modelo es excelente como si estuviera invertido, que es exactamente por lo que no puede usarse como evidencia en ningún sentido. El modelo todavía supera la barra de "marcar todo" a 500×, y el informe lo dice en lugar de insinuar lo contrario.

**Simplificación conocida, impresa en el informe:** el óptimo barrido es un umbral plano mientras que producción usa uno por tramos de importe, así que la comparación es aproximada. El volumen de 50.000 transacciones/día es una suposición que escala todas las cifras por día. Y los recuentos provienen de un corpus sintético — así que esto es aritmética, no evidencia. El coste real por transacción del modelo es **desconocido**, y esta es la aritmética que tenemos preparada para el día en que exista un corpus etiquetado.

## Explicabilidad, Monitoreo y Auditoría

- **SHAP** (`TreeExplainer` sobre XGBoost): top-5 atribuciones calculadas async por transacción puntuada, visualizadas en el dashboard.
- **Detección de drift**: una implementación PSI propia (distribuciones referencia vs actual). `GET /api/v1/monitoring/drift`.
- **Triggers de reentrenamiento**: se activan con `F1 < 0.7` o `drift_score > 30` (verificado en `MonitoringService`). La lógica está viva; la referencia de drift contra la que se compara nunca se ha poblado con una ventana completa, y ahora se niega a sembrarse con menos de 200 filas.
- **Audit trail**: cada score, revisión de analista e informe LLM se registra con checksums SHA-256. La exportación de actividad de analistas es solo admin.

## Workers Asíncronos (Redis Streams)

| Stream | Consumer group | Worker | Salida | Política de reintento |
|---|---|---|---|---|
| `fraud:llm` | `llm-workers` | `llm_worker` | fila `LLMReport` + entrada de auditoría | queda PENDING, máx. 3 |
| `fraud:shap` | `shap-workers` | `shap_worker` | filas `ShapAttribution` (top 5) | 3 reintentos → DLQ |
| `fraud:embeddings` | `embedding-workers` | `embedding_worker` | clave Redis con resultado (TTL 1h) | ack al success, log al fallo |

Los streams se recortan (`MAXLEN ~ 100,000`). La DLQ (`fraud:dlq`, tope 10K) guarda el stream original, el consumer group y el motivo del error. Un loop de recuperación reclama mensajes pendientes idle cada 60s vía `XAUTOCLAIM` (timeout de 5 min).

## Quick Start

### Con Docker (recomendado)

```bash
git clone https://github.com/mikelrh-dev/fraud-detector.git
cd fraud-detector
cp .env.example .env

docker compose up -d                                # 8 servicios: postgres, redis, ollama, api, 3 workers, frontend
docker compose exec ollama ollama pull qwen2.5:0.5b # LLM por defecto (configurable vía OLLAMA_MODEL)

# Frontend + API:  http://localhost:3000
# Docs API:        http://localhost:3000/docs
# Liveness:        http://localhost:3000/health
```

El puerto de la API no se publica deliberadamente al host, así que nginx es el
único punto de entrada: eso es lo que hace confiable el limitador por IP
(`X-Real-IP` se sobrescribe, no se agrega). La API se alcanza a través de nginx
en `:3000`, nunca en `:8000`.

Las tablas y las migraciones las aplica automáticamente el entrypoint del
contenedor `api` (`alembic upgrade head`) al arrancar, así que no hace falta un
paso de bootstrap aparte.

Creá tu primer usuario vía API:

```bash
curl -X POST http://localhost:3000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "analyst@example.com", "password": "...", "full_name": "Analyst"}'
```

> `scripts/create_admin.py` imprime un `INSERT` SQL listo para ejecutar si preferís sembrar un admin directamente.

### Desarrollo local

```bash
# Backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Obligatorio: Settings tiene tres campos sin default (DB_PASSWORD, REDIS_PASSWORD,
# REDIS_URL), así que la app no puede importarse sin un .env.
cp .env.example .env

# Solo infraestructura
docker compose up postgres redis ollama -d

python scripts/init_db.py    # create_all; el loop de dev no corre alembic
uvicorn src.api.main:app --reload

# Frontend (segunda terminal)
cd frontend && npm install && npm run dev
```

## Entrenamiento del Modelo ML

`models/xgboost_paysim_v1.joblib` está versionado, así que un clon recién hecho ya puntúa
con la capa ML completa: no hay nada que entrenar antes de usar el sistema. Reentrenar es
opcional; hace falta para cambiar el corpus, para reproducir las métricas de arriba o para
trabajar sobre el modelo:

```bash
python scripts/train_xgboost_aligned.py       # → models/xgboost_paysim_v1.joblib
# reiniciar la API para cargar el modelo
```

No hay un paso aparte de generación de datos. El trainer genera su propio corpus de 50.000
transacciones y ~1% de fraude si falta `data/synthetic_transactions.csv`, y se niega a
entrenar sobre cualquier corpus que no haya escrito él mismo: comprueba una marca
`corpus_schema`, así que un corpus producido por otro generador falla de forma ruidosa en
lugar de entrenar en silencio un modelo corrompido.

`scripts/generate_synthetic_data.py` es un generador **aparte** para notebooks y dashboards
de demostración: escribe una semilla de 5% de fraude en `data/demo_seed_transactions.csv`,
que no es un archivo que el trainer lea.

Si el artefacto falta o no se puede leer, la API igualmente arranca y puntúa, aportando
`ml_score = 0`: las capas de reglas y de contexto llevan la decisión por sí solas.

`train_xgboost_aligned.py` entrena sobre exactamente las features de `FeatureEngine` que usa producción. (`scripts/train_model.py` entrena una baseline XGBoost sin calibrar para comparar; escribe en su propio `models/xgboost_reference_v1.joblib` y no es el modelo que se sirve.)

## Endpoints de la API

### Autenticación
| Método | Ruta | Auth |
|---|---|---|
| POST | `/api/v1/auth/register` | público |
| POST | `/api/v1/auth/login` | público |
| POST | `/api/v1/auth/refresh` | refresh token |
| POST | `/api/v1/auth/logout` | user (blackliste el token) |

### Transacciones
| Método | Ruta | Auth |
|---|---|---|
| POST | `/api/v1/transactions` | user — crear + pipeline completo de scoring |
| GET | `/api/v1/transactions` | user — listado, filtros, paginación |
| GET | `/api/v1/transactions/{id}` | user — detalle + atribuciones SHAP |
| DELETE | `/api/v1/transactions/{id}` | **admin** — soft delete |
| GET | `/api/v1/transactions/graph/stats` | user — estadísticas del grafo de fraude |
| GET | `/api/v1/transactions/{uid}/graph-features` | user — features de grafo por usuario |
| GET | `/api/v1/transactions/{id}/embedding` | user — análisis de embedding del merchant |

### Alertas
| Método | Ruta | Auth |
|---|---|---|
| GET | `/api/v1/alerts` | user |
| POST | `/api/v1/alerts/{id}/review` | user |
| POST | `/api/v1/alerts/{id}/false-positive` | user |
| POST | `/api/v1/alerts/{id}/revert` | user |

### Reportes · Monitoreo · Auditoría
| Método | Ruta | Auth |
|---|---|---|
| GET | `/api/v1/transactions/{id}/report` | user — informe LLM (200 / 202 / 404) |
| GET | `/api/v1/monitoring/drift` | user — análisis de drift |
| GET | `/api/v1/monitoring/dashboard` | user — agregados del dashboard |
| GET | `/api/v1/monitoring/metrics` | analyst + admin — métricas de corridas ML |
| POST | `/api/v1/monitoring/reference-data` | **admin** — sembrar la ventana de referencia de drift |
| GET | `/api/v1/audit/transactions/{id}` | user — trail de decisiones |
| GET | `/api/v1/audit/analysts/{uid}` | **admin** — actividad del analista |
| POST | `/api/v1/audit/export` | **admin** — exportar por rango de fechas |

Health, todos públicos: `GET /health` (liveness estático) · `GET /health/ready` (ejecuta
`SELECT 1` contra Postgres y `PING` contra Redis — esto es lo que llama el healthcheck de
compose) · `GET /health/workers` (topología por worker) · `GET /api/v1/health` ·
`GET /api/v1/status`.

**Rate limits** (ventana fija de 60s, por IP de cliente, fail-open si Redis está caído):

| Ruta | Límite |
|---|---|
| `/api/v1/auth/login`, `/api/v1/auth/register` | 10/min |
| `/api/v1/auth/refresh` | 5/min |
| `/api/v1/auth/logout` | 20/min |
| `/api/v1/transactions` | 100/min |
| `/api/v1/alerts` | 60/min |
| `/api/v1/audit` | 60/min |
| `/api/v1/monitoring` | 30/min |

`/metrics` reporta la topología de workers sin auth. nginx deliberadamente **no** lo hace
proxy, así que es inalcanzable desde fuera de la red de compose — ver ADR-006.

## Estructura del Proyecto

```
fraud-detector/
├── src/
│   ├── api/                # FastAPI: main, rate_limit, v1/ (auth, transactions, alerts, reports, monitoring, audit)
│   ├── core/               # config, database, redis, security + stream_publisher / stream_manager / stream_dlq
│   ├── models/             # 12 modelos SQLAlchemy (transaction, user, fraud_score, fraud_alert, llm_report,
│   │                       #   ml_model_run, audit_entry, shap_attribution, rule, drift_reference,
│   ├── schemas/            # esquemas Pydantic v2
│   ├── services/           # rule_engine, feature_engine, ml_model, ensemble, shap_service,
│   │                       #   graph_service, merchant_embedding_service, velocity_store,
│   │                       #   llm, drift_service, monitoring, audit, transaction, auth
│   └── workers/            # llm_worker, shap_worker, embedding_worker (consumidores Redis Streams)
├── frontend/               # React 19 + TS + Vite + Tailwind 4 (8 páginas, 24 componentes, vitest + MSW)
├── tests/                  # unitarios + integración (1210 tests de backend)
├── scripts/                # init_db, create_admin, generate_synthetic_data, train_xgboost_aligned
├── notebooks/              # notebooks de exploración/entrenamiento con PaySim
├── docker/                 # Dockerfiles (api, frontend) + nginx.conf
├── alembic/                # migraciones
└── docker-compose.yml      # 8 servicios
```

## Testing

```bash
# Backend (1210 tests)
pytest tests/ -v --cov=src --cov-report=term
pytest tests/unit -v            # solo unitarios
pytest tests/integration -v     # solo integración — se ejecuta con db y redis SIMULADOS (ver conftest)

# Frontend
cd frontend && npm test         # vitest
```

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`), disparado en push/PR a `main`, `master` o `enhanced-proyecto`:

| Job | Qué hace |
|---|---|
| `backend-lint` | ruff + mypy |
| `backend-test` | pytest con contenedores de servicio PostgreSQL 16 + Redis 7 |
| `frontend-lint-test` | ESLint + vitest |
| `frontend-build` | build de producción (tras lint+test) |
| `docker-build` | build smoke de imágenes Docker (solo PRs) |

## Variables de Entorno

[.env.example](.env.example) es la lista autoritativa: cópiala y ajústala, en lugar de armar
una a mano:

```bash
cp .env.example .env
```

Tres configurações **no tienen default** en `Settings` y la app no arranca sin ellas:
`DB_PASSWORD`, `REDIS_PASSWORD` y `REDIS_URL`. Bajo compose, `REDIS_PASSWORD` también se
inyecta en `REDIS_URL` por ti.

```env
# Sin default — la app se niega a arrancar sin estas tres
DB_PASSWORD=...
REDIS_PASSWORD=...
REDIS_URL=redis://:...@localhost:6379/0

# Por defecto es un secrets.token_urlsafe(32) nuevo en cada arranque de proceso.
# Dejarlo vacío está bien en dev local; en producción debe inyectarse
# explícitamente o el arranque falla.
JWT_SECRET_KEY=

# ENVIRONMENT (alias: API_ENV) selecciona en silencio la rama de producción,
# que cambia CORS de "*" a solo FRONTEND_URL, desactiva /docs y
# /openapi.json, y exige que JWT_SECRET_KEY + API_SECRET_KEY se inyecten.
ENVIRONMENT=development

# Solo es seguro detrás de un proxy que SOBREESCRIBA X-Real-IP y
# X-Forwarded-For. docker/nginx.conf los sobrescribe, así que compose pone
# esto en true por su cuenta. Ponlo en false si expones el puerto de la API
# directamente: si no, un cliente puede falsear su IP y saltarse el
# limitador por IP.
TRUST_PROXY_HEADERS=false
```

Todo lo demás sí tiene un default real en `src/core/config.py`: `DB_USER=fraud`,
`DB_NAME=fraud_detector`, `DB_HOST=localhost`, `DB_PORT=5432`,
`OLLAMA_HOST=http://localhost:11434`, `OLLAMA_MODEL=qwen2.5:0.5b`, `OLLAMA_TIMEOUT=30`,
`JWT_ALGORITHM=HS256`, `JWT_EXP_MINUTES=15`, los pesos del ensemble `0,60 / 0,25 / 0,15`,
`FRAUD_DETECTION_ENABLED=true`, `VELOCITY_STORE_ENABLED=true` y
`FRONTEND_URL=http://localhost:3000`.

## Decisiones de Arquitectura

**¿Por qué 3 capas?** Las reglas son rápidas, deterministas y explicables — capturan patrones conocidos de fraude. El ML detecta lo que las reglas no pueden expresar. El contexto adapta el score a la línea base de cada usuario. Si una capa falla, las demás siguen produciendo un score.

**¿Por qué el LLM no decide?** Los LLMs son no deterministas y pueden alucinar. Ninguna decisión de bloqueo por fraude debería depender de uno. El trabajo del LLM es estrictamente *explicar* una decisión ya tomada a un analista humano — valor sin riesgo.

**¿Por qué XGBoost?** Supervisado, rápido en CPU, y su estructura de árboles se conecta directo a `TreeExplainer` para atribuciones SHAP por transacción.

**¿Por qué Redis Streams (y no solo listas)?** Los consumer groups dan entrega at-least-once, recuperación de mensajes pendientes (`XAUTOCLAIM`) y dead-letter queue — la diferencia entre "casi siempre funciona" y un pipeline auditable.

**¿Por qué soft delete?** Las transacciones son registros financieros. `DELETE` marca las filas como borradas; el historial queda consultable para auditoría y reentrenamiento.

## Licencia

MIT

## Autor

Proyecto de portfolio de [mikelrh-dev](https://github.com/mikelrh-dev) que demuestra:

- Arquitectura híbrida: reglas deterministas + ML + LLM local (con separación estricta entre decidir y explicar)
- ML en producción: feature engineering alineado entre entrenamiento y serving, explicabilidad SHAP, monitoreo de drift, triggers de reentrenamiento
- Pipelines async confiables: Redis Streams, consumer groups, reintentos, DLQ
- Seguridad: JWT con refresh + blacklist, RBAC, rate limiting, audit trail inmutable con SHA-256
- Disciplina de testing: 1210 tests de backend + suite vitest de frontend (789 tests), CI de 5 jobs
