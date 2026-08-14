# ANÁLISIS DE RIESGOS DE PRODUCCIÓN — OPCIÓN C

Revisión detallada de 4 riesgos críticos en la implementación actual.

---

## 1. 🕸️ GRAFO (NetworkX): THREAD-SAFETY & MEMORY LEAKS

### RIESGO IDENTIFICADO: ⚠️ CRÍTICO

#### 1.1 Thread-Safety (Concurrencia)

**Estado Actual:**
```python
# src/services/graph_service.py (líneas 15-27)
class FraudGraphService:
    def __init__(self):
        self.graph = nx.DiGraph()  # ← NO TIENE LOCK
        self.known_fraudsters = set()  # ← NO TIENE LOCK
```

**Cómo se llama desde FastAPI:**
```python
# src/api/v1/transactions.py (línea 91)
_graph_service = FraudGraphService()  # ← SINGLETON global

# Se usa en líneas 145, 220, 475, 498
# Cada llamada al endpoint llama a:
graph_features = _graph_service.get_graph_features(...)  # ← LECTURA sin lock
_graph_service.add_transaction(...)  # ← ESCRITURA sin lock
```

**El Problema:**
FastAPI usa `uvicorn` que corre en modo multi-worker. Cada worker es un proceso separado, PERO dentro de cada proceso hay múltiples coroutines async. Si 50 transacciones llegan simultáneamente:

```
Coroutine 1: add_transaction() → G.add_edge(user1, merchant1)
Coroutine 2: add_transaction() → G.add_edge(user2, merchant2)  # Acceso concurrente
Coroutine 3: get_graph_features() → nx.degree_centrality(G)   # Lee mientras se escribe
→ Race condition → Grafo corrupto
```

**Verificación en el código:**
- `src/services/graph_service.py`, línea 30-73: `add_transaction()` modifica `self.graph` **sin candado**
- `src/services/graph_service.py`, línea 74-146: `get_graph_features()` lee `self.graph` **sin candado**
- NetworkX en Python puro **NO es thread-safe** (no usa GIL en operaciones de grafo)

**Impacto en Producción:**
- **Probabilidad:** MEDIA (ocurre solo con alta concurrencia)
- **Severidad:** ALTA (corrupción de estado → decisiones de fraude incorrectas)
- **Síntomas:** Errores aleatorios de NetworkX, nodos/edges perdidos, shortest_path() devuelve NaN

---

#### 1.2 Memory Leak (Crecimiento Infinito)

**Estado Actual:**
```python
# src/services/graph_service.py (líneas 30-73)
def add_transaction(self, sender_id: str, receiver_id: str, ...):
    # Agrega nodos SIN LÍMITE
    self.graph.add_node(sender_id, ...)
    self.graph.add_node(receiver_id, ...)
    self.graph.add_node(card_id, ...)
    self.graph.add_edge(sender_id, receiver_id)
    self.graph.add_edge(sender_id, card_id)
    # ← No hay mecanismo de pruning
```

**El Problema:**
- Cada transacción agrega 3 nodos + 2 edges al grafo
- En 1 mes con 100K transacciones: ~300K nodos + 200K edges
- NetworkX almacena grafo en memoria RAM (no en disk)
- Sin pruning, en 6 meses: **OOM (Out of Memory)** → crash de la app

**Estimación en VPS (23GB RAM):**
- Grafo con 1M nodos: ~500MB (estimado)
- Current: 6 meses de datos = ~18M transacciones = ~54M nodos
- **Resultado: 27GB RAM requerido → SUPERA los 23GB disponibles**

**Impacto en Producción:**
- **Probabilidad:** ALTA (ocurre después de 3-6 meses)
- **Severidad:** CRÍTICA (crash del servicio)
- **Síntomas:** Consumo de RAM creciente → Killed by OOM → downtime

---

### RECOMENDACIÓN: CAMBIAR

**Soluciones necesarias:**

1. **Agregar asyncio.Lock() para thread-safety:**
   ```python
   class FraudGraphService:
       def __init__(self):
           self.graph = nx.DiGraph()
           self.lock = asyncio.Lock()  # ← AGREGAR
       
       async def add_transaction(self, ...):
           async with self.lock:  # ← Sincronizar acceso
               self.graph.add_node(...)
   ```

2. **Agregar pruning automático (cada 24h):**
   ```python
   async def prune_old_transactions(self, days_retention: int = 30):
       """Elimina nodos más antiguos que days_retention."""
       cutoff_time = now() - timedelta(days=days_retention)
       nodes_to_remove = [
           node for node in self.graph.nodes()
           if self.graph.nodes[node].get("timestamp", now()) < cutoff_time
       ]
       self.graph.remove_nodes_from(nodes_to_remove)
   ```

3. **Usar RedisGraph (producción):**
   - Reemplazar NetworkX con RedisGraph (persistencia en Redis)
   - Soporte nativo para multi-threading
   - Queries escalables

---

## 2. ⚡ REDIS STREAMS: MENSAJES FANTASMA & MEMORY BLOAT

### RIESGO IDENTIFICADO: ⚠️ ALTO

#### 2.1 Stream crecimiento infinito (MAXLEN faltante)

**Estado Actual:**
```python
# src/core/stream_publisher.py (líneas 29-59)
async def publish_event(stream_name: str, event_data: dict[str, Any]) -> str:
    message_id = await client.xadd(
        stream_name,
        {"data": json.dumps(event_with_ts)},
    )  # ← SIN MAXLEN, stream crece sin límite
```

**El Problema:**
- XADD sin MAXLEN = todos los mensajes se quedan en Redis permanentemente
- Con 100 eventos/segundo × 86400 segundos/día = 8.6M eventos/día
- Cada evento: ~500 bytes
- **1 día = 4.3GB de eventos en Redis**
- **VPS Redis: 23GB → LLENO EN 5 días**

**Verificación en el código:**
- `src/core/stream_publisher.py`, línea 49: `client.xadd()` **sin argumento MAXLEN**

**Impacto en Producción:**
- **Probabilidad:** CRÍTICA (ocurre en TODAS las ejecuciones)
- **Severidad:** CRÍTICA (Redis fills → crash)
- **Síntomas:** Redis IOPS lento → API timeouts → eventos no procesados

---

#### 2.2 Pending Entries List (PEL) acumulación

**Estado Actual:**
```python
# src/workers/shap_worker.py (líneas 116-127)
while True:
    messages = await redis_client.xreadgroup(
        GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: ">"}, count=1, block=1000
    )
    for stream_name, msg_list in messages:
        for message_id, fields in msg_list:
            try:
                success = await process_shap_message(message_data, db, shap_service)
                if success:
                    await redis_client.xack(STREAM_NAME, GROUP_NAME, message_id)
                # ← Si success=False, message queda en PEL (pending)
```

**El Problema:**
- Si `process_shap_message()` falla 3 veces → mensaje nunca se XACK
- XREADGROUP siempre devuelve ">" (nuevos), ignore los pending
- Pending messages se acumulan en PEL → Redis memoria crece
- Después de crashes: mensajes pueden quedar en PEL por HORAS
- **Sin XAUTOCLAIM: mensajes nunca se recuperan, solo se abandon**

**Verificación en el código:**
- `src/workers/shap_worker.py`, línea 117-127: **NO HAY XAUTOCLAIM para recuperar pendientes**
- `src/workers/embedding_worker.py`, línea 89-106: **MISMO PROBLEMA**
- `src/workers/llm_worker.py`: **MISMO PROBLEMA**

**Impacto en Producción:**
- **Probabilidad:** MEDIA (ocurre si hay crashes o timeout)
- **Severidad:** MEDIA (data loss de reportes/atribuciones)
- **Síntomas:** Algunas transacciones nunca reciben reports → usuario no ve explicación

---

### RECOMENDACIÓN: CAMBIAR

**Soluciones necesarias:**

1. **Agregar MAXLEN a XADD:**
   ```python
   message_id = await client.xadd(
       stream_name,
       {"data": json.dumps(event_with_ts)},
       maxlen=100000,  # ← Mantener últimos 100K eventos
       approximate=True,  # ← Aproximado (más rápido)
   )
   ```

2. **Agregar XAUTOCLAIM para recuperar pendientes:**
   ```python
   async def recover_pending_messages(self):
       """Recupera mensajes no procesados después de 5 minutos."""
       pending = await redis_client.xpending(STREAM_NAME, GROUP_NAME)
       for message_id, consumer, idle_ms, retries in pending['consumers']:
           if idle_ms > 300000:  # 5 minutos sin ACK
               recovered = await redis_client.xautoclaim(
                   STREAM_NAME, GROUP_NAME, CONSUMER_NAME, 
                   min_idle_time=300000
               )
               # Reintentar procesar
   ```

3. **Establecer máximo de reintentos:**
   ```python
   MAX_RETRIES = 3
   if retry_count >= MAX_RETRIES:
       await redis_client.xack(STREAM_NAME, GROUP_NAME, message_id)
       await send_to_dlq(message_id)  # Dead-Letter Queue
   ```

---

## 3. 📊 MLOPS (EVIDENTLY AI): BLOQUEO DEL EVENT LOOP

### RIESGO IDENTIFICADO: ⚠️ ALTO

#### 3.1 Drift evaluation bloqueando el event loop

**Estado Actual:**
```python
# src/api/v1/monitoring.py (líneas 42-99)
@router.get("/drift")
async def get_drift_status(...):
    # ... construir DataFrame ...
    
    # LÍNEA 99: BLOQUEA EL EVENT LOOP
    drift_result = _drift_service.evaluate_drift(current_data)
    # ← Evidently corre Statistics, Statistical, Hypothesis tests
    # ← Con 100 filas + 4 columnas ≈ 500ms a 2s (CPU-bound)
```

**El Problema:**
- `evaluate_drift()` llama a `Report(metrics=[DataDriftPreset()]).run()`
- Evidently calcula: Kolmogorov-Smirnov, Chi-squared, Wasserstein distance...
- Con 100 transacciones: **~500ms a 2 segundos de CPU puro**
- **Mientras corre: TODOS los otros usuarios esperan** (async event loop está bloqueado)
- Uvicorn corre en single thread por default → **GIL bloquea completamente**

**Verificación en el código:**
- `src/api/v1/monitoring.py`, línea 99: **LLAMADA SÍNCRONA a `evaluate_drift()`**
- `src/services/drift_service.py`, línea 81: `Report.run()` es CPU-bound, NO async

**Impacto en Producción:**
- **Probabilidad:** MEDIA (solo si se llama al endpoint /drift)
- **Severidad:** ALTA (todos los usuarios sufren latencia)
- **Síntomas:** P99 latencia de 2s cuando se monitorea drift, timeouts en otros endpoints

---

### RECOMENDACIÓN: CAMBIAR

**Solución necesaria:**

```python
# src/api/v1/monitoring.py (línea 99)
# ANTES:
drift_result = _drift_service.evaluate_drift(current_data)

# DESPUÉS:
drift_result = await asyncio.to_thread(
    _drift_service.evaluate_drift, 
    current_data
)  # ← Corre en ThreadPoolExecutor, no bloquea event loop
```

**Impacto:**
- Permite a FastAPI procesar otros requests mientras se calcula drift
- No afecta latencia de transacciones normales

---

## 4. 🧠 EMBEDDINGS LOCALES: CARGA REDUNDANTE DE MODELOS

### RIESGO IDENTIFICADO: ⚠️ MEDIO

#### 4.1 Modelo cargado múltiples veces desde disco

**Estado Actual:**
```python
# src/workers/embedding_worker.py (línea 34)
class EmbeddingWorker:
    def __init__(self):
        self.embedding_service = MerchantEmbeddingService()
        # ← SentenceTransformer se carga AQUÍ

# src/services/merchant_embedding_service.py (línea 38-50)
def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
    self.model = SentenceTransformer(model_name)
    # ← AQUÍ: Descarga modelo (si no existe en caché)
    # ← Larga desde: ~/.cache/huggingface/models/... (disco)
```

**El Problema:**
- Primera llamada: **Load desde disco: 3-5 segundos** (según I/O del sistema)
- `SentenceTransformer.encode()`: Uso de CUDA/CPU
- Con 10K transacciones/día: **Solo 1 carga en init(), entonces reutilización**
- Pero: Si worker reinicia = recarga desde disco

**Verificación en el código:**
- `src/workers/embedding_worker.py`, línea 31-34: **BUENO: Modelo cargado en `__init__()`**
- `src/services/merchant_embedding_service.py`, línea 44-50: **BUENO: Cached globalmente**

**Mitigación actual:**
- ✅ SentenceTransformer corre en GPU/CPU según disponibilidad
- ✅ Modelo se carga UNA VEZ en init()
- ✅ Se reutiliza en todas las iteraciones del loop

**Impacto en Producción:**
- **Probabilidad:** BAJA (modelo ya cacheado en la mayoría de casos)
- **Severidad:** BAJA (carga inicial de 5s, después cero latencia)
- **Síntomas:** Primer request lento (5s), resto normales

---

### RECOMENDACIÓN: SIN CAMBIOS INMEDIATOS

**Estado:** ACEPTABLE. El modelo ya se carga correctamente en `__init__()`.

**Mejora futura (opcional):**
```python
# Usar un warmup/preload global para asegurar cache
@app.on_event("startup")
async def warmup_embedding_model():
    service = MerchantEmbeddingService()
    service.get_embedding("amazon")  # Force load to cache
    logger.info("Embedding model warmed up")
```

---

## RESUMEN DE RECOMENDACIONES

| Riesgo | Severidad | Recomendación | Esfuerzo | Urgencia |
|--------|-----------|---------------|----------|----------|
| Graph Thread-Safety | CRÍTICA | Agregar asyncio.Lock() | 30 min | INMEDIATA |
| Graph Memory Leak | CRÍTICA | Agregar pruning cada 24h | 1 hora | INMEDIATA |
| Redis Stream MAXLEN | CRÍTICA | Agregar MAXLEN=100k a XADD | 15 min | INMEDIATA |
| Redis PEL Pending | MEDIA | Agregar XAUTOCLAIM + retry logic | 1 hora | PRÓXIMA |
| Drift Event Loop | ALTA | Usar asyncio.to_thread() | 10 min | PRÓXIMA |
| Embeddings Load | BAJA | Keepalive OK, warmup opcional | 0 min | OPCIONAL |

---

## RESUMEN EJECUTIVO

### ✅ BUENOS

1. **Embedding Worker:** Modelo cargado correctamente en init(), sin redundancia
2. **Database Connection:** AsyncSession usado correctamente (no bloquea)
3. **Error Handling:** Try-catch en todos los workers, fallback graceful

### ⚠️ CRÍTICOS (FIX ANTES DE PRODUCCIÓN)

1. **Graph NetworkX:** Sin thread-safety → race condition bajo concurrencia
2. **Graph Memory:** Sin pruning → OOM después de 3-6 meses
3. **Redis Streams:** Sin MAXLEN → fills Redis en 5 días

### 🔶 ALTOS (FIX EN PRÓXIMA RELEASE)

1. **Redis PEL:** Sin XAUTOCLAIM → mensajes perdidos si worker crash
2. **Drift Endpoint:** Calculo CPU-bound bloqueando event loop

### 🟡 BAJOS (OPCIONAL)

1. **Embeddings:** Funcionan bien, warmup es mejora cosmetica

---

## CONCLUSIÓN

**NO ESTÁ LISTO PARA PRODUCCIÓN sin fixes críticos.**

**Cambios mínimos necesarios:**
1. Graph: Agregar `asyncio.Lock()` + pruning
2. Redis: Agregar `MAXLEN` en XADD
3. Drift: Usar `asyncio.to_thread()`

**Tiempo estimado:** 2-3 horas

Después de estos cambios: **LISTO PARA PRODUCCIÓN**
