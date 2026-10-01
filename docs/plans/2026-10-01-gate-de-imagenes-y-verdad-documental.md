# Gate de imagenes y verdad documental

## Que cierra

`CI verde` no prueba hoy que la imagen exista, y las cifras de los tests viven
a mano en diez ficheros que nadie verifica.

Este work unit no necesita Docker local: el runner de GitHub ya lo tiene, asi
que el gate se verifica en el propio CI.

## Defectos verificados

### D1 - el gate de imagenes solo corre en pull_request

`.github/workflows/ci.yml:161`

```
if: github.event_name == 'pull_request'
```

El push a `enhanced-proyecto` es el canal de entrega real del proyecto, y ahi
el job no se ejecuta. Todo lo que se haerlamentado sobre "la imagen construye"
sale de ejecuciones locales o de pull requests, nunca del camino de entrega.

### D2 - el job promete un smoke test que no hace

`.github/workflows/ci.yml:158` se llama `Docker Build (smoke test)`, pero los
dos unicos pasos son `docker build`. No hay `docker run`, ni health check, ni
ninguna lectura del resultado. El nombre afirma una verificacion que el job no
ejecuta, y un lector que confie en el nombre contara con una garantia inexistente.

### D3 - las derivaciones metricas de codigo no se detectan

`tests/docs/test_published_metrics.py` comprueba que los documentos coincidan
con `docs/published_metrics.json`. Ese manifiesto se genera a mano cuando cambia
un harness. Si `scripts/evaluate_model.py` cambia y nadie regenera, el guard
sigue verde porque compara documentos contra un manifiesto que ya no
corresponde al codigo.

Solo hay dos forma de que la deriva entre al repositorio: que alguien cambie el
manifiesto a mano, o que nadie lo regenere. La segunda es la probable.

### D4 - cuatro documentos repiten los defectos ya corregidos en QUICK_START

Verificado por busqueda sobre el contenido de cada fichero:

| Documento | Puerto `:8000` | `qwen2.5` | `alembic upgrade head` manual |
|---|---|---|---|
| `OPERATIONAL_GUIDE.md` | si | no | si |
| `NEXT_STEPS.md` | si | si | si |
| `ALL_PRODUCTION_FIXES_COMPLETED.md` | si | no | no |
| `docs/wiki/runbooks/local-development.md` | si | si | si |

`docker-compose.yml` publica un unico puerto host, `3000:80`. `8000` es
`expose:` interno del contenedor de API, y postgres, redis y ollama no publican
nada. Toda instruccion `localhost:8000` recibe conexion rehusada.

`alembic upgrade head` lo ejecuta el entrypoint bajo `set -e`. Documentarlo como
paso manual ensena a ejecutar el mismo paso dos veces, y hace creer que puede
fallar de forma independiente cuando no puede.

El modelo de produccion es `llama3.2:1b` en `src/core/config.py` y
`.env.example`. `qwen2.5` en un documento que empieza con `cp .env.example .env`
descarga un modelo que la aplicacion no pide.

### D5 - el recuento de tests vive a mano y ya no coincide

Los documentos afirman `1218 collected / 1180 passed`. El estado real es
`1221 passed`. El numero se desactualiza cada vez que se anade un test, y el
guard de metricas no lo cubre porque solo vigila cifras de ML.

## Decisiones

### D1/D2 - construir en push, y renombrar el job

Se retira el `if:` para que el gate corra en el canal de entrega real.

Coste: cada push paga el tiempo de construir dos imagenes. Se acepta porque un
gate que no corre en el camino de entrega no es un gate.

El job se renombra a `Docker Build (images only)`. Convertirlo en un smoke test
real exigiria un `docker run` con postgres y redis disponibles dentro de ese
job, lo que es un work unit propio. Prefiero un nombre honesto ahora que una
promesa incumplida.

### D3 - workflow separado para la deriva de metricas

Un `schedule:` en `ci.yml` ejecutaria **todos** los jobs cada noche, incluidos
lint, tests y build de frontend, para regenerar un JSON. Un workflow propio
`.github/workflows/metrics-drift.yml` con solo `schedule` y
`workflow_dispatch` ejecuta solo lo que debe.

El job regenera el manifiesto y falla si hay `git diff`. El generador tarda
entre 7 y 16 minutos, que es la razon de que no entre en cada push.

### D4 - corregir los cuatro documentos

Misma correccion ya aplicada y verificada en `QUICK_START.md`. Los cuatro
deben pasar los 41 tests de `tests/docs/` sin editar el test.

### D5 - el recuento se verifica en el job programado, no en el guard rapido

Ejecutar `pytest --collect-only` desde dentro de un test exige un subproceso
que carga `tests/conftest.py`, que exige `REDIS_PASSWORD` y las variables de
base de datos. Un guard que depende del entorno es un guard que falla por
razones ajenas a lo que comprueba.

El guard rapido se queda en 0,3 s. La comprobacion cara vive en el job
programado, que ya corre la suite real y puede affordar el coste.

## Fuera de alcance

- Smoke test real de la imagen: necesita postgres y redis dentro del job.
- Verificacion de migraciones contra Postgres real.
- Redis real para el drift monitoring.
- `MonitoringService` sin cablear.
- `model_status` que devuelve `"operational"` mientras `/health` dice
  `"not_loaded"`.

Todo lo anterior requiere Docker o una decision de producto.

## Criterio de terminado

1. Un push a `enhanced-proyecto` ejecuta `Docker Build (images only)` y termina
   en verde o rojo real.
2. El workflow programado regenera el manifiesto y falla ante cualquier diff.
3. Ninguno de los cuatro documentos contiene `:8000`, `qwen2.5` ni una
   instruccion `alembic` manual.
4. `tests/docs/`, ruff, mypy y la suite completa en verde.
5. `origin/master` sin modificar.