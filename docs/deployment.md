# Deployment Guide

## Requisitos Previos

- Docker 24+
- Docker Compose 2+
- Python 3.11+ (para desarrollo local)
- 4GB RAM mínimo (8GB recomendado)

## Configuración de entorno

Crear `.env` en la raíz del proyecto:

```bash
# Database
DB_USER=fraud
DB_PASSWORD=change_me_in_prod
DB_NAME=fraud_detector
DB_HOST=postgres
DB_PORT=5432

# Redis
REDIS_PASSWORD=change_me_in_prod
REDIS_URL=redis://:change_me_in_prod@redis:6379/0

# API
ENVIRONMENT=production
JWT_SECRET_KEY=generate_with_secrets.token_urlsafe(32)
API_SECRET_KEY=generate_with_secrets.token_urlsafe(32)
FRONTEND_URL=https://your-domain.com

# Ollama
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=llama3.2:1b
```

## Deploy con Docker Compose

```bash
# Build y start
docker compose up -d

# Descargar el modelo del LLM (nada en el stack lo hace por ti; el
# healthcheck de ollama es `ollama list`, que pasa con cero modelos)
docker compose exec ollama ollama pull llama3.2:1b

# Verificar health. Compose NO publica el puerto de la API: el unico
# puerto en el host es 3000, que es nginx, y nginx hace de proxy de
# /api, /health y /docs hacia api:8000 dentro de la red.
curl http://localhost:3000/health
curl http://localhost:3000/health/ready
curl http://localhost:3000/health/workers

# Ver logs
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f shap-worker
docker compose logs -f embedding-worker
```

## Migraciones

Las migraciones se aplican automáticamente al iniciar el contenedor `api`. Para aplicar manualmente:

```bash
docker compose exec api alembic upgrade head
```

## Health Checks

| Endpoint | Descripción |
|---|---|
| `GET /health` | API está viva |
| `GET /health/ready` | DB y Redis alcanzables |
| `GET /health/workers` | Consumer lag por stream |
| `GET /metrics` | Métricas Prometheus |

## Troubleshooting

### Workers no consumen mensajes

```bash
# Verificar consumer groups
docker compose exec redis redis-cli XINFO GROUPS fraud:llm

# Verificar pendientes
docker compose exec redis redis-cli XPENDING fraud:llm llm-workers - + 10
```

### DB no conecta

```bash
# Verificar salud de postgres
docker compose ps postgres

# Ver logs
docker compose logs postgres
```

### ML model no carga

```bash
# Verificar que el modelo existe
docker compose exec api ls -la models/

# Re-entrenar si es necesario. train_model.py escribe una baseline sin
# calibrar en models/xgboost_reference_v1.joblib y NO es el modelo que se
# sirve; el que se sirve lo produce train_xgboost_aligned.py.
docker compose exec api python scripts/train_xgboost_aligned.py
```

## Rollback

```bash
# Revertir a versión anterior
docker compose down
git checkout <previous-commit>
docker compose up -d
```

## Monitoreo

Configurar Prometheus para scrapear `http://api:8000/metrics`:

```yaml
scrape_configs:
  - job_name: fraud-detector
    static_configs:
      - targets: ["api:8000"]
```
