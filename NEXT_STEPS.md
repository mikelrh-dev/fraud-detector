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

# Pull del modelo LLM (~2GB)
docker compose exec ollama ollama pull llama3.2:3b

# Verificar que está instalado
docker compose exec ollama ollama list
```

**Alternativa más rápida:** Usar un modelo más pequeño:
```bash
docker compose exec ollama ollama pull qwen2.5:1.5b  # ~1GB, más rápido
```

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
| Servicio | URL | Descripción |
|----------|-----|-------------|
| API | http://localhost:8000 | Backend FastAPI |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Frontend | http://localhost:3000 | Dashboard React |
| PostgreSQL | localhost:5432 | Base de datos |
| Redis | localhost:6379 | Cache + Queue |
| Ollama | localhost:11434 | LLM local |

---

## 5. Ejecutar Migraciones de Base de Datos

```bash
# Crear tablas en PostgreSQL
docker compose exec api alembic upgrade head

# Verificar que las tablas se crearon
docker compose exec postgres psql -U fraud -d fraud_detector -c "\dt"
```

---

## 6. Crear Usuario Admin

```bash
# Registrarse via API
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@fraud-detector.local",
    "password": "admin123"
  }'

# Login para obtener JWT
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@fraud-detector.local",
    "password": "admin123"
  }'

# Guardar el token JWT para usar en las peticiones
export JWT_TOKEN="eyJ..."
```

---

## 7. Probar el Sistema

### Crear una transacción de prueba

```bash
curl -X POST http://localhost:8000/api/v1/transactions \
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
curl http://localhost:8000/api/v1/alerts \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### Ver informe LLM (si se generó)

```bash
curl http://localhost:8000/api/v1/transactions/{transaction_id}/report \
  -H "Authorization: Bearer $JWT_TOKEN"
```

---

## 8. Frontend Dashboard

Abrir http://localhost:3000 en el navegador.

**Credenciales:**
- Email: `admin@fraud-detector.local`
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
docker compose exec ollama ollama pull llama3.2:3b

# 6. Migraciones
docker compose exec api alembic upgrade head

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
- [ ] Modelo Ollama descargado (`llama3.2:3b`)
- [ ] `docker compose up` funcionando
- [ ] Migraciones ejecutadas
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
# Pull del modelo
docker compose exec ollama ollama pull llama3.2:3b
```

### Error: "Port already in use"
```bash
# Cambiar puertos en docker-compose.yml o detener otros servicios
# API: 8000, Frontend: 3000, Postgres: 5432, Redis: 6379, Ollama: 11434
```

---

## Recursos

- **API Docs**: http://localhost:8000/docs
- **README**: [README.md](./README.md)
- **SDD Artifacts**: [openspec/](./openspec/)
- **Tests**: `pytest tests/ -v --cov=src`

---

*Última actualización: 2026-06-11*
