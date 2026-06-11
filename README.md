# 🛡️ Fraud Detector Hybrid

Sistema híbrido de detección de fraude que combina **motor de reglas** (determinista), **machine learning** (Isolation Forest) y **LLM local** (Ollama) para generar informes técnicos explicativos.

## Arquitectura de 3 Capas

```
┌─────────────────────────────────────────────────────────────┐
│                    TRANSACTION SCORING PIPELINE              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Layer 1: Rule Engine (Deterministic)                       │
│  ├── 6 reglas: high_amount, high_velocity, unusual_merchant │
│  ├── unusual_hours, country_mismatch, card_mismatch         │
│  └── Score: 0-100 (cap)                                     │
│                                                              │
│  Layer 2: ML Model (Isolation Forest)                       │
│  ├── 10 features: amount vs avg, velocity, geo, time        │
│  ├── Anomaly detection (unsupervised)                       │
│  └── Score: 0-100 (normalized)                              │
│                                                              │
│  Layer 3: Ensemble Scoring                                  │
│  ├── Weighted: rules 45% + ML 45% + context 10%             │
│  ├── Dynamic thresholds by amount tier                      │
│  └── Classification: legitimate | review | fraud            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (if fraud)
┌─────────────────────────────────────────────────────────────┐
│              LLM WORKER (Async via Redis Queue)              │
├─────────────────────────────────────────────────────────────┤
│  • Consumes from "fraud:reports" queue                      │
│  • Generates technical report in Spanish                    │
│  • Includes: risk justification, recommendation, context    │
│  • Retry with exponential backoff (max 3)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              MONITORING + AUDIT TRAIL                        │
├─────────────────────────────────────────────────────────────┤
│  • Evidently AI: drift detection, performance metrics       │
│  • Retraining triggers: F1 < 0.7 OR drift_score > 30        │
│  • SHA-256 checksums on every audit entry                   │
│  • Immutable audit log: scoring, analyst actions, reports   │
└─────────────────────────────────────────────────────────────┘
```

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| **Backend** | Python 3.11 + FastAPI (async) |
| **Base de datos** | PostgreSQL 16 (async via asyncpg) |
| **Cache/Queue** | Redis 7 |
| **ML** | scikit-learn (Isolation Forest), joblib, numpy, pandas |
| **LLM** | Ollama (Llama 3.2 3B) |
| **Monitoring** | Evidently AI (drift detection, metrics) |
| **Frontend** | React 19 + TypeScript + Vite + Recharts + Zustand |
| **Auth** | JWT (python-jose) + bcrypt |
| **Contenedores** | Docker + docker-compose |
| **Testing** | pytest + pytest-asyncio + pytest-cov |

## Quick Start

### Con Docker (recomendado)

```bash
# 1. Clonar y configurar
git clone <repo-url>
cd fraud-detector
cp .env.example .env

# 2. Levantar servicios
docker compose up -d

# 3. Pull del modelo LLM
docker compose exec ollama ollama pull llama3.2:3b

# 4. Ejecutar migraciones
docker compose exec api alembic upgrade head

# 5. Acceder
# API: http://localhost:8000/docs
# Frontend: http://localhost:3000
```

### Desarrollo local

```bash
# 1. Instalar dependencias backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt

# 2. Instalar dependencias frontend
cd frontend
npm install
cd ..

# 3. Levantar PostgreSQL y Redis
docker compose up postgres redis -d

# 4. Ejecutar migraciones
alembic upgrade head

# 5. Ejecutar API
uvicorn src.api.main:app --reload

# 6. Ejecutar frontend (en otra terminal)
cd frontend
npm run dev
```

## Entrenamiento del Modelo ML

El sistema funciona sin modelo ML (ml_score = 0), pero para activar la detección completa:

```bash
# 1. Descargar dataset de Kaggle
# https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud
# Guardar como data/creditcard.csv

# 2. O generar datos sintéticos
python scripts/generate_synthetic_data.py

# 3. Entrenar modelo
python scripts/train_model.py

# 4. El modelo se guarda en models/isolation_forest_v1.joblib
# 5. Reiniciar API para cargar el modelo
```

## Estructura del Proyecto

```
fraud-detector/
├── src/
│   ├── api/              # FastAPI endpoints
│   │   └── v1/           # Versioned API
│   ├── core/             # Config, database, redis, security
│   ├── models/           # SQLAlchemy models (9 entities)
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   │   ├── rule_engine.py      # 6 deterministic rules
│   │   ├── feature_engine.py   # 10 ML features
│   │   ├── ml_model.py         # Isolation Forest wrapper
│   │   ├── ensemble.py         # Weighted scoring
│   │   ├── llm.py              # Ollama client
│   │   ├── monitoring.py       # Drift detection
│   │   └── audit.py            # SHA-256 audit trail
│   └── workers/          # Async workers
│       └── llm_worker.py # Redis queue consumer
├── frontend/             # React dashboard
│   ├── src/
│   │   ├── api/          # Axios client + JWT interceptor
│   │   ├── store/        # Zustand state management
│   │   ├── pages/        # Login, Dashboard, Transactions, Alerts
│   │   └── components/   # Charts, tables, forms
│   └── ...
├── tests/                # pytest suite (246 tests, 88% coverage)
├── scripts/              # Training + data generation
├── docker/               # Dockerfiles + nginx.conf
├── openspec/             # SDD artifacts (specs, design, tasks)
└── ...
```

## API Endpoints

### Transacciones
- `POST /api/v1/transactions` — Crear + score completo
- `GET /api/v1/transactions` — Listar con filtros
- `GET /api/v1/transactions/{id}` — Detalle
- `DELETE /api/v1/transactions/{id}` — Soft delete (admin)

### Alertas
- `GET /api/v1/alerts` — Listar alertas
- `POST /api/v1/alerts/{id}/review` — Marcar como revisada
- `POST /api/v1/alerts/{id}/false-positive` — Marcar falso positivo
- `POST /api/v1/alerts/{id}/revert` — Revertir bloqueo

### Reportes LLM
- `GET /api/v1/transactions/{id}/report` — Obtener informe (200/202/404)

### Monitoreo
- `GET /api/v1/monitoring/drift` — Reporte de drift
- `GET /api/v1/monitoring/metrics` — Métricas del modelo
- `GET /api/v1/monitoring/dashboard` — Dashboard metrics

### Auditoría
- `GET /api/v1/audit/transactions/{id}` — Trail de decisiones
- `GET /api/v1/audit/analysts/{id}` — Actividad del analista (admin)
- `POST /api/v1/audit/export` — Exportar log (admin)

### Autenticación
- `POST /api/v1/auth/register` — Registro
- `POST /api/v1/auth/login` — Login (JWT)
- `POST /api/v1/auth/refresh` — Refresh token
- `POST /api/v1/auth/logout` — Logout (blacklist)

## Variables de Entorno

```env
# Database
DB_USER=fraud
DB_PASSWORD=your_password
DB_NAME=fraud_detector
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0

# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
OLLAMA_TIMEOUT=30

# JWT
JWT_SECRET_KEY=your_jwt_secret
JWT_ALGORITHM=HS256
JWT_EXP_MINUTES=15

# Ensemble Weights
ENSEMBLE_RULE_WEIGHT=0.45
ENSEMBLE_ML_WEIGHT=0.45
ENSEMBLE_CONTEXT_WEIGHT=0.10

# Feature Flags
FRAUD_DETECTION_ENABLED=true

# Frontend
FRONTEND_URL=http://localhost:3000
```

## Testing

```bash
# Ejecutar todos los tests
pytest tests/ -v --cov=src --cov-report=term

# Solo tests unitarios
pytest tests/unit/ -v

# Solo tests de integración
pytest tests/integration/ -v

# Con coverage detallado
pytest tests/ -v --cov=src --cov-report=html
# Abrir htmlcov/index.html en el navegador
```

**Cobertura actual:** 88% (246 tests)

## Decisiones de Arquitectura

### ¿Por qué 3 capas?
- **Reglas**: Rápido, explicable, determinista. Captura patrones conocidos.
- **ML**: Detecta anomalías no obvias. Complementa las reglas.
- **LLM**: Genera informes técnicos para analistas. NO decide, solo explica.

### ¿Por qué Isolation Forest?
- Unsupervised: no necesita datos etiquetados
- Rápido: entrena en segundos, predice en microsegundos
- Explicable: anomaly_score se puede convertir a risk_score
- Liviano: corre en CPU, no necesita GPU

### ¿Por qué ensemble ponderado?
- Simple y tunable: los pesos se pueden ajustar sin reentrenar
- Explicable: cada capa contribuye al score final
- Robusto: si una capa falla, las otras compensan

### ¿Por qué LLM solo explica?
- El LLM NO decide (no bloquea, no aprueba)
- Solo genera informes técnicos para analistas
- Evita alucinaciones críticas en la decisión de fraude

## Rate Limiting

- `/auth/login`: 10 requests/min
- `/transactions`: 100 requests/min
- `/alerts`: 60 requests/min

## Feature Flags

- `FRAUD_DETECTION_ENABLED`: Si es `false`, endpoints de scoring devuelven 503

## Licencia

MIT

## Autor

Desarrollado como proyecto de portfolio para demostrar:
- Arquitectura de 3 capas (reglas + ML + LLM)
- ML en producción (no solo notebooks)
- Feature engineering + ensemble scoring
- Model monitoring con drift detection
- Audit trail con checksums SHA-256
- Frontend React con visualizaciones avanzadas
- Testing riguroso (246 tests, 88% coverage)
- Docker + deployment ready
