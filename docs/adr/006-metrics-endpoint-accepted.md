# ADR-006: `/metrics` se acepta sin restricción de acceso

**Estado:** Aceptado (riesgo aceptado, sin cambio de comportamiento)
**Fecha:** 2026-09-29
**Hallazgo:** OPS-02, auditoría 2026-09-29

## Contexto

`GET /metrics` (`src/api/v1/health.py:124`) publica la topología interna de
los workers sin dependencia de autenticación:

- longitud de los streams `fraud:llm`, `fraud:shap` y `fraud:embeddings`
- mensajes pendientes por consumer group
- `fraud_detector_worker_failures_total` por motivo de fallo

Es decir, cuántos workers existen, cómo se llaman, qué cola atienden y
cuánto se han atascado. La auditoría lo rated **bajo**, y con razón: los
endpoints Prometheus son convencionalmente anónimos, el payload es
topología interna y no contiene datos de negocio.

## Un hecho que corrige la premisa del hallazgo

Al redactar este ADR se comprobó la premisa del hallazgo ("alcanzable sólo a
través de nginx") y **es más fuerte de lo que el hallazgo afirmaba**:

- el servicio `api` **no publica ningún puerto** en `docker-compose.yml`;
  el único puerto publicado es `3000:80`, el del frontend
- `docker/nginx.conf` proxya únicamente `location /api/` y `location /health`
- `location /` sirve la SPA (`try_files $uri $uri/ /index.html`), no la API

`/metrics` no coincide con ninguno de los dos prefijos con `proxy_pass`, así
que **no es alcanzable desde fuera de la red de Docker**. Hoy responde sólo a
`http://api:8000/metrics` desde dentro de la red de compose. El riesgo
descrito por OPS-02 no materializa en el despliegue actual.

## Decisión

**Se acepta el riesgo. No se cambia el comportamiento de la aplicación.**

Ninguna de las correcciones disponibles es mejor que el hallazgo:

- **Autenticar el endpoint** rompe el scraping el día que exista un
  Prometheus, y hoy no hay ninguno que proteger. Se rompe una capacidad
  futura para corregir una exposición que la topología ya cierra.
- **Eliminar el endpoint** descarta una capacidad real: el contador de
  fallos por worker es la única señal de que un worker está atascado, y es
  la que A18 hizo observable a propósito.
- **Allow-list en nginx** no se puede verificar sin contenedor, y Docker está
  caído. Publicar un cambio de configuración que nadie ha ejecutado es peor
  que el hallazgo que corrige.

La compensación es que el endpoint no está expuesto, y eso se hace cumplir
por configuración, no por código.

## Condición que cambia la decisión

Esta decisión es válida **mientras el despliegue no exponga `/metrics`**.
Revisarla en cuanto ocurra cualquiera de estas tres cosas:

1. Se añade a `docker/nginx.conf` una `location` que proxee `/metrics`.
2. Se publica el puerto de `api` en `docker-compose.yml`.
3. Se añade una configuración de scrape de Prometheus al repositorio.

En ese momento hay que restringir **en nginx, antes de exponer**: `allow` para
la IP del scraper, un listener separado, o mTLS. Y junto con ese cambio,
decidir qué métricas se conservan: las longitudes de stream y los nombres de
los consumer groups son topología, y son la parte que un atacante usaría para
dimensionar un ataque contra las colas.

`tests/unit/test_deployment_health_invariants.py::TestMetricsNotExposed`
falla hoy si se publica el puerto de `api` o si nginx proxya `/metrics`, de
modo que la condición 1 y la 2 no pueden introductions en silencio.

## Consecuencias

- El hallazgo queda **registrado, no cerrado por código**. No hay test del
  endpoint que lo proteja, porque no hay nada en la aplicación que proteger:
  la garantía vive en `docker-compose.yml` y `docker/nginx.conf`.
- Cambiar la topología de despliegue sin revisar este ADR reintroduce OPS-02.
- Los nombres de los streams y de los consumer groups (`fraud:llm`,
  `llm-workers`, `llm-worker-1`) son configuración de Prometheus en la
  práctica: renombrarlos rompe los dashboards que se construyan sobre ellos.
  Conviene tratarlos como estables aunque hoy no exista ningún dashboard.

## Verificación

- `docker-compose.yml`: el servicio `api` no declara `ports`
- `docker/nginx.conf`: `proxy_pass` sólo en `location /api/` y
  `location /health`
- No existe `scrape_config` en el repositorio
- `pytest tests/unit/test_deployment_health_invariants.py` sin contenedor
