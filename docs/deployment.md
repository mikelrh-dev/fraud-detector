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
OLLAMA_MODEL=qwen2.5:0.5b
```

## Deploy con Docker Compose

```bash
# Build y start
docker compose up -d

# Verificar health
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
curl http://localhost:8000/health/workers

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

# Re-entrenar si es necesario
docker compose exec api python scripts/train_model.py
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
