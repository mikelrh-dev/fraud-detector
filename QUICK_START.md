# QUICK START: Poner el Sistema en Marcha (5 minutos)

## TL;DR - Comandos esenciales

```bash
# 1. Clonar + entrar
git clone https://github.com/mikelrh-dev/fraud-detector.git
cd fraud-detector

# 2. Preparar .env
cp .env.example .env

# 3. Iniciar TODO
docker compose up -d

# 4. Descargar el modelo del LLM (lo hace falta, y NADIE lo descarga por ti)
docker compose exec ollama ollama pull llama3.2:1b

# 5. Verificar que la API responde (a traves de nginx, en el puerto 3000)
curl http://localhost:3000/health
curl http://localhost:3000/health/ready    # este consulta Postgres y Redis de verdad

# 6. Crear un usuario
curl -X POST http://localhost:3000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","email":"demo@example.com","password":"Str0ng-Pass-2026","role":"analyst"}'

# 7. Iniciar sesion y copiar el access_token de la respuesta
curl -X POST http://localhost:3000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"Str0ng-Pass-2026"}'

export TOKEN="<pega aqui el access_token>"

# 8. Crear transaccion de prueba (necesita el token: el endpoint exige auth)
curl -X POST http://localhost:3000/api/v1/transactions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "amount": 100,
    "currency": "USD",
    "merchant_name": "Amazon",
    "merchant_category": "retail",
    "card_last4": "4242"
  }'
```

## Notas sobre los pasos

- **El puerto es 3000, no 8000.** Compose no publica el puerto de la API: el
  unico contenedor que publica un puerto en el host es `frontend`, que es
  nginx. Nginx hace de proxy de `/api/`, `/health`, `/docs` y `/openapi.json`
  hacia `api:8000` dentro de la red. Es deliberado: publicar la API crearia un
  segundo acceso que se salta nginx, que es el unico componente que sobrescribe
  `X-Real-IP`, y con el limitador por IP por delante un atacante podria falsear
  su IP en cada peticion.
- **El paso 4 no es opcional.** El healthcheck de `ollama` es `ollama list`, que
  pasa con cero modelos, asi que un despliegue recien levantado se declara sano
  sin tener modelo y luego todos los informes dan 404. `OLLAMA_MODEL` en
  `.env.example` dice `llama3.2:1b`; cambia el modelo, cambialo en los dos
  sitios.
- **No hay paso de base de datos.** `docker/entrypoint.api.sh` corre
  `alembic upgrade head` bajo `set -e` antes de levantar uvicorn, asi que las
  migraciones se aplican al arrancar el contenedor `api`. Si una migracion
  falla, el contenedor no arranca en lugar de servir 500s.
- **El paso 8 necesita token.** `POST /api/v1/transactions` depende de
  `get_current_user` y responde 401 sin cabecera `Authorization`. El payload
  exige `amount`, `currency` (3 letras, ISO 4217), `merchant_name` y
  `card_last4` (exactamente 4 caracteres). No lleva `user_id`: el campo existe
  pero esta deprecado y el servidor lo ignora a proposito — usa siempre la
  identidad del token, no la del payload.

## Verificacion rapida

```bash
# Todos sanos?
docker compose ps

# Logs vivos
docker compose logs -f

# Resources OK?
docker stats

# Redis responde? (no publica puerto: hay que entrar al contenedor)
docker compose exec redis redis-cli ping                 # PONG
docker compose exec redis redis-cli CONFIG GET appendonly # appendonly: yes

# Postgres responde? (tampoco publica puerto)
docker compose exec postgres psql -U fraud -d fraud_detector -c '\dt'

# Workers procesando?
docker compose logs embedding-worker | grep "Embedding processed"

# Frontend?
curl http://localhost:3000
```

## Puertos

Compose publica **un solo puerto en el host**.

| Servicio | Desde el host | Direccion |
|---|---|---|
| `frontend` (nginx) + API | **si** | http://localhost:3000 |
| `api` directo | no | `api:8000`, solo dentro de la red de compose |
| `postgres` | no | `postgres:5432`, solo dentro de la red |
| `redis` | no | `redis:6379`, solo dentro de la red |
| `ollama` | no | `ollama:11434`, solo dentro de la red |

Lo que no se publica se alcanza con `docker compose exec <servicio> <comando>`,
o desde otro contenedor de la misma red (`http://api:8000`).

## Si algo falla

```bash
# Logs detallados
docker compose logs <service_name>

# Reiniciar servicio
docker compose restart <service_name>

# Reset completo (borra datos: Postgres, Redis y el modelo descargado)
docker compose down -v && docker compose up -d && docker compose exec ollama ollama pull llama3.2:1b
```

## Para VPS (despues de probarlo en local)

```bash
# 1. SSH a VPS
ssh user@vps_ip

# 2. Clonar
git clone https://github.com/mikelrh-dev/fraud-detector.git
cd fraud-detector

# 3. Instalar Docker si no esta
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 4. Copiar .env y cambiar las credenciales
cp .env.example .env
nano .env

# 5. Iniciar
docker compose up -d

# 6. Descargar el modelo del LLM
docker compose exec ollama ollama pull llama3.2:1b

# 7. Monitorear
docker compose logs -f
```

En el VPS solo sigue publicado el puerto 3000, asi que la API se alcanza en
`http://<tu-dominio>:3000`. Pon `FRONTEND_URL` y `ENVIRONMENT=production` en el
`.env` antes de exponerlo: en produccion se desactivan `/docs` y
`/openapi.json`, y `JWT_SECRET_KEY` pasa a ser obligatorio.

---

**LISTO.** Todo lo de arriba esta comprobado contra `docker-compose.yml` y
contra los schemas de Pydantic: los URLs apuntan al unico puerto publicado, los
payloads validan contra `TransactionCreate` y `RegisterRequest`, y el modelo
coincide con `OLLAMA_MODEL`.
