# SPEC — Loop 1: verificación observable (bloques 0 y 1)

**Rama:** `enhanced-proyecto`. **`master` no se toca bajo ninguna circunstancia.**
**Alcance:** que el CI se ejecute y quede verde. Nada más en este loop.

## Por qué esto va primero

Los bloques 3 y 5 corrigen documentación y contrato de ML. Pero mientras el CI no
se ejecute, toda esa corrección es **verificación local que ningún tercero ve**.
Un badge verde es la única afirmación del proyecto que un reclutador no tiene que
creerse, y es la de mejor relación valor/esfuerzo del plan.

## Bloque 0 — Cerrar el trabajo del LLM pendiente

Árbol sucio con `src/services/llm.py` y `tests/test_llm_service.py` modificados:
el ejemplo de regla única (el caso modal es 26,6% de transacciones frente a 6,4%
multirregla) y la retirada del merchant name del prompt, que se measuró pegado a
la prosa y almacenado en el informe.

Ya verificado antes de este loop: 18 tests del LLM pasan, ruff y mypy limpios, y
la invención de prosa bajó de 39 a 7 en la medición sobre el corpus real.

**Entregable:** un commit que describa el defecto, no la edición.

## Bloque 1 — Que el CI se ejecute y quede verde

### B1 · El trigger

`.github/workflows/ci.yml:4-6`

```yaml
on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]
```

Añadir `enhanced-proyecto` a ambas listas. **Causa raíz de que 165 commits no
tuvieran validación alguna**, más heroic than "el build está roto".

### B2 · El entorno

`ci.yml:97-103` (job `backend-test`) define `DB_USER`, `DB_PASSWORD`, `DB_NAME`,
`DB_HOST`, `DB_PORT`, `REDIS_URL` — y no `REDIS_PASSWORD`. `src/core/config.py:58`
lo declara sin default:

```python
redis_password: str  # No default — must be injected via env (security)
```

Efecto: `ValidationError` al importar `Settings`, que tumba **toda** la suite
antes de que.collect un solo test. Segundo bloqueador, independiente de B3.

El servicio Redis de CI corre `redis:7-alpine` con `--health-cmd "redis-cli ping"`
y **sin `--requirepass`**, así que el valor de `REDIS_PASSWORD` en CI es
puramente para satisfacer la validación de `Settings`, no para autenticar.

### B3 · La dependencia muerta

`requirements.txt:56` → `evidently==0.4.30`

- **0 imports** en `src/`, `scripts/`, `tests/`, `alembic/`, `notebooks/`.
- `src/services/drift_service.py` solo lo menciona en el docstring de la clase;
  la implementación es PSI hecho a mano con numpy.
- La única importaciones del repo están en `original/`, que **no está trackeado**
  y cuyos tests pytest no recoge.
- `src/api/v1/monitoring.py:313` conserva el comentario *"Evidently calculations
  are CPU-bound (500ms-2s)"*, que describe algo que no ocurre.

Es además lo que provoca el `ImportError` de agosto: `evidently 0.4.30` participa
en la resolución de `scikit-learn`, y `parse_version` **no existe en sklearn
1.5.0** — ni en `sklearn.utils` ni en `sklearn.utils.validation`, comprobado en
este venv.

**Acció:** eliminar la línea. Es una dependencia que no se usa y que constrain
el resolvedor.

## Verificación — cómo sé que funcionó

1. `gh run list` muestra un run **completed** sobre `enhanced-proyecto`.
2. Todos los jobs en verde.
3. El log del job contiene `N passed` y el coverage por encima de 80.
4. **`master` sigue en `44829d2`.** Invariante, no preferencia.

## Riesgos

- **Iteración obligatoria.** CI instala `requirements.txt`, que difiere del venv
  local en 9 paquetes. Si algo falla allí y no aquí, es un hallazgo: significa que
  el entorno de desarrollo no es el que se despliega.
- `httpx` está pineado en 0.27.0 y el venv local tiene 0.28.1. CI usa el pin, que
  es contra el que el código se escribió, así que **CI es más probable que pase
  que el venv local**. Reconciliar eso es el Bloque 2, fuera de este loop.
- Si B3 no bastara para el `ImportError`, la causa estará en la resolución de
  `scikit-learn` y habrá quemirar el árbol de dependencias en el log del run.
  **No se adivina: se lee el log.**

## Fuera de alcance

Bloques 2 (venv), 4 (observabilidad), 6 (Postgres real). Docs y contrato de ML
son el Loop 2. Nada de esto se toca aquí.