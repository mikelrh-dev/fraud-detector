# Próximos Pasos — Fraud Detector

> Todo el código está implementado. Estos son los pasos manuales que debes completar para tener el sistema funcionando.

---

## 1. Descargar Dataset de Kaggle

El modelo ML necesita datos para entrenarse.

```bash
# Crear directorio de datos
mkdir -p data

# Opción A: Descargar desde Kaggle
# 1. Ir a https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud
# 2. Descargar creditcard.csv
# 3. Moverlo a data/creditcard.csv

# Opción B: Generar datos sintéticos (no requiere cuenta Kaggle)
python scripts/generate_synthetic_data.py
# Genera data/synthetic_transactions.csv con 50k transacciones
```

---

## 2. Entrenar el Modelo ML

```bash
# Ejecutar el script de entrenamiento
python scripts/train_model.py

# Esto genera:
# - models/isolation_forest_v1.joblib (modelo serializado)
# - logs de métricas (precision, recall, F1, AUC-ROC)

# Verificar que el modelo se creó
ls -lh models/
```

**Nota:** El sistema funciona SIN modelo (ml_score = 0), pero para activar la detección completa necesitas entrenarlo.

---

## 3. Pull del Modelo Ollama

```bash
# Levantar servicios primero
docker compose up -d

# Pull del modelo LLM (~1.3GB)
docker compose exec ollama ollama pull llama3.2:1b

# Verificar que está instalado
docker compose exec ollama ollama list
```

**Nota:** el modelo de producción es `llama3.2:1b` — lo declaran `OLLAMA_MODEL`
en `.env.example` y `ollama_model` en `src/core/config.py`. Si cambias el modelo
en uno de esos dos sitios, cámbialo en el otro también y descarga ese: la API
pide un modelo concreto y un `ollama pull` de otro deja el despliegue sano y con
todos los informes dando 404.

---

## 4. Levantar Todo el Sistema

```bash
# Construir y levantar todos los servicios
docker compose up --build -d

# Verificar que todo está corriendo
docker compose ps

# Ver logs de la API
docker compose logs -f api

# Ver logs del worker LLM
docker compose logs -f worker
```

**Servicios:**

Compose publica **un solo puerto en el host**: el `3000:80` de `frontend`, que
es nginx y hace de proxy hacia `api:8000`. Cualquier `curl http://localhost:8000/...`
desde el host recibe conexión rehusada.

| Servicio | Desde el host | Dirección |
|----------|---------------|-----------|
| Frontend + API | **sí** | http://localhost:3000 |
| API Docs | **sí** | http://localhost:3000/docs |
| Frontend (directo) | no | `frontend:80`, solo dentro de la red |
| API | no | `api:8000`, solo dentro de la red |
| PostgreSQL | no | `postgres:5432`, solo dentro de la red |
| Redis | no | `redis:6379`, solo dentro de la red |
| Ollama | no | `ollama:11434`, solo dentro de la red |

Lo que no se publica se alcanza con `docker compose exec <servicio> <comando>`.

---

## 5. Las migraciones ya corrieron

No hay paso manual. `docker/entrypoint.api.sh` ejecuta `alembic upgrade head`
bajo `set -e` antes de levantar uvicorn, así que las tablas se crean al arrancar
el contenedor `api`. Si una migración falla, el contenedor no arranca en lugar
de servir 500s.

Para comprobarlo sin ejecutar nada:

```bash
# El log del arranque
docker compose logs api | head -5
# ==> Applying database migrations
# ==> Starting API

# Y /health/ready corre SELECT 1 y PING contra Postgres y Redis de verdad
curl http://localhost:3000/health/ready

# Ver las tablas que se crearon
docker compose exec postgres psql -U fraud -d fraud_detector -c "\dt"
```

---

## 6. Crear Usuario Admin

```bash
# Registrarse via API (toda petición va por nginx, en el puerto 3000)
curl -X POST http://localhost:3000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@frauddetector.dev",
    "password": "admin123"
  }'

# Login para obtener JWT
curl -X POST http://localhost:3000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@frauddetector.dev",
    "password": "admin123"
  }'

# Guardar el token JWT para usar en las peticiones
export JWT_TOKEN="eyJ..."
```

---

## 7. Probar el Sistema

### Crear una transacción de prueba

```bash
curl -X POST http://localhost:3000/api/v1/transactions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "amount": 5500.00,
    "currency": "USD",
    "merchant_name": "Suspicious Merchant",
    "merchant_category": "gambling",
    "card_last4": "9999",
    "user_id": "00000000-0000-0000-0000-000000000001"
  }'
```

**Respuesta esperada:**
```json
{
  "transaction_id": "...",
  "rule_score": 50.0,
  "ml_score": 0.0,
  "ensemble_score": 22.5,
  "threshold": 40,
  "classification": "review",
  "fired_rules": ["high_amount"],
  "created_at": "..."
}
```

### Ver alertas

```bash
curl http://localhost:3000/api/v1/alerts \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### Ver informe LLM (si se generó)

```bash
curl http://localhost:3000/api/v1/transactions/{transaction_id}/report \
  -H "Authorization: Bearer $JWT_TOKEN"
```

---

## 8. Frontend Dashboard

Abrir http://localhost:3000 en el navegador.

**Credenciales:**
- Email: `admin@frauddetector.dev`
- Password: `admin123`

**Funcionalidades:**
- Dashboard con métricas y gráficos
- Lista de transacciones con filtros
- Detalle de transacción con breakdown de scoring
- Panel de alertas con acciones (review, false-positive, revert)
- Informes LLM técnicos

---

## 9. (Opcional) Deploy a Oracle Cloud

Si quieres desplegar en tu VPS Oracle Cloud:

```bash
# 1. Conectar al VPS
ssh oracle@<tu-ip>

# 2. Clonar el repo
git clone https://github.com/mikelrh-dev/fraud-detector.git
cd fraud-detector

# 3. Configurar .env
cp .env.example .env
nano .env  # Editar con valores de producción

# 4. Levantar servicios
docker compose up -d --build

# 5. Pull modelo Ollama
docker compose exec ollama ollama pull llama3.2:1b

# 6. Verificar. No hay paso de migraciones: el entrypoint corre
#    `alembic upgrade head` bajo `set -e` al arrancar `api`
docker compose ps
curl http://localhost:3000/health/ready

# 7. (Opcional) Configurar Nginx + SSL
# Ver docs de Let's Encrypt para tu dominio
```

---

## 10. (Opcional) Grabar Video Demo

Para tu portfolio, graba un video de 30-60 segundos mostrando:

1. **Dashboard** — métricas, gráficos, última actividad
2. **Crear transacción** — mostrar el scoring en tiempo real
3. **Alerta de fraude** — mostrar la clasificación y el informe LLM
4. **Acción del analista** — marcar como falso positivo o revertir
5. **Audit trail** — mostrar el log de decisiones

**Herramientas recomendadas:**
- OBS Studio (gratis, multiplataforma)
- Loom (gratis hasta 5 min)
- QuickTime (Mac)

---

## Checklist Final

- [ ] Dataset descargado o generado
- [ ] Modelo ML entrenado (`models/isolation_forest_v1.joblib`)
- [ ] Modelo Ollama descargado (`llama3.2:1b`)
- [ ] `docker compose up` funcionando
- [ ] Migraciones aplicadas por el entrypoint al arrancar `api`
- [ ] Usuario admin creado
- [ ] Transacción de prueba creada
- [ ] Alerta generada
- [ ] Informe LLM generado
- [ ] Frontend accesible en http://localhost:3000
- [ ] Video demo grabado (opcional)
- [ ] Deploy a Oracle Cloud (opcional)

---

## Troubleshooting

### Error: "Fraud detection is currently disabled"
```bash
# Verificar .env
grep FRAUD_DETECTION_ENABLED .env
# Debe ser: FRAUD_DETECTION_ENABLED=true
```

### Error: "Model not found"
```bash
# Verificar que el modelo existe
ls -lh models/
# Si no existe, correr: python scripts/train_model.py
```

### Error: "Ollama connection refused"
```bash
# Verificar que Ollama está corriendo
docker compose ps ollama
# Pull del modelo — nada lo descarga por ti
docker compose exec ollama ollama pull llama3.2:1b
```

### Error: "Port already in use"
```bash
# El único puerto que compose publica en el host es el 3000 (frontend: 80).
# Detener lo que lo ocupe, o cambiar "3000:80" en docker-compose.yml.
# El 8000 no puede entrar en conflicto: es un expose: interno del contenedor api.
# Postgres, Redis y Ollama tampoco publican nada.
```

---

## Recursos

- **API Docs**: http://localhost:3000/docs
- **README**: [README.md](./README.md)
- **SDD Artifacts**: [openspec/](./openspec/)
- **Tests**: `pytest tests/ -v --cov=src`

---

*Última actualización: 2026-06-11*
