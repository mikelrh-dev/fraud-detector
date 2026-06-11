# 🛡️ Fraud Detector Hybrid

Sistema híbrido de detección de fraude que combina un **motor de reglas** (rápido, determinista) con un **LLM local** (Ollama) para generar informes explicativos.

## Arquitectura

```
Transacción → Motor de Reglas → Score + Alerta
                                    ↓
                              LLM Worker (Ollama)
                                    ↓
                              Informe Explicativo
                                    ↓
                              Dashboard (React)
```

## Stack

- **Backend:** Python 3.11 + FastAPI
- **Base de datos:** PostgreSQL 16 (async)
- **Cache/Queue:** Redis 7
- **LLM:** Ollama (Llama 3.2 3B)
- **Frontend:** React + TypeScript + Vite
- **Contenedores:** Docker + docker-compose

## Quick Start

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

## Estructura

```
src/
├── api/          # Endpoints FastAPI
├── models/       # Modelos SQLAlchemy
├── schemas/      # Pydantic schemas
├── services/     # Lógica de negocio (motor de reglas)
├── workers/      # LLM Worker (generación de informes)
├── utils/        # Utilidades
└── core/         # Config, DB, Redis
```

## Desarrollo

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar tests
pytest tests/ -v --cov=src

# Ejecutar API en modo dev
uvicorn src.api.main:app --reload
```

## Licencia

MIT
