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
- PostgreSQL (puerto 5432)
- Redis (puerto 6379) con persistencia AOF + RDB
- Ollama (puerto 11434) — modelo LLM
- API (puerto 8000) — FastAPI
- 3 Workers: llm-worker, shap-worker, embedding-worker
- Frontend (puerto 3000) — React

### 2.2 Verificar que todos los servicios están healthy
```bash
docker compose ps

# Debería ver algo como:
# NAME                  STATUS
# postgres              Up (healthy)
# redis                 Up (healthy)
# ollama                Up
# api                   Up (healthy)
# llm-worker            Up
# shap-worker           Up
# embedding-worker      Up
# frontend              Up
```

### 2.3 Esperar a que Ollama descarue el modelo (puede tardar 5-10 min)
```bash
# Ver logs de ollama
docker compose logs ollama

# Debería terminar con algo como:
# Successfully loaded model "mistral"
```

---

## FASE 3: VERIFICAR CONEXIONES (5 minutos)

### 3.1 Comprobar que la API está viva
```bash
curl http://localhost:8000/health
# Debería devolver: {"status":"ok"}
```

### 3.2 Comprobar que Redis está alive
```bash
redis-cli ping
# Debería devolver: PONG

# Verificar persistencia
redis-cli CONFIG GET appendonly
# Debería mostrar: appendonly yes
```

### 3.3 Comprobar que PostgreSQL está alive
```bash
psql -h localhost -U fraud -d fraud_detector -c "SELECT 1"
# Debería devolver: 1
```

### 3.4 Verificar que Ollama tiene el modelo
```bash
curl http://localhost:11434/api/tags
# Debería mostrar: "mistral" en la lista
```

---

## FASE 4: INICIALIZAR BASE DE DATOS (5 minutos)

### 4.1 Correr migraciones de Alembic
```bash
docker compose exec api alembic upgrade head
# Debería completar sin errores
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
curl -X POST http://localhost:8000/api/v1/transactions \
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
curl -X POST http://localhost:8000/api/v1/transactions \
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
docker compose logs llm-worker | tail -20

# Debería mostrar: "SHAP computed for transaction", "Embedding processed", "LLM report"
```

### 5.4 Verificar Redis Streams
```bash
# Ver eventos en cada stream
redis-cli XLEN fraud:llm
redis-cli XLEN fraud:shap
redis-cli XLEN fraud:embeddings

# Ver consumer groups
redis-cli XINFO GROUPS fraud:llm

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
docker compose logs -f shap-worker embedding-worker llm-worker

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
# 2. Puerto 8000 ya está en uso → cambiar puerto en docker-compose.yml
# 3. Error de importación → verificar requirements.txt
```

### Si Redis no persiste
```bash
# Verificar configuración
redis-cli CONFIG GET appendonly
redis-cli CONFIG GET save

# Si no está activado:
redis-cli CONFIG SET appendonly yes
redis-cli CONFIG REWRITE  # Persistir cambios
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

# Reiniciar limpio
docker compose up -d
docker compose exec api alembic upgrade head
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
- [ ] `curl http://localhost:8000/health` → OK
- [ ] `redis-cli ping` → PONG
- [ ] Alembic migrations corrieron
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

# 4. Verificar
docker compose ps
curl http://localhost:8000/health

# 5. Ver logs
docker compose logs -f
```

---

**SISTEMA LISTO PARA OPERACIÓN.** 🚀
