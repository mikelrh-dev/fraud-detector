# ANÁLISIS RIGUROSO: 3 RIESGOS OCULTOS DE PRODUCCIÓN

Revisión línea-por-línea de 3 riesgos operacionales que no estaban en el análisis anterior.

---

## 1. 🔒 LOCK GLOBAL EN GRAFO: CUELLO DE BOTELLA DE CONCURRENCIA

### RIESGO IDENTIFICADO: ⚠️ MEDIO (Latencia bajo carga)

#### Estado Actual

```python
# src/services/graph_service.py (línea 40)
class FraudGraphService:
    def __init__(self):
        self.lock = asyncio.Lock()  # ← LOCK GLOBAL
    
    # Línea 63: ADD_TRANSACTION
    async def add_transaction(self, ...):
        async with self.lock:  # ← BLOQUEA TODO
            self.graph.add_node(...)
            self.graph.add_edge(...)
            # Línea 86-94: Pruning
            if self.graph.number_of_nodes() % 1000 == 0:
                await self._prune_old_nodes()  # ← PUEDE DURAR SEGUNDOS
```

#### El Problema

**Scenario 1: Transacciones normales (rápido)**
- `add_transaction()` toma ~1ms (add 3 nodes + 2 edges)
- Lock adquirido: 1ms
- Lock liberado: OK, próxima transacción entra

**Scenario 2: Pruning (LENTO) - cada 1000 transacciones**
- `_prune_old_nodes()` iterates ~54M nodos (en 6 meses)
- Operación: O(N) → 100ms-500ms
- Lock adquirido: 500ms
- **Durante esos 500ms: TODAS las transacciones entrantes ESPERAN**
- P99 latencia: 500ms → usuario ve timeout

```
Transacción 1: Acquire lock → add_node → add_edge → Release (1ms) ✓
Transacción 2: Acquire lock → add_node → add_edge → Release (1ms) ✓
...
Transacción 1000: Acquire lock → prune (500ms) → Release (500ms) ✗ CUELLO DE BOTELLA
Transacción 1001: WAIT → WAIT → WAIT (espera 500ms) ✗ LATENCIA ALTA
Transacción 1002: WAIT → WAIT → WAIT (espera 500ms) ✗ LATENCIA ALTA
```

#### Verificación en el Código

- `src/services/graph_service.py`, línea 40: Un **único** `asyncio.Lock()`
- Línea 63: Usado en `add_transaction()` (lectura + escritura)
- Línea 109: Usado en `get_graph_features()` (solo lectura)
- Línea 132: Usado en `get_stats()` (solo lectura)
- Línea 147-165: `_prune_old_nodes()` **dentro del lock** (muy costoso)

#### Impacto en Producción

- **Probabilidad:** MEDIA (ocurre cada 1000 transacciones)
- **Severidad:** MEDIA (P99 latencia ~500ms, user timeout)
- **Síntomas:** Picos de latencia cada 1000 transacciones, algunos requests timeout

---

### RECOMENDACIÓN: OPTIMIZAR (NO crítico ahora, pero documenta para futuro)

**Solución 1: Mover pruning fuera del lock (CORTO PLAZO)**
```python
# En lugar de prunar dentro del lock cada 1000 adds:
# Mover a un background task que corre cada 12 horas
async def _background_pruning_loop(self):
    while True:
        await asyncio.sleep(43200)  # 12 horas
        async with self.lock:
            await self._prune_old_nodes()
```

**Solución 2: Read-Write Lock (MEDIO PLAZO)**
```python
# En lugar de un lock global, usar RwLock
from asyncio_contextmanager import asynccontextmanager

class FraudGraphService:
    def __init__(self):
        self.read_lock = asyncio.Semaphore(100)  # 100 lectores simultáneos
        self.write_lock = asyncio.Lock()
    
    async def get_graph_features(self, user_id):
        async with self.read_lock:
            # Múltiples lectores pueden correr en paralelo
            ...
    
    async def add_transaction(self, ...):
        async with self.write_lock:
            # Solo un escritor a la vez
            ...
```

**Solución 3: Grafo paralelo (LARGO PLAZO)**
```python
# Mantener 2 grafos:
# - self.graph_current (lectura activa)
# - self.graph_next (escritura/pruning)
# Intercambiarlos atómicamente cada 12 horas
```

**STATUS ACTUAL:** ⚠️ **ACEPTABLE**
- Lock simple es suficiente para volumen actual (~1000 txn/hora)
- Pero documentar para escalar a futura

---

## 2. 🔥 REDIS PERSISTENCE: PÉRDIDA DE EVENTOS

### RIESGO IDENTIFICADO: ⚠️ CRÍTICO (Data loss)

#### Estado Actual

```yaml
# docker-compose.yml (línea 21-34)
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  # ← NO HAY CONFIGURACIÓN DE PERSISTENCIA
  # ← NO HAY appendonly yes (AOF)
  # ← NO HAY save RDB intervals
```

#### El Problema

**Scenario 1: Redis reinicia sin persistencia**
- API publica 1000 eventos a `fraud:llm` stream
- Eventos esperan en Redis siendo procesados por llm_worker
- **Docker container de Redis CRASHEA** (update, restart, oom-kill)
- Redis reinicia
- **TODOS los 1000 eventos desaparecen** (nunca fueron persistidos)
- LLM reports nunca se generan
- **Data loss silencioso**

**Redis sin AOF = memoria volátil**
```
API → Redis (en RAM)
      ↓
      Si Redis muere → TODO perdido

API → Redis (con AOF en disk)
      ↓
      Si Redis muere → AOF recupera from disk
```

#### Verificación en el Código

- `docker-compose.yml`, línea 22: `image: redis:7-alpine`
- Línea 26: `volumes: redis_data:/data` (sin configuración)
- **NO HAY** `redis.conf` con `appendonly yes`
- **NO HAY** RDB snapshots configurados

**En producción: Redis es tu Message Broker**
- `fraud:llm` stream: LLM reports esperando
- `fraud:shap` stream: SHAP attributions esperando
- `fraud:embeddings` stream: Embedding results esperando
- **Si Redis muere: 3 streams perdidos**

#### Impacto en Producción

- **Probabilidad:** MEDIA (container updates 1-2x/mes)
- **Severidad:** CRÍTICA (data loss de reportes/explanations)
- **Síntomas:** Eventos no procesados después de restart de Redis

---

### RECOMENDACIÓN: ACTIVAR PERSISTENCIA (CRÍTICO - FIX INMEDIATO)

**Solución: Activar AOF (Append-Only File)**
```yaml
# docker-compose.yml
redis:
  image: redis:7-alpine
  command: redis-server --appendonly yes --appendfsync everysec
  volumes:
    - redis_data:/data
  # ← AOF guardará CADA evento a disk
```

**Alternativa: RDB snapshots (menos safe pero más rápido)**
```yaml
redis:
  image: redis:7-alpine
  command: redis-server --save 60 10000  # Save every 60s if 10K keys changed
  volumes:
    - redis_data:/data
```

**MEJOR PRÁCTICA: Ambas (AOF + RDB)**
```yaml
redis:
  image: redis:7-alpine
  command: redis-server --appendonly yes --appendfsync everysec --save 60 10000
  volumes:
    - redis_data:/data
```

---

## 3. 💾 MEMORY LIMITS EN DOCKER: OOM KILLER

### RIESGO IDENTIFICADO: ⚠️ ALTO (Worker crash/slowdown)

#### Estado Actual

```yaml
# docker-compose.yml
api:
  build: ...
  # ← NO HAY mem_limit
  # ← NO HAY memswap_limit

worker:
  build: ...
  # ← NO HAY mem_limit

shap-worker:
  build: ...
  # ← NO HAY mem_limit

embedding-worker:
  build: ...
  # ← NO HAY mem_limit
  # ← SentenceTransformer carga modelos → 300MB+
```

#### El Problema

**Scenario 1: Embedding-worker sin límite**
- SentenceTransformer carga modelo `all-MiniLM-L6-v2` → 100-150MB
- PyTorch loads CUDA kernels → +50-100MB
- Process requests → 300-500MB por worker
- VPS tiene 23GB (54% usado por API + otros servicios)
- **Embedding worker puede crecer sin límite → 5GB+**
- Si se suma a otros workers → total 15GB+
- **PostgreSQL queda sin RAM → queries slow → crashes**

**Scenario 2: Native memory leak en PyTorch**
- Rare pero possible: tensors no se liberan correctamente
- Embedding worker crece de 300MB → 1GB → 3GB → 10GB
- VPS RAM agotada
- **Kernel OOM Killer mata los procesos** (unpredictable orden)
- PostgreSQL o API puede ser asesinado
- **Sistema inestable**

#### Verificación en el Código

- `docker-compose.yml`, línea 52-80 (`api`): **SIN mem_limit**
- Línea 82-106 (`worker`): **SIN mem_limit**
- Línea 108-129 (`shap-worker`): **SIN mem_limit**
- Línea 131-148 (`embedding-worker`): **SIN mem_limit**

**Comparación: VPS actual**
- Total RAM: 23GB
- API (FastAPI): ~500MB
- PostgreSQL: ~2GB
- Redis: ~100MB
- Ollama (LLM): ~8GB
- **Libre: ~12GB**
- **Sin límites: Workers pueden comerse todo**

#### Impacto en Producción

- **Probabilidad:** MEDIA (memory leaks rare pero posibles)
- **Severidad:** ALTA (database slowdown/crash)
- **Síntomas:** Workers consumen RAM infinitamente, DB queries slow

---

### RECOMENDACIÓN: ESTABLECER LÍMITES (IMPORTANT - FIX EN PRÓXIMA RELEASE)

**Solución: Agregar mem_limit a cada worker**
```yaml
api:
  mem_limit: 2g  # API no debería exceder 2GB
  memswap_limit: 2.5g  # Allow 500MB swap
  
embedding-worker:
  mem_limit: 1g  # Sentence-Transformers ~300-500MB
  memswap_limit: 1.2g
  
shap-worker:
  mem_limit: 800m  # SHAP cálculos ~300-500MB
  memswap_limit: 1g
  
worker:  # llm_worker
  mem_limit: 500m  # Light processing (just queue reading)
  memswap_limit: 600m
```

**Recomendación de límites por worker:**
| Worker | Base | Peak | Limit | Swap |
|--------|------|------|-------|------|
| API | 300MB | 600MB | **2GB** | 2.5GB |
| embedding-worker | 300MB | 800MB | **1GB** | 1.2GB |
| shap-worker | 200MB | 600MB | **800M** | 1GB |
| worker (LLM) | 100MB | 300MB | **500M** | 600M |

**Benefit:**
- Si embedding-worker crece anormalmente → Docker mata solo ese container
- PostgreSQL permanece vivo
- Sistema recoverable

---

## RESUMEN DE RIESGOS OCULTOS

| Riesgo | Severidad | Probabilidad | Status | Fix |
|--------|-----------|--------------|--------|-----|
| Lock global (graph) | MEDIA | MEDIA | ⚠️ DOCUMENTAR | Background pruning (FUTURO) |
| Redis persistence | CRÍTICA | MEDIA | 🔴 **FIX AHORA** | Activar AOF |
| Memory limits | ALTA | MEDIA | 🟠 FIX PRÓXIMO | mem_limit en workers |

---

## RECOMENDACIÓN INMEDIATA

**CRÍTICO (antes de deploy a VPS):**
1. ✅ Activar Redis AOF (5 minutos)
2. ✅ Agregar mem_limit a workers (5 minutos)

**IMPORTANTE (próxima release):**
3. ⚠️ Documentar Read-Write Lock pattern para grafo (future scaling)

**Commits necesarios:**
- docker-compose.yml: AOF + mem_limit
- DOCUMENTATION: Lock pattern para futuro

---

## PREGUNTAS ANTES DE PROCEDER

1. **Lock Global:** ¿Crees que el scenario de 1000 transacciones + pruning es un problema ahora? (Volumen: ~1000/hora = 1 pruning cada 1 hora)
2. **Redis Persistence:** ¿Querés AOF (safe pero lento) o RDB (rápido pero puede perder últimos segundos)?
3. **Memory Limits:** ¿Aplicamos los límites que propuse o querés otros números?
