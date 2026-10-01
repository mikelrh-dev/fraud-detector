# GUÍA DE OPERACIÓN: Poner el Sistema en Marcha (Local o VPS)

---

## FASE 1: PREPARACIÓN DEL ENTORNO (10 minutos)

### 1.1 Clonar el repo (si no lo tienes)
```bash
git clone https://github.com/mikelrh-dev/fraud-detector.git
cd fraud-detector
git pull origin master  # Asegurar últimos fixes
```

### 1.2 Verificar Docker instalado
```bash
docker --version
docker compose --version
```

### 1.3 Copiar archivo .env
```bash
cp .env.example .env
# Editar si es necesario (credenciales DB, puertos, etc.)
```

**Contenido recomendado de .env:**
```env
# Database
DB_USER=fraud
DB_PASSWORD=fraud_secret
DB_NAME=fraud_detector
DB_HOST=postgres

# Redis
REDIS_URL=redis://redis:6379/0

# Ollama (LLM)
OLLAMA_HOST=http://ollama:11434

# API
API_PORT=8000
LOG_LEVEL=INFO
```

---

## FASE 2: INICIAR SERVICIOS (5-10 minutos)

### 2.1 Iniciar todos los contenedores
```bash
docker compose up -d
```

**Qué se inicia:**
- PostgreSQL — solo `postgres:5432` dentro de la red de compose. No publica puerto en el host.
- Redis — solo `redis:6379` dentro de la red. Con persistencia AOF + RDB.
- Ollama — solo `ollama:11434` dentro de la red. Modelo LLM.
- API — solo `api:8000` dentro de la red. Es un `expose:` interno, **no** se publica en el host (ver §3.1).
- 3 Workers: `worker` (LLM), `shap-worker`, `embedding-worker`.
  El del LLM se llama `worker` en compose; su módulo es `src.workers.llm_worker`. `docker compose logs llm-worker` falla con "no such service".
- Frontend — **único** servicio que publica un puerto en el host: `3000:80`. Es nginx, y hace de proxy hacia `api:8000`.

### 2.2 Verificar que todos los servicios están healthy
```bash
docker compose ps

# Debería ver algo como:
# NAME                  STATUS
# postgres              Up (healthy)
# redis                 Up (healthy)
# ollama                Up
# api                   Up (healthy)
# worker                Up
# shap-worker           Up
# embedding-worker      Up
# frontend              Up
```

### 2.3 Descargar el modelo de Ollama (puede tardar 5-10 min)

El healthcheck de `ollama` es `ollama list`, que pasa con cero modelos. Es
decir: **nadie descarga el modelo por ti**. Sin este paso el contenedor se
declara sano y luego todos los informes dan 404.

```bash
# Descargar el modelo (OLLAMA_MODEL en .env dice llama3.2:1b)
docker compose exec ollama ollama pull llama3.2:1b

# Ver logs de ollama
docker compose logs ollama

# Comprobar que el modelo está ahí
docker compose exec ollama ollama list
# Debería mostrar: llama3.2:1b
```

Si cambias `OLLAMA_MODEL` en `.env`, descarga ese modelo y no otro.

---

## FASE 3: VERIFICAR CONEXIONES (5 minutos)

Compose publica **un solo puerto en el host**: el `3000:80` de `frontend`, que
es nginx. La API no está publicada — `8000` es un `expose:` interno del
contenedor, así que `curl http://localhost:8000/...` desde el host recibe
conexión rehusada. Se llega a la API a través de nginx, en `:3000`. Lo que no
se publica se comprueba entrando al contenedor con `docker compose exec`.

### 3.1 Comprobar que la API está viva
```bash
curl http://localhost:3000/health
# Debería devolver: {"status":"ok"}

# Este consulta Postgres y Redis de verdad — es el mismo check que usa el
# healthcheck del contenedor `api`, y es el que detecta una DB sin migrar
curl http://localhost:3000/health/ready
```

### 3.2 Comprobar que Redis está alive
```bash
# Redis no publica puerto: hay que entrar al contenedor
docker compose exec redis redis-cli ping
# Debería devolver: PONG

# Verificar persistencia
docker compose exec redis redis-cli CONFIG GET appendonly
# Debería mostrar: appendonly yes
```

### 3.3 Comprobar que PostgreSQL está alive
```bash
# PostgreSQL tampoco publica puerto
docker compose exec postgres psql -U fraud -d fraud_detector -c "SELECT 1"
# Debería devolver: 1
```

### 3.4 Verificar que Ollama tiene el modelo
```bash
# Ollama tampoco publica puerto
docker compose exec ollama ollama list
# Debería mostrar "llama3.2:1b" en la lista
```

---

## FASE 4: INICIALIZAR BASE DE DATOS (5 minutos)

### 4.1 Las migraciones ya corrieron

No hay paso manual de Alembic. `docker/entrypoint.api.sh` corre
`alembic upgrade head` bajo `set -e` antes de levantar uvicorn, así que las
migraciones se aplican al arrancar el contenedor `api`. Correrlas a mano
ejecutaría el mismo paso dos veces; y si una migración fallara durante el
arranque, el contenedor no arrancaría en lugar de servir 500s.

Cómo comprobarlo, sin ejecutar nada:
```bash
# El log del arranque muestra el paso de migraciones
docker compose logs api | head -5
# ==> Applying database migrations
# ==> Starting API

# Y /health/ready corre SELECT 1 y PING de verdad: si faltara una tabla, falla
curl http://localhost:3000/health/ready
```

### 4.2 Crear usuario admin (opcional, para testing)
```bash
docker compose exec api python scripts/create_admin.py
# Prints a ready-to-run SQL INSERT statement
```

### 4.3 Generar datos de test (opcional, para testing)
```bash
python scripts/generate_synthetic_data.py
# Genera 50k transacciones sinteticas (~5% fraude)
```

---

## FASE 5: TESTING MANUAL (10 minutos)

### 5.1 Crear una transacción legítima
```bash
curl -X POST http://localhost:3000/api/v1/transactions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "user_id": "user123",
    "amount": 50.00,
    "currency": "USD",
    "merchant_name": "Amazon",
    "merchant_category": "retail",
    "card_last4": "4242"
  }'

# Debería devolver:
# {
#   "transaction_id": "...",
#   "classification": "legitimate",
#   "ensemble_score": 15,
#   "created_at": "2026-08-14T...",
#   "friction_level": "none"
# }
```

### 5.2 Crear una transacción sospechosa
```bash
curl -X POST http://localhost:3000/api/v1/transactions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "user_id": "user456",
    "amount": 5000.00,
    "currency": "USD",
    "merchant_name": "crypto exchange",
    "merchant_category": "crypto",
    "card_last4": "9999"
  }'

# Debería devolver:
# {
#   "transaction_id": "...",
#   "classification": "fraud",
#   "ensemble_score": 92,
#   "created_at": "2026-08-14T...",
#   "friction_level": "high",
#   "action": "block"
# }
```

### 5.3 Verificar que los workers están procesando
```bash
# Ver logs de workers
docker compose logs shap-worker | tail -20
docker compose logs embedding-worker | tail -20
docker compose logs worker | tail -20

# Debería mostrar: "SHAP computed for transaction", "Embedding processed", "LLM report"
```

### 5.4 Verificar Redis Streams
```bash
# Redis no publica puerto: hay que entrar al contenedor
docker compose exec redis redis-cli XLEN fraud:llm
docker compose exec redis redis-cli XLEN fraud:shap
docker compose exec redis redis-cli XLEN fraud:embeddings

# Ver consumer groups
docker compose exec redis redis-cli XINFO GROUPS fraud:llm

# Debería mostrar info de consumer groups activos
```

---

## FASE 6: ACCEDER AL FRONTEND (2 minutos)

### 6.1 Abrir el dashboard
```
http://localhost:3000
```

### 6.2 Login (si hay autenticación)
- User: `admin`
- Password: `admin_secret_password` (o la que generaste)

### 6.3 Ver transacciones
- Dashboard debe mostrar transacciones procesadas
- Verificar scoring, reglas disparadas, etc.

---

## FASE 7: MONITOREO (Ongoing)

### 7.1 Revisar logs en tiempo real
```bash
# Todos los servicios
docker compose logs -f

# Solo API
docker compose logs -f api

# Solo workers
docker compose logs -f shap-worker embedding-worker worker

# Solo Redis
docker compose logs -f redis
```

### 7.2 Monitorear recursos
```bash
# Ver uso de CPU, memoria, I/O
docker stats

# Debería verse algo como:
# CONTAINER          CPU %    MEM USAGE / LIMIT
# api                5%       200MB / 2GB ✓
# embedding-worker   15%      400MB / 1GB ✓
# shap-worker        8%       300MB / 800MB ✓
# redis              1%       50MB / No limit ✓
# postgres           2%       1.2GB / No limit ✓
```

### 7.3 Verificar persistencia de Redis
```bash
# Ver archivos de persistencia
docker compose exec redis ls -lh /data/

# Debería mostrar:
# -rw-r--r-- appendonly.aof (archivo que crece con cada evento)
# -rw-r--r-- dump.rdb (snapshot)
```

---

## FASE 8: TROUBLESHOOTING

### Si la API no inicia
```bash
# Ver logs detallados
docker compose logs api

# Causas comunes:
# 1. PostgreSQL no está healthy → esperar más tiempo
# 2. El puerto 3000 ya está en el host → detener lo que lo ocupe, o cambiar
#    "3000:80" en docker-compose.yml. El 8000 no puede entrar en conflicto: es
#    un expose: interno y no se publica
# 3. Error de importación → verificar requirements.txt
```

### Si Redis no persiste
```bash
# Verificar configuración (dentro del contenedor: Redis no publica puerto)
docker compose exec redis redis-cli CONFIG GET appendonly
docker compose exec redis redis-cli CONFIG GET save

# Si no está activado, hay que cambiar el `command:` del servicio redis en
# docker-compose.yml, no el Redis en caliente: docker compose up recrea el
# contenedor y perdería lo hecho con CONFIG SET.
```

### Si un worker está crasheando
```bash
# Ver logs del worker específico
docker compose logs shap-worker -f

# Reiniciar solo ese worker
docker compose restart shap-worker

# Si sigue fallando, aumentar mem_limit en docker-compose.yml
```

### Si la base de datos está corrupta
```bash
# Borrar volumen de PostgreSQL (⚠️ BORRA DATOS)
docker compose down -v

# Reiniciar limpio. No hace falta correr migraciones a mano: el entrypoint
# corre `alembic upgrade head` bajo `set -e` en cada arranque de `api`
docker compose up -d
```

---

## COMANDOS ÚTILES DE OPERACIÓN

```bash
# Parar todos los servicios (sin borrar datos)
docker compose down

# Parar y borrar TODO (⚠️ borra datos)
docker compose down -v

# Ver estado de salud
docker compose ps

# Reiniciar servicio específico
docker compose restart api

# Ver logs en tiempo real
docker compose logs -f

# Escalar workers (si tienes múltiples)
docker compose up -d --scale shap-worker=2

# Ver uso de recursos
docker stats

# Entrar en contenedor
docker compose exec api bash

# Ver configuración actual
docker compose config
```

---

## CHECKLIST DE OPERACIÓN

- [ ] Docker instalado
- [ ] `.env` configurado
- [ ] `docker compose up -d` completado
- [ ] Todos los servicios en `Up (healthy)`
- [ ] Ollama descargó modelo (~5-10 min)
- [ ] `curl http://localhost:3000/health` → OK
- [ ] `docker compose exec redis redis-cli ping` → PONG
- [ ] `curl http://localhost:3000/health/ready` → OK (Postgres y Redis de verdad)
- [ ] Alembic migrations aplicadas por el entrypoint (log: `==> Applying database migrations`)
- [ ] Transacción de prueba creada y clasificada
- [ ] Workers procesando eventos (ver logs)
- [ ] Redis Streams tienen eventos
- [ ] Frontend accesible en localhost:3000
- [ ] Memory limits respetados (docker stats)
- [ ] Redis persistencia activa (AOF + RDB)

---

## SIGUIENTE PASO: DEPLOY A VPS

Una vez verificado en local, para desplegar a VPS:

```bash
# 1. En VPS, clonar repo
git clone https://github.com/mikelrh-dev/fraud-detector.git
cd fraud-detector

# 2. Copiar .env (o crear uno nuevo)
cp .env.example .env
# Editar con credenciales de producción

# 3. Iniciar
docker compose up -d

# 4. Verificar (el único puerto publicado en el host es el 3000)
docker compose ps
curl http://localhost:3000/health

# 5. Ver logs
docker compose logs -f
```

---

**SISTEMA LISTO PARA OPERACIÓN.** 🚀
