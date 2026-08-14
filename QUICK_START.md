# QUICK START: Poner el Sistema Operativo (5 minutos)

## TL;DR - Comandos esenciales

```bash
# 1. Clonar + entrar
git clone https://github.com/mikelrh-dev/fraud-detector.git
cd fraud-detector

# 2. Preparar .env
cp .env.example .env

# 3. Iniciar TODO
docker compose up -d

# 4. Esperar a que Ollama descargue modelo (5-10 min)
docker compose logs ollama | grep "Successfully loaded"

# 5. Inicializar BD
docker compose exec api alembic upgrade head

# 6. Verificar que funciona
curl http://localhost:8000/health
redis-cli ping

# 7. Crear transacción de prueba
curl -X POST http://localhost:8000/api/v1/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test",
    "amount": 100,
    "merchant_name": "Amazon",
    "merchant_category": "retail",
    "card_last4": "4242"
  }'
```

## Verificación rápida

```bash
# Todos sanos?
docker compose ps

# Logs vivos
docker compose logs -f

# Resources OK?
docker stats

# Redis persistencia activa?
redis-cli CONFIG GET appendonly  # Should show: yes

# Frontend?
curl http://localhost:3000

# Workers procesando?
docker compose logs embedding-worker | grep "processed"
```

## Puertos

- **API:** http://localhost:8000
- **Frontend:** http://localhost:3000
- **PostgreSQL:** localhost:5432
- **Redis:** localhost:6379
- **Ollama:** localhost:11434

## Si algo falla

```bash
# Logs detallados
docker compose logs <service_name>

# Reiniciar servicio
docker compose restart <service_name>

# Reset completo (⚠️ borra datos)
docker compose down -v && docker compose up -d
```

## Para VPS (después de probarlo en local)

```bash
# 1. SSH a VPS
ssh user@vps_ip

# 2. Clonar
git clone https://github.com/mikelrh-dev/fraud-detector.git
cd fraud-detector

# 3. Instalar Docker si no está
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 4. Copiar .env con credenciales de prod
nano .env

# 5. Iniciar
docker compose up -d

# 6. Monitorear
docker compose logs -f
```

---

**LISTO.** 🚀
