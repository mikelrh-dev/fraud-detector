# 🛡️ Plan de Desarrollo: Fraud Detector Hybrid + ML

> **Proyecto:** Sistema híbrido de detección de fraude con motor de reglas + ML + LLM local
> **Duración estimada:** 28 días (4 semanas)
> **Stack:** FastAPI + PostgreSQL + Redis + Ollama + scikit-learn + React
> **Coste:** 0€ (Oracle Cloud Always Free + modelos open source)

---

## 📐 Arquitectura Final

```
Transacción entrante
       ↓
┌─────────────────────────────────────────┐
│  CAPA 1: Motor de Reglas (determinista) │
│  - Reglas de negocio (if/then)          │
│  - Límites, geolocalización, frecuencia │
│  → Score parcial + alertas inmediatas   │
└─────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────┐
│  CAPA 2: ML Model (estadístico)         │
│  - XGBoost: clasificación supervisada   │
│  - Isolation Forest: detección anomalías│
│  - Feature engineering (50+ features)   │
│  → Score ML + probabilidad fraude       │
└─────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────┐
│  CAPA 3: LLM Worker (explicativo)       │
│  - Ollama (Llama 3.2 3B)                │
│  - Genera informe explicativo           │
│  - Contexto: score + features + reglas  │
│  → Informe en lenguaje natural          │
└─────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────┐
│  Dashboard (React)                      │
│  - Visualización en tiempo real         │
│  - Métricas, gráficos, alertas          │
│  - Revisión de informes LLM             │
└─────────────────────────────────────────┘
```

---

## 🎯 Fases de Desarrollo

### **FASE 1: API + Base de Datos + Motor de Reglas** (días 1-6)

**Objetivo:** Backend funcional con motor de reglas determinista.

#### Día 1-2: Setup y modelos de datos
- [ ] Configurar entorno de desarrollo (venv, pre-commit, ruff)
- [ ] Modelo SQLAlchemy: `Transaction`
  - Campos: id, amount, currency, timestamp, merchant_id, merchant_category,
    card_country, ip_country, device_id, user_id, status, risk_score, metadata
- [ ] Modelo SQLAlchemy: `FraudAlert`
  - Campos: id, transaction_id, alert_type, severity, score, description, created_at
- [ ] Modelo SQLAlchemy: `MLModel` (metadata de modelos entrenados)
  - Campos: id, name, version, type, accuracy, f1_score, trained_at, is_active
- [ ] Migraciones Alembic
- [ ] Tests unitarios de modelos

#### Día 3-4: Motor de reglas
- [ ] `src/services/rules_engine.py`
  - Regla 1: Transacción > 10.000€ → score +30
  - Regla 2: País diferente al habitual → score +25
  - Regla 3: Múltiples transacciones en < 1h → score +20
  - Regla 4: Merchant en lista negra → score +40
  - Regla 5: Hora inusual (3-6 AM) → score +10
  - Regla 6: Dispositivo nuevo → score +15
- [ ] Sistema de pesos configurables (YAML/JSON)
- [ ] `src/services/transaction_service.py`
  - POST /api/v1/transactions → evalúa reglas → guarda → retorna score
  - GET /api/v1/transactions/{id} → detalle + alertas
  - GET /api/v1/transactions → lista con filtros
- [ ] Tests de integración del motor de reglas

#### Día 5-6: API endpoints + autenticación
- [ ] Endpoints CRUD completos
- [ ] Autenticación JWT (opcional, puede ser API key)
- [ ] Rate limiting (Redis)
- [ ] Documentación OpenAPI completa
- [ ] Tests E2E con pytest + httpx

**Entregable:** API funcional que evalúa transacciones con motor de reglas.

---

### **FASE 2: ML — Modelos de Clasificación y Anomalías** (días 7-14) ⭐ NUEVO

**Objetivo:** Entrenar modelos de ML con datos sintéticos y integrarlos en el pipeline.

#### Día 7-8: Generación de datos sintéticos
- [ ] `src/ml/data_generator.py`
  - Generar 100.000 transacciones sintéticas
  - Distribución: 95% legítimas, 5% fraudulentas
  - Features: amount, hour, country_match, device_age, merchant_risk, etc.
  - Patrones de fraude:
    - Transacciones grandes en países no habituales
    - Múltiples transacciones pequeñas en corto tiempo
    - Compras en merchants de alto riesgo
    - Uso de dispositivos nuevos con montos altos
- [ ] Guardar dataset en `data/synthetic_transactions.csv`
- [ ] Split train/test (80/20)

#### Día 9-10: Feature engineering
- [ ] `src/ml/feature_engineering.py`
  - Features temporales: hora del día, día de semana, es_fin_de_semana
  - Features de agregación: promedio de transacciones últimas 24h, 7d, 30d
  - Features de distancia: distancia entre país IP y país tarjeta
  - Features de dispositivo: edad del dispositivo, número de dispositivos del usuario
  - Features de merchant: riesgo del merchant, categoría, historial
  - Normalización (StandardScaler)
  - Encoding de variables categóricas (LabelEncoder, OneHotEncoder)
- [ ] Pipeline de preprocessing (scikit-learn Pipeline)

#### Día 11-12: Entrenamiento de modelos
- [ ] `src/ml/models/classifier.py`
  - **XGBoost Classifier** (modelo principal)
    - Hiperparámetros: max_depth=6, learning_rate=0.1, n_estimators=200
    - Validación cruzada (5-fold)
    - Métricas: accuracy, precision, recall, F1, AUC-ROC
    - Guardar modelo: `models/xgboost_fraud_v1.pkl`
  - **Random Forest** (baseline)
    - Comparación con XGBoost
- [ ] `src/ml/models/anomaly_detector.py`
  - **Isolation Forest** (detección de anomalías)
    - Contamination: 0.05 (esperamos 5% de fraude)
    - n_estimators: 100
    - Guardar modelo: `models/isolation_forest_v1.pkl`
- [ ] `src/ml/model_trainer.py`
  - Script de entrenamiento completo
  - Logging de métricas (MLflow opcional)
  - Guardar modelos + metadata en BD

#### Día 13-14: Integración en el pipeline
- [ ] `src/services/ml_service.py`
  - Cargar modelos al iniciar la API
  - Método `predict(transaction)` → retorna score ML + probabilidad
  - Método `detect_anomaly(transaction)` → retorna score anomalía
  - Combinar scores: `final_score = 0.4 * rules + 0.4 * xgboost + 0.2 * isolation`
- [ ] Endpoint GET /api/v1/ml/status → estado de modelos cargados
- [ ] Endpoint POST /api/v1/ml/retrain → reentrenamiento manual (admin)
- [ ] Tests de predicción con datos sintéticos

**Entregable:** Modelos ML entrenados, integrados en el pipeline de evaluación.

---

### **FASE 3: LLM Worker — Informes Explicativos** (días 15-19)

**Objetivo:** Usar Ollama para generar informes en lenguaje natural.

#### Día 15-16: Setup Ollama + prompts
- [ ] Docker Compose: servicio Ollama (ya incluido)
- [ ] Pull del modelo: `ollama pull llama3.2:3b`
- [ ] `src/workers/llm_worker.py`
  - Conectar con Ollama API (http://localhost:11434)
  - Template de prompt:
    ```
    Eres un analista de fraude financiero. Genera un informe conciso sobre esta transacción.

    Datos:
    - Monto: {amount}€
    - Merchant: {merchant_name} ({merchant_category})
    - País: {country}
    - Hora: {timestamp}
    - Score reglas: {rules_score}/100
    - Score ML: {ml_score}/100
    - Score final: {final_score}/100
    - Alertas: {alerts}

    Genera un informe de 3-4 párrafos explicando:
    1. Por qué esta transacción es sospechosa (o no)
    2. Qué factores contribuyen al riesgo
    3. Recomendación (aprobar, revisar manualmente, bloquear)
    ```
  - Timeout: 30s
  - Retry logic (3 intentos)

#### Día 17-18: Cola de tareas asíncrona
- [ ] Redis Queue (RQ) o Celery
  - Cola: `fraud_reports`
  - Worker: procesa solicitudes de informes LLM
- [ ] `src/workers/tasks.py`
  - Task: `generate_fraud_report(transaction_id)`
  - Guarda informe en BD (campo `llm_report` en Transaction)
- [ ] Endpoint POST /api/v1/transactions/{id}/report → encola generación
- [ ] Endpoint GET /api/v1/transactions/{id}/report → retorna informe (si existe)

#### Día 19: Integración completa
- [ ] Al crear transacción con score > 70 → encola generación de informe automáticamente
- [ ] Tests de integración LLM (mock de Ollama para tests rápidos)

**Entregable:** Informes LLM generados automáticamente para transacciones de alto riesgo.

---

### **FASE 4: Dashboard React** (días 20-24)

**Objetivo:** Interfaz visual para revisar transacciones, alertas e informes.

#### Día 20-21: Setup React + layout
- [ ] Vite + React + TypeScript
- [ ] Tailwind CSS + shadcn/ui
- [ ] Layout: sidebar + main content
- [ ] Rutas:
  - `/` → Dashboard (métricas generales)
  - `/transactions` → Lista de transacciones
  - `/transactions/:id` → Detalle + informe LLM
  - `/alerts` → Alertas de fraude
  - `/ml` → Estado de modelos ML

#### Día 22-23: Componentes principales
- [ ] Tabla de transacciones (paginación, filtros, búsqueda)
- [ ] Tarjetas de métricas:
  - Total transacciones hoy
  - Transacciones fraudulentas detectadas
  - Score promedio
  - Alertas activas
- [ ] Gráficos (Recharts):
  - Transacciones por hora
  - Distribución de scores
  - Tendencia de fraude (últimos 7 días)
- [ ] Detalle de transacción:
  - Info básica (monto, merchant, país)
  - Scores (reglas, ML, final)
  - Alertas activadas
  - Informe LLM (si existe)
  - Botones: Aprobar / Rechazar / Marcar para revisión

#### Día 24: Conexión con API
- [ ] React Query (TanStack Query) para fetching
- [ ] WebSocket (opcional) para actualizaciones en tiempo real
- [ ] Auth (JWT o API key)

**Entregable:** Dashboard funcional conectado a la API.

---

### **FASE 5: Pulido, Deploy y Documentación** (días 25-28)

#### Día 25: Testing completo
- [ ] Tests unitarios: 80%+ cobertura
- [ ] Tests de integración
- [ ] Tests E2E (Playwright opcional)
- [ ] Load testing (Locust: 100 req/s)

#### Día 26: Optimización
- [ ] Caché Redis para queries frecuentes
- [ ] Índices en BD (transaction_id, user_id, timestamp)
- [ ] Compresión de respuestas API (gzip)
- [ ] Rate limiting por IP

#### Día 27: Deploy en VPS
- [ ] Docker Compose production (ya configurado)
- [ ] Nginx reverse proxy (HTTPS con Let's Encrypt)
- [ ] Variables de entorno production
- [ ] Backup automático de BD (cron diario)
- [ ] Monitoreo básico (logs, uptime)

#### Día 28: Documentación + Demo
- [ ] README.md completo (instalación, uso, arquitectura)
- [ ] Video demo (2-3 min):
  - Crear transacción legítima → score bajo
  - Crear transacción fraudulenta → score alto + alerta + informe LLM
  - Mostrar dashboard con métricas
  - Mostrar modelo ML entrenado
- [ ] Subir a YouTube (no listado)
- [ ] Documentar decisiones técnicas (ADRs)

**Entregable:** Proyecto completo, desplegado, documentado, con video demo.

---

## 📊 Resumen de Tecnologías

| Capa | Tecnología | Función |
|---|---|---|
| **API** | FastAPI + Python 3.11 | Endpoints REST |
| **BD** | PostgreSQL 16 (async) | Almacenamiento transacciones |
| **Cache** | Redis 7 | Cola de tareas, caché |
| **ML** | scikit-learn + XGBoost | Clasificación + anomalías |
| **LLM** | Ollama (Llama 3.2 3B) | Informes explicativos |
| **Frontend** | React + TypeScript + Vite | Dashboard |
| **Contenedores** | Docker + docker-compose | Deploy |
| **Proxy** | Nginx | HTTPS, reverse proxy |

---

## 🎯 Criterios de Éxito

- ✅ API responde en < 200ms (sin LLM)
- ✅ Motor de reglas detecta 100% de patrones definidos
- ✅ Modelo XGBoost alcanza F1 > 0.85 en test set
- ✅ Isolation Forest detecta anomalías no cubiertas por reglas
- ✅ LLM genera informes en < 30s
- ✅ Dashboard carga en < 2s
- ✅ Sistema soporta 100 transacciones/segundo
- ✅ Cobertura de tests > 80%

---

## 🚀 Próximos Pasos

1. **Hoy:** Crear rama `feat/api-rules` y empezar Fase 1
2. **Día 7:** Crear rama `feat/ml-models` y empezar Fase 2
3. **Día 15:** Crear rama `feat/llm-worker` y empezar Fase 3
4. **Día 20:** Crear rama `feat/dashboard` y empezar Fase 4
5. **Día 25:** Crear rama `release/v1.0` y empezar Fase 5

---

*Plan creado por OWL (Hermes) + Mikel — 2026-06-11*
*Actualizado con ML incluido*
