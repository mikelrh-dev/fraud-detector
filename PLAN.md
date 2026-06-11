# 🛡️ Fraud Detector Hybrid — Plan de Desarrollo

> **Fecha:** 2026-06-11
> **Autor:** OWL (Hermes) + Mikel
> **Duración:** 21 días (3 semanas)
> **Stack:** FastAPI + PostgreSQL + Redis + Ollama + React
> **Coste:** 0€ (VPS Oracle Cloud Always Free)

---

## 🎯 Visión del Proyecto

Sistema híbrido de detección de fraude que combina:
- **Motor de reglas** (backend sólido, determinista)
- **LLM local con Ollama** (informes explicativos, contexto)

> *"El motor de reglas detecta. El LLM explica por qué."*

---

## 📐 Arquitectura

```
┌─────────────────────────────────────────────────┐
│                  FRONTEND                        │
│              React + TailwindCSS                 │
│     Dashboard │ Alertas │ Informes │ Config      │
└──────────────────────┬──────────────────────────┘
                       │ REST API / WebSocket
┌──────────────────────▼──────────────────────────┐
│                  BACKEND (FastAPI)                │
│                                                  │
│  ┌──────────────┐  ┌──────────────┐             │
│  │  API Layer   │  │  WebSocket   │             │
│  │  (endpoints) │  │  (tiempo     │             │
│  │              │  │   real)      │             │
│  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                      │
│  ┌──────▼─────────────────▼───────┐             │
│  │     FRAUD DETECTION ENGINE     │             │
│  │                                │             │
│  │  ┌─────────┐  ┌────────────┐  │             │
│  │  │ REGLAS  │  │  LLM       │  │             │
│  │  │ Motor   │──│  Ollama    │  │             │
│  │  │         │  │  Llama 3B  │  │             │
│  │  └─────────┘  └────────────┘  │             │
│  └──────────────┬────────────────┘             │
│                 │                                │
│  ┌──────────────▼────────────────┐             │
│  │    DATA LAYER                 │             │
│  │  PostgreSQL │ Redis │ Docker  │             │
│  └───────────────────────────────┘             │
└─────────────────────────────────────────────────┘
```

---

## 📅 Fase 1: API + Base de Datos (Días 1-5)

### Día 1: Setup del proyecto

```bash
mkdir -p ~/projects/fraud-detector/{src/{api,models,schemas,services,workers,utils},tests/{unit,integration},frontend}
cd ~/projects/fraud-detector
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn[standard] sqlalchemy asyncpg pydantic pydantic-settings redis pytest pytest-asyncio httpx factory-boy faker python-dotenv alembic
```

**Tareas:**
- [ ] Crear estructura de carpetas
- [ ] Configurar venv + requirements.txt
- [ ] Configurar `.env` y `.env.example`
- [ ] Configurar `.gitignore`
- [ ] Docker Compose (PostgreSQL + Redis)
- [ ] README.md inicial

**docker-compose.yml:**
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: fraud_detector
      POSTGRES_USER: fraud_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

### Día 2: Modelos de datos

**Tareas:**
- [ ] Modelo `Transaction` (id, amount, currency, merchant, location, timestamp, user_id, status, risk_score)
- [ ] Modelo `FraudRule` (id, name, description, condition, severity, active)
- [ ] Modelo `Alert` (id, transaction_id, rule_id, severity, message, created_at, resolved)
- [ ] Modelo `User` (id, name, email, risk_profile)
- [ ] Alembic migrations
- [ ] Pydantic schemas (request/response)

**src/models/transaction.py:**
```python
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    FLAGGED = "flagged"
    BLOCKED = "blocked"

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="EUR")
    merchant = Column(String(255))
    merchant_category = Column(String(100))
    location_lat = Column(Float)
    location_lon = Column(Float)
    country = Column(String(2))
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(Enum(TransactionStatus), default=TransactionStatus.PENDING)
    risk_score = Column(Float, default=0.0)

    user = relationship("User", back_populates="transactions")
    alerts = relationship("Alert", back_populates="transaction")
```

### Día 3: Endpoints REST

**Tareas:**
- [ ] `POST /api/v1/transactions` — Crear transacción
- [ ] `GET /api/v1/transactions/{id}` — Obtener transacción
- [ ] `GET /api/v1/transactions` — Listar con filtros (status, fecha, user_id)
- [ ] `GET /api/v1/alerts` — Listar alertas
- [ ] `PATCH /api/v1/alerts/{id}/resolve` — Resolver alerta
- [ ] `GET /api/v1/rules` — Listar reglas
- [ ] `POST /api/v1/rules` — Crear regla
- [ ] `GET /api/v1/stats` — Estadísticas del dashboard

### Día 4: Motor de reglas

**Tareas:**
- [ ] Servicio `RuleEngine` — evalúa transacciones contra reglas activas
- [ ] Reglas predefinidas:
  - **Monto alto:** > 5000€ → riesgo alto
  - **Velocidad:** > 3 transacciones en 5 minutos → sospechoso
  - **Ubicación:** país diferente al habitual → revisar
  - **Hora inusual:** transacción entre 00:00-06:00 → revisar
  - **Merchant de riesgo:** lista negra de merchants
- [ ] Sistema de scoring: cada regla suma puntos de riesgo
- [ ] Umbrales: 0-30 bajo, 30-70 medio, 70-100 alto

**src/services/rule_engine.py:**
```python
class RuleEngine:
    def __init__(self, db_session):
        self.db = db_session
        self.rules = []

    async def load_rules(self):
        """Carga reglas activas de la BD"""
        ...

    async def evaluate(self, transaction: Transaction) -> RiskAssessment:
        """Evalúa una transacción contra todas las reglas"""
        score = 0.0
        triggered_rules = []

        for rule in self.rules:
            if await rule.check(transaction):
                score += rule.weight
                triggered_rules.append(rule)

        return RiskAssessment(
            score=min(score, 100.0),
            level=self._get_level(score),
            triggered_rules=triggered_rules
        )
```

### Día 5: Tests Fase 1

**Tareas:**
- [ ] Tests unitarios del motor de reglas
- [ ] Tests de integración de endpoints
- [ ] Tests con datos de ejemplo (factory_boy)
- [ ] Cobertura > 80%
- [ ] CI local (pre-commit hooks)

---

## 📅 Fase 2: LLM Worker (Días 6-10)

### Día 6: Setup Ollama

```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh
# Descargar modelo ligero (3B, ~2GB RAM)
ollama pull llama3.2:3b
```

**Tareas:**
- [ ] Instalar Ollama en VPS
- [ ] Descargar `llama3.2:3b` (~2GB)
- [ ] Verificar que funciona: `ollama run llama3.2:3b "Hello"`
- [ ] Crear script de inicio automático con Docker

### Día 7: Servicio LLM

**Tareas:**
- [ ] Servicio `LLMService` — se conecta a Ollama via API
- [ ] Prompt engineering para análisis de fraude
- [ ] Generación de informes explicativos
- [ ] Cache de respuestas en Redis (evitar llamadas repetidas)

**src/services/llm_service.py:**
```python
class LLMService:
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.client = httpx.AsyncClient(base_url=ollama_url)

    async def analyze_transaction(
        self,
        transaction: Transaction,
        risk_assessment: RiskAssessment
    ) -> str:
        """Genera informe explicativo del riesgo"""
        prompt = self._build_prompt(transaction, risk_assessment)
        response = await self.client.post("/api/generate", json={
            "model": "llama3.2:3b",
            "prompt": prompt,
            "stream": False
        })
        return response.json()["response"]

    def _build_prompt(self, tx, risk) -> str:
        return f"""Eres un analista de fraude experto. Analiza esta transacción:

Transacción:
- Monto: {tx.amount} {tx.currency}
- Merchant: {tx.merchant}
- País: {tx.country}
- Hora: {tx.timestamp}

Evaluación de riesgo:
- Score: {risk.score}/100
- Nivel: {risk.level}
- Reglas activadas: {[r.name for r in risk.triggered_rules]}

Genera un informe breve (3-5 líneas) explicando:
1. Por qué es sospechosa (o por qué no)
2. Recomendación: aprobar, revisar, o bloquear
3. Contexto adicional relevante

Informe:"""
```

### Día 8: Worker asíncrono

**Tareas:**
- [ ] Worker que procesa transacciones en cola (Redis)
- [ ] Flujo: transacción creada → evaluar reglas → si riesgo medio/alto → LLM analiza
- [ ] Resultados guardados en BD
- [ ] WebSocket para notificaciones en tiempo real

### Día 9: Endpoints LLM

**Tareas:**
- [ ] `GET /api/v1/transactions/{id}/analysis` — Informe LLM
- [ ] `POST /api/v1/analyze` — Análisis manual de una transacción
- [ ] `GET /api/v1/reports` — Informes generados
- [ ] Tests del servicio LLM (con mocks)

### Día 10: Tests Fase 2

**Tareas:**
- [ ] Tests del LLMService con mocks
- [ ] Tests del worker asíncrono
- [ ] Tests de integración completos
- [ ] Verificar uso de RAM (< 4GB total con Ollama)

---

## 📅 Fase 3: Dashboard React (Días 11-15)

### Día 11: Setup frontend

```bash
cd ~/projects/fraud-detector/frontend
npm create vite@latest . -- --template react-ts
npm install tailwindcss @tailwindcss/vite recharts lucide-react
```

**Tareas:**
- [ ] Vite + React + TypeScript
- [ ] TailwindCSS
- [ ] Recharts (gráficos)
- [ ] Estructura de componentes

### Día 12: Componentes principales

**Tareas:**
- [ ] `Dashboard` — vista general con métricas
- [ ] `TransactionList` — lista de transacciones
- [ ] `AlertPanel` — panel de alertas
- [ ] `RiskMeter` — medidor de riesgo visual

### Día 13: Gráficos y visualización

**Tareas:**
- [ ] Gráfico de transacciones por día (línea)
- [ ] Gráfico de alertas por tipo (barras)
- [ ] Mapa de calor de fraude por país
- [ ] Tabla de transacciones con filtros

### Día 14: Tiempo real

**Tareas:**
- [ ] Conexión WebSocket al backend
- [ ] Notificaciones de nuevas alertas
- [ ] Actualización en tiempo real del dashboard
- [ ] Estado global (React Context o Zustand)

### Día 15: Tests Fase 3

**Tareas:**
- [ ] Tests de componentes con Vitest
- [ ] Tests de integración frontend
- [ ] E2E con Playwright (opcional)
- [ ] Responsive design

---

## 📅 Fase 4: Pulido + Deploy (Días 16-21)

### Día 16-17: Seguridad

**Tareas:**
- [ ] Autenticación JWT
- [ ] Rate limiting
- [ ] CORS configurado
- [ ] Input validation completa
- [ ] Headers de seguridad

### Día 18-19: Deploy

**Tareas:**
- [ ] Docker Compose de producción
- [ ] Nginx como reverse proxy
- [ ] SSL con Let's Encrypt (si hay dominio)
- [ ] Variables de entorno de producción
- [ ] Health checks

### Día 20: Documentación

**Tareas:**
- [ ] README.md completo con:
  - Descripción del proyecto
  - Arquitectura
  - Instalación
  - API docs
  - Screenshots
- [ ] API docs automática (FastAPI /docs)
- [ ] Diagrama de arquitectura

### Día 21: Demo + Video

**Tareas:**
- [ ] Semilla de datos de prueba realistas
- [ ] Grabar video demo (30-60 seg)
- [ ] Subir a YouTube (no listado)
- [ ] Actualizar CV/LinkedIn con links

---

## 📊 Resumen de Planning

| Fase | Días | Entregable |
|---|---|---|
| **F1: API + BD** | 1-5 | API funcional con motor de reglas |
| **F2: LLM** | 6-10 | Ollama integrado, informes automáticos |
| **F3: Dashboard** | 11-15 | React dashboard con gráficos en tiempo real |
| **F4: Pulido** | 16-21 | Deploy, seguridad, docs, demo |

---

## 💰 Presupuesto de RAM

| Servicio | RAM |
|---|---|
| PostgreSQL | ~500MB |
| Redis | ~100MB |
| Ollama (llama3.2:3b) | ~2.5GB |
| FastAPI + Workers | ~300MB |
| React (build estático) | ~0MB (Nginx) |
| Nginx | ~50MB |
| **Total** | **~3.5GB** |
| **Disponible** | **24GB** |
| **Margen** | **20.5GB** ✅ |

---

## 🛠️ Stack Final

| Capa | Tecnología |
|---|---|
| Backend | Python 3.11 + FastAPI |
| Base de datos | PostgreSQL 16 |
| Cache | Redis 7 |
| LLM | Ollama + Llama 3.2 3B |
| Frontend | React 19 + TypeScript + TailwindCSS |
| Gráficos | Recharts |
| Deploy | Docker Compose + Nginx |
| Tests | pytest + Vitest |
| VPS | Oracle Cloud ARM64 (4 cores, 24GB RAM) |

---

## 🎯 Criterios de Éxito

- [ ] API recibe transacciones y las evalúa en < 200ms
- [ ] Motor de reglas detecta patrones conocidos con > 90% precisión
- [ ] LLM genera informes coherentes en < 5 segundos
- [ ] Dashboard muestra datos en tiempo real
- [ ] Cobertura de tests > 80%
- [ ] Seguridad: 0 vulnerabilidades críticas
- [ ] Video demo funcionando
- [ ] Código en GitHub con README profesional

---

*Documento creado por OWL (Hermes) — 2026-06-11*
*Actualizar según evolución del desarrollo*
