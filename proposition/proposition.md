A veces la interfaz no renderiza correctamente el botón de descarga del archivo generado. ¡No te preocupes!

Como alternativa infalible, te dejo aquí mismo el contenido exacto de los 4 archivos Markdown. Solo tienes que copiarlos y pasárselos directamente a tu agente (puedes pegarlos en su chat o guardarlos tú mismo como `.md`).

Aquí tienes los 4 planes de acción:

### Archivo 1: `01_graph_analytics_networkx.md`

```markdown
# Mejora 1: Graph Analytics con NetworkX para Detección de Mulas

## 🎯 Objetivo
Identificar "anillos de fraude" y cuentas mula implementando un grafo en memoria. El modelo tabular (XGBoost) evalúa transacciones individuales, pero NetworkX evaluará si el usuario o la tarjeta de crédito están a $\leq$ 2 saltos de un defraudador conocido.

## 🛠️ Stack & Dificultad
*   **Librería:** `NetworkX` (Python puro, consumo de RAM mínimo).
*   **Dificultad:** Media.
*   **Coste:** 0€.

## 📋 Instrucciones Específicas para el Agente (Aider/Cline)

1.  **Instalar Dependencia:** Añadir `networkx>=3.0` a `requirements.txt`.
2.  **Servicio de Grafo (`src/services/graph_service.py`):**
    *   Crear una clase `FraudGraphService` (Singleton o instanciada al inicio).
    *   Mantener un objeto `nx.Graph()` en memoria.
    *   Implementar método `add_transaction(sender_id, receiver_id, card_id, is_fraud=False)`:
        *   Crear aristas entre `sender_id` y `receiver_id`.
        *   Crear aristas entre `sender_id` y `card_id`.
    *   Implementar método `get_graph_features(user_id)` que devuelva un dict:
        *   `degree_centrality`: Número de conexiones del nodo.
        *   `shortest_path_to_fraud`: Calcular la distancia al nodo marcado como fraude más cercano. Retornar `999` si no hay ruta.
        *   `is_near_fraud`: `1` si `shortest_path_to_fraud <= 2`, si no `0`.
3.  **Integración en `src/api/v1/transactions.py`:**
    *   Al recibir un `POST /api/v1/transactions`, llamar a `get_graph_features(user_id)`.
    *   Pasar estas *features* adicionales al Feature Engine y, opcionalmente, inyectarlas en el payload que evalúa el Rule Engine o XGBoost.
    *   Tras resolver la transacción, llamar a `add_transaction(...)` para actualizar el grafo.

```

---

### Archivo 2: `02_mlops_data_drift.md`

```markdown
# Mejora 2: MLOps Data Drift con Evidently AI

## 🎯 Objetivo
Detectar *Concept Drift* o *Data Drift* en producción. Si los patrones de fraude cambian (ej. los estafadores empiezan a enviar $5,000 en vez de $100), el sistema debe alertar que el modelo XGBoost se está volviendo obsoleto.

## 🛠️ Stack & Dificultad
*   **Librería:** `evidently` (Reportes estadísticos).
*   **Dificultad:** Baja.
*   **Coste:** 0€.

## 📋 Instrucciones Específicas para el Agente (Aider/Cline)

1.  **Instalar Dependencia:** Añadir `evidently` a `requirements.txt`.
2.  **Servicio de Monitorización (`src/services/drift_service.py`):**
    *   Crear una clase `DataDriftService`.
    *   Cargar en memoria un dataset pequeño de "Referencia" (ej. 500 filas representativas del CSV sintético original).
    *   Implementar un método `evaluate_drift(current_data_df)` que utilice `DataDriftPreset` de Evidently.
    *   Extraer del resultado de Evidently (en formato dict/JSON) si la distancia métrica (ej. Wasserstein) supera el umbral de alerta para columnas clave (`amount`, `velocity_1h`).
3.  **Endpoint (`src/api/v1/monitoring.py`):**
    *   Crear un nuevo endpoint `GET /api/v1/monitoring/drift`.
    *   Este endpoint consultará las últimas N transacciones de la base de datos (PostgreSQL), las convertirá a un DataFrame de Pandas, y llamará a `DataDriftService.evaluate_drift()`.
    *   Devolver un JSON resumiendo el estado del Drift: `{"drift_detected": true/false, "features_drifted": [...]}`.

```

---

### Archivo 3: `03_event_driven_redis.md`

```markdown
# Mejora 3: Arquitectura Event-Driven (Redis Streams)

## 🎯 Objetivo
Desacoplar la inferencia síncrona (<50ms) de tareas pesadas como el cálculo SHAP, registros de auditoría y generación de reportes LLM, utilizando `Redis Streams` en lugar de una pesada infraestructura de Kafka.

## 🛠️ Stack & Dificultad
*   **Librería:** `redis-py` (Comandos `XADD`, `XREADGROUP`).
*   **Dificultad:** Media.
*   **Coste:** 0€ (Usando el contenedor Redis actual).

## 📋 Instrucciones Específicas para el Agente (Aider/Cline)

1.  **Servicio Stream (`src/core/stream_publisher.py`):**
    *   Crear funciones para publicar eventos: `publish_transaction_event(tx_data: dict)`.
    *   Usar el cliente Redis de `src/core/redis.py` con el comando `XADD` para insertar en el stream `fraud_events`.
2.  **Actualizar `src/api/v1/transactions.py`:**
    *   Quitar las llamadas directas (o *BackgroundTasks* genéricas) a las funciones pesadas (auditoría, SHAP).
    *   Tras guardar en BBDD y devolver la respuesta HTTP síncrona de Scoring, llamar a `publish_transaction_event(tx_data)`.
3.  **Refactorizar Workers (`src/workers/shap_worker.py` y `llm_worker.py`):**
    *   Modificar los workers actuales para que actúen como consumidores de un *Consumer Group* de Redis.
    *   Implementar un bucle infinito que escuche con `XREADGROUP` bloqueante (`BLOCK 0`) sobre el stream `fraud_events`.
    *   Procesar el evento, realizar la tarea (SHAP/LLM) y marcar el mensaje como procesado usando `XACK`.

```

---

### Archivo 4: `04_dynamic_friction.md`

```markdown
# Mejora 4: Fricción Dinámica & Step-Up Auth

> **NOT YET BUILT / AÚN NO CONSTRUIDO.** The schema half shipped; the score-band
> routing and the modal did not. Read the status per item before acting:
>
> 1. **SHIPPED** — `ScoringResponse.friction_level: str` and `action: str | None`
>    exist in `src/schemas/scoring.py` today. They are **free-form strings, not
>    an `Enum`**, and the values are `allow | challenge | block` and
>    `block_transaction | request_3d_secure | request_sms | None`. The
>    `ALLOW / CHALLENGE_3DS / CHALLENGE_BIOMETRIC / BLOCK` enum below was
>    **proposed and not adopted** — do not "fix" the schema to match it.
> 2. **SUPERSEDED — do not implement as written.** Fixed score bands in
>    `src/services/ensemble.py` cannot work here: the threshold is tiered by
>    amount, and classification is routed on the layer scores by
>    `ScoringService._classify_routed`
>    (`src/services/scoring_service.py:139`), not on the score. Friction is
>    already derived from that classification in
>    `_determine_friction_level` (`src/api/v1/transactions.py:100-131`):
>    `fraud` -> `block`, and in the `review` band the midpoint
>    `threshold * 0.875` picks 3D Secure over SMS.
> 3. **NOT YET BUILT.** `frontend/src/components/TransactionChallengeModal.tsx`
>    does **not exist**. There is no step-up UI in this repository; the create
>    flow renders `ScoreResultCard` and a toast. The path below is a
>    description of work to do, not a file to edit.

## 🎯 Objetivo
Transformar el sistema de un modelo binario (Permitir/Bloquear) a un flujo Fintech real. Intervenir transacciones dudosas en el frontend con "Challenges" (ej. biometría, 3DS) en lugar de bloquearlas inmediatamente.

## 🛠️ Stack & Dificultad
*   **Stack:** Python (FastAPI schemas) y TypeScript (React).
*   **Dificultad:** Baja-Media.
*   **Coste:** 0€.

## 📋 Instrucciones Específicas para el Agente (Aider/Cline)

1.  **Actualizar Schemas Backend (`src/schemas/scoring.py`) — YA HECHO:**
    *   `ScoringResponse` ya incluye `friction_level: str` y `action: str | None`, como strings libres, no como `Enum`. No rehacer.
2.  **Lógica de Umbrales Backend (`src/services/ensemble.py`) — SUPERADO:**
    *   NO implementar bandas fijas de score. Ver el punto 2 del aviso: el umbral es por tramo de importe y la clasificación se enruta por capas.
3.  **Frontend Modal (`frontend/src/components/TransactionChallengeModal.tsx`) — AÚN NO CONSTRUIDO:**
    *   Crear un componente modal en React. El archivo no existe todavía.
    *   Si al crear una transacción el endpoint devuelve `friction_level: "challenge"`, no mostrar un simple *toast* de éxito.
    *   Abrir el modal simulando una petición de OTP/3D Secure o escaneo biométrico.
    *   Si el usuario "pasa" el reto simulado, la UI marca la transacción como Legítima forzando una actualización en la vista de transacciones.

```

Pásale todo esto directamente al agente y pregúntale por cuál de las mejoras prefiere empezar. ¡Ya me contarás qué te responde!