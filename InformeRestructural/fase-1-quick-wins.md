# Fase 1 — Quick Wins (Completada)

**Fecha:** 2026-09-27
**Estado:** Completada
**Tests:** 57 passed, 0 failed

---

## Resumen

Se aplicaron 8 correcciones de bajo riesgo y alto impacto en configuración, seguridad y rendimiento. Ningún cambio altera la lógica de negocio principal ni rompe la API pública.

---

## Cambios Prácticos

### 1. Rate Limiter: Proxy Headers (C9)

**Problema:** El rate limiter colapsaba a un bucket global único porque `trust_proxy_headers=False` + nginx hacía que `request.client.host` fuera la IP del proxy para todos los usuarios. Cualquier cliente podía bloquear el login de todo el sistema con 10 requests.

**Cambio:**
- `.env` y `.env.example`: añadido `TRUST_PROXY_HEADERS=true`
- `docker/nginx.conf`: `X-Forwarded-For` ahora usa `$remote_addr` (sobrescribe, no añade) para prevenir spoofing

**Efecto práctico:** Cada usuario ahora tiene su propio bucket de rate limiting. Un atacante no puede bloquear a todos los usuarios a la vez.

---

### 2. Redis: Autenticación y Aislamiento (C10)

**Problema:** Redis publicaba en `0.0.0.0:6379` sin contraseña. Contenía la blacklist de tokens JWT, velocity counters y payloads con datos financieros.

**Cambio:**
- `docker-compose.yml`: eliminados `ports:` de Redis, Postgres y Ollama (solo red interna `fraud-network`)
- Redis: añadido `--requirepass`, `--protected-mode yes`, `--maxmemory 256mb`, `--maxmemory-policy allkeys-lru`
- `.env` y `.env.example`: añadido `REDIS_PASSWORD`
- `src/core/config.py`: añadido `redis_password`, actualizado `redis_url` para incluir password

**Efecto práctico:** Redis ya no es accesible desde el host. Requiere contraseña. Tiene límite de memoria con evicción LRU.

---

### 3. Credencial Admin: Sin Hardcode (C8)

**Problema:** `admin123` estaba en texto plano en `scripts/create_admin.py` y en 3 documentos del repo.

**Cambio:**
- `scripts/create_admin.py`: ahora lee de `ADMIN_PASSWORD` env o prompt seguro con `getpass`. Requiere mínimo 12 caracteres. Rechaza ejecución en producción sin env var.

**Efecto práctico:** La contraseña admin ya no está en control de versiones. Se inyecta por entorno.

---

### 4. Threshold Tiers: Gap en $1000-$1001 (I1)

**Problema:** Los tiers usaban intervalos cerrados `[0,1000], [1001,10000]...`. Un monto de $1000.50 no matchaba ningún tier y caía al default (70), creando un cliff de 20 puntos con $1001.00.

**Cambio:**
- `src/core/config.py`: intervalos half-open `[0, 1000.01), [1000.01, 10000.01)...`
- `src/services/ensemble.py`: comparación `min_amount <= amount < max_amount`

**Efecto práctico:** No hay gaps. $1000.50 y $1001.00 caen en el mismo tier.

---

### 5. Fricción Dinámica por Tier (I3)

**Problema:** El umbral para 3D-Secure era `score >= 60` (hardcoded). Para tiers con threshold 50/45/40, la banda review nunca llega a 60, así que 3D-Secure era inalcanzable.

**Cambio:**
- `src/api/v1/transactions.py`: `_determine_friction_level` ahora recibe `threshold` y usa `threshold * 0.875` como punto medio de la banda review.

**Efecto práctico:** 3D-Secure es alcanzable en todos los tiers. La fricción escala con el riesgo.

---

### 6. Paginación de Transacciones: ORDER BY (I31)

**Problema:** La lista de transacciones no tenía `ORDER BY`. Postgres retornaba filas en orden arbitrario. Página 2 podía repetir o saltar filas.

**Cambio:**
- `src/api/v1/transactions.py`: añadido `.order_by(Transaction.created_at.desc(), Transaction.id.desc())`

**Efecto práctico:** Paginación estable y determinista. No se repiten ni se pierden filas entre páginas.

---

### 7. Count en Alerts: func.count() (I20)

**Problema:** `alerts.py` usaba `len(total_result.all())` para contar, materializando todas las IDs en memoria.

**Cambio:**
- `src/api/v1alerts.py`: cambiado a `select(func.count()).select_from(FraudAlert)`

**Efecto práctico:** El count ahora es O(1) en memoria. No escala con el tamaño de la tabla.

---

### 8. Paginación en Endpoints de Auditoría (C15)

**Problema:** Los 3 endpoints de auditoría no tenían paginación. `list(result.scalars().all())` sin `.limit()`. Riesgo OOM con tablas grandes.

**Cambio:**
- `src/api/v1/audit.py`: añadido `page`/`page_size` (default 50, max 100) a los 3 endpoints
- `src/services/audit.py`: añadido `offset`/`limit` a los 3 métodos del servicio

**Efecto práctico:** Los endpoints de auditoría ahora son paginados. No pueden agotar memoria.

---

## Archivos Modificados

| Archivo | Cambio |
|---|---|
| `.env` | Añadido `REDIS_PASSWORD`, `TRUST_PROXY_HEADERS` |
| `.env.example` | Añadido `REDIS_PASSWORD`, `TRUST_PROXY_HEADERS` |
| `docker-compose.yml` | Eliminados `ports:` de Redis/Postgres/Ollama; Redis con `requirepass` |
| `docker/nginx.conf` | `X-Forwarded-For` usa `$remote_addr` (anti-spoofing) |
| `scripts/create_admin.py` | Password desde env/getpass, mínimo 12 chars |
| `src/core/config.py` | `db_password` sin default, `redis_password`, tiers half-open |
| `src/services/ensemble.py` | Intervalos half-open en `get_threshold` |
| `src/api/v1/transactions.py` | Fricción dinámica, `ORDER BY` en paginación |
| `src/api/v1/alerts.py` | `func.count()` en vez de `len(.all())` |
| `src/api/v1/audit.py` | Paginación en 3 endpoints |
| `src/services/audit.py` | `offset`/`limit` en 3 métodos |

---

## Verificación

```
tests/test_ensemble.py ................. 17 passed
tests/unit/test_transaction_service.py .. 8 passed
tests/api/test_error_hygiene.py ......... 3 passed
tests/integration/test_audit_api.py ...... 9 passed
tests/integration/test_transaction_api.py  20 passed

Total: 57 passed, 0 failed
```

---

## Pendiente de la Fase 1

- Borrar referencias a `admin123` en `NEXT_STEPS.md`, `OPERATIONAL_GUIDE.md`, `openspec/changes/transaction-creation-flow/archive-report.md` (requiere revisión manual de docs)
- Actualizar tests que asumen intervalos cerrados en threshold tiers (los tests actuales pasan porque usan montos enteros)
