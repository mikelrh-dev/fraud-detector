# SPEC — Loop 2: lo que un третьим ejecuta primero (bloques 3 y 5)

**Rama:** `enhanced-proyecto`. **`master` no se toca.**
**Precondición cumplida:** Loop 1 cerrado con CI en verde (`6b10a25`, 4/4 jobs).

## Por qué este loop

El Loop 1 dejó el CI verde, pero el juez富裕 discovered que el verde no cubre lo que
un tercero hace primero: `docker compose up`. El job de Docker está condicionado a
`pull_request`, así que **las imágenes nunca se construyen en un push**, y
`conftest` mockea Postgres y Redis, así que **ningún test toca una base de datos**.

Este loop no arregla eso — requiere Docker. Arregla lo que sí se puede arreglar sin
Docker: **que las instrucciones que un reclutador copia literalmente funcionen, y que
el contrato de ML que el proyecto publica diga la verdad.**

## Bloque 3 — Lo que se ejecuta primero

### B3.1 · `QUICK_START.md` — el documento más roto del repo

Verificado contra los schemas y contra `docker-compose.yml`:

| Línea | Afirma | Realidad |
|---|---|---|
| 27-35 | payload de transacción | **422**: falta `currency`, y `user_id: "test"` no es UUID (`uuid_parsing`) |
| 23, 27, 62 | API en `localhost:8000` | compose **no publica el puerto de la API**. Solo `3000:80`. `api` tiene `expose: 8000`, que es interno |
| 24, 51 | `redis-cli ping` / `CONFIG GET` en el host | Redis no publica puerto |
| 64-66 | tabla de puertos 5432 / 6379 / 11434 | Ninguno se publica |
| 20 | `alembic upgrade head` manual | `docker/entrypoint.api.sh` ya lo ejecuta antes de servir, bajo `set -e` |
| 17 | `logs ollama \| grep "Successfully loaded"` | Nada descarga el modelo. El healthcheck es `ollama list`, que pasa con cero modelos |

Un reclutador que copia el TL;DR falla en el paso 6 y en el 7.

### B3.2 · El modelo en la documentación

`README.md:200` y `:416`, `README.es.md:201` y `:422`, `docs/deployment.md:34`
piden `ollama pull qwen2.5:0.5b`. `config.py:67` y `.env.example:28` dicen
`llama3.2:1b`. Como el Quick Start empieza por `cp .env.example .env`, la app
pedirá `llama3.2:1b` y el usuario habrá descargado otro modelo.

### B3.3 · El recuento de tests

«1210 backend tests» aparece en **10 sitios**: `README.md:30,347,358,444`,
`README.es.md:30,351,362,451`, `case-study/en/index.html:60,89`. Lo real es
**1218 collected / 1180 passed** — 1210 no es ningún número.

### B3.4 · `/transactions/graph/stats`

`README.md:289` lo describe como endpoint de usuario. `transactions.py:649-653`
devuelve **403 sin rol admin**.

## Bloque 5 — El contrato de ML

### B5.1 · La guarda que no puede dispararse

`scripts/train_xgboost_aligned.py:993` calcula
`contamination = np.sum(y_train) / len(y_train)`; `:1042` calcula
`calibration_prior = np.mean(y_train)`. Son **bit-idénticos** — medido:
`|diff| = 0.000e+00`. La guarda de `:1045` contra `1e-9` **nunca dispara**, y su
mensaje dice *"the corpus prevalence"* cuando ninguno de los dos operandos lo es.

Es la guarda de CAL-001, el defecto más sutil que encontró el proyecto.

**Y la trampa:** compararla contra `y.mean()` —la prevalencia real del corpus—
**rompe cada entrenamiento**, porque un split estratificado da 0.010050 frente a
0.010040, diferencia `1e-05` sobre una tolerancia de `1e-9`.

**Decisión:** no «arreglarla» hacia arriba. La afirmación honesta es que la
comparación es redundante por construcción, y que la verificación que sí significa
algo vive en `evaluate_model.py:394-400` y `tests/test_model_feature_contract.py`,
que releen el sello del artefacto ya desplegado. Se documenta como tal, en el sitio
donde alguien la leerá antes de tocar el pin.

### B5.2 · `evaluate_model.py:122` — labels falsos

```python
transactions, _ = T.add_realistic_noise(
    transactions, np.zeros(len(transactions), dtype=int), ...
)
```

La rama de ruido de fraude **no se ejecuta nunca**, y el log afirma
`fraud: 40.0% noise intensity`. **Todas las métricas publicadas se calcularon
sobre un corpus al que nunca se le aplicó el ruido de fraude.**

### B5.3 · El ledger de honestidad, falso en la dirección peligrosa

`tests/test_audit_orphans.py:55,106-108` marca `alerts_per_day`,
`optimal_threshold` y `breakeven_cost_ratio` como **"dead in cost_model.py"**.
`scripts/evaluate_cost.py:51` las importa, y generan la tabla de costes que el
README publica. Un mantenedor que se fiara del ledger podría **borrar código vivo
por leer una etiqueta que dice "dead"**.

## Verificación

1. Los payloads de `QUICK_START.md` validan contra los schemas de Pydantic.
2. Cada URL de `QUICK_START.md` resuelve a un puerto que compose publica, o es una
   orden `docker compose exec`.
3. `ollama pull` en los docs dice `llama3.2:1b`, igual que `config.py` y `.env.example`.
4. El recuento de tests coincide con lo que `pytest` imprime.
5. `grep` no encuentra ni una afirmación muerta en el ledger de orphans.
6. Gates locales verdes y **CI verde**.

## Fuera de alcance

- Docker: no se puede construir la imagen ni levantar el stack. Bloque 7 del plan.
- Postgres/Redis reales: Bloque 6.
- `mypy scripts/`, `evidently` en `original/`, `evaluate_cost.py` completa.

## Riesgo

Bajo en código, medio en documentación: cambiar Quick Start toca lo que la gente
copia. Mitigación — **cada URL y cada payload se comprueba contra compose y contra
Pydantic, no de memoria.**