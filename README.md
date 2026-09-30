# 🛡️ Fraud Detector Hybrid

[![CI](https://github.com/mikelrh-dev/fraud-detector/actions/workflows/ci.yml/badge.svg)](https://github.com/mikelrh-dev/fraud-detector/actions/workflows/ci.yml)

**English** | [Español](README.es.md)

> 📖 **Read the [technical case study](case-study/en/index.html)** — an 11-chapter walkthrough of how this system works, every number traced to a real artifact.
>
> 🧭 **Technical wiki:** [browse the developer wiki](docs/wiki/index.md) for the system model, architecture, scoring pipeline, workers, ML and operations.

Hybrid fraud detection system for financial transactions. A **deterministic rule engine** (9 rules), a **supervised ML model** (XGBoost) and a **local LLM** (Ollama) that writes explanatory reports for analysts — the LLM never decides, it only explains.

> **On the ML model, plainly:** it is trained on a **synthetic corpus** of fraud archetypes generated in this repo — not on PaySim, and not on bank data. The rules decide; the ML layer contributes a calibrated 25%. The measured numbers, and the limits we know about, are in [What the model does and does not do](#what-the-model-does-and-does-not-do).

Every transaction gets a 0–100 risk score, a classification (`legitimate | review | fraud`), SHAP feature attributions, and — when flagged — an async LLM-generated technical report.

## Highlights

- **3-layer ensemble scoring**: rules 60% + ML 25% + context 15%, with dynamic fraud thresholds by amount tier
- **9 deterministic rules** covering amount, velocity, merchant risk, card mismatch, off-hours patterns, country mismatch and fraud-ring proximity
- **XGBoost** with 10 engineered features, graceful degradation (system works with `ml_score = 0` if no model is loaded)
- **SHAP explainability**: top-5 feature contributions persisted per transaction
- **Fraud ring detection**: directed graph (NetworkX), flags users within 2 hops of a known fraudster
- **Merchant spoofing detection**: sentence-transformers embeddings + cosine similarity (catches `AMAZ0N_STORE` → `Amazon`)
- **Redis Streams** with consumer groups, pending-message recovery (`XAUTOCLAIM`) and a dead-letter queue
- **Model monitoring**: Evidently data drift + custom PSI, automatic retraining triggers (F1 < 0.7 or drift > 30) — implemented, not yet exercised against a populated reference
- **Immutable audit trail** with SHA-256 checksums on every scoring decision and analyst action
- **JWT auth** (access + refresh + blacklist), role-based access (user/admin), per-route rate limiting
- **React 19 dashboard** with score trends, SHAP cards and alert workflow
- **846 backend tests** (unit + integration) and 746 frontend tests, CI with 5 jobs (ruff, mypy, pytest, ESLint, vitest, Docker smoke build)

## Architecture

```mermaid
flowchart TB
    FE["React 19 Dashboard"] -->|"REST + JWT"| API["FastAPI (async)"]

    API --> RE["Layer 1 · Rule Engine<br/>9 deterministic rules"]
    API --> ML["Layer 2 · XGBoost<br/>10 engineered features"]
    API --> CTX["Layer 3 · Context<br/>user history · geo · time"]

    RE --> ENS["Ensemble Scorer<br/>0.60 / 0.25 / 0.15"]
    ML --> ENS
    CTX --> ENS

    ENS --> DB[("PostgreSQL 16")]
    ENS -->|"review / fraud"| PUB["Stream Publisher"]

    PUB --> Q1["fraud:llm"] --> W1["LLM Worker<br/>Ollama report (ES)"]
    PUB --> Q2["fraud:shap"] --> W2["SHAP Worker<br/>top-5 attributions"]
    PUB --> Q3["fraud:embeddings"] --> W3["Embedding Worker<br/>spoofing check"]

    W1 -. "3 failed retries" .-> DLQ["DLQ · fraud:dlq"]
    W2 -. "3 failed retries" .-> DLQ
```

**Stack:** Python 3.11 · FastAPI · PostgreSQL 16 (asyncpg) · Redis 7 (Streams) · XGBoost · SHAP · NetworkX · sentence-transformers · Evidently · Ollama · React 19 + TypeScript + Vite + Tailwind 4 · Docker Compose (8 services)

## How a Transaction Is Scored

```
risk_score = 0.60 × rule_score + 0.25 × ml_score + 0.15 × context_score
```

Classification against a dynamic threshold that tightens for larger amounts:

| Amount tier | Fraud threshold |
|---|---|
| $0 – $1,000 | ≥ 70 |
| $1,001 – $10,000 | ≥ 50 |
| $10,001 – $50,000 | ≥ 45 |
| $50,001+ | ≥ 40 |

`review` band starts at 75% of the tier threshold. Everything below is `legitimate`.

### Layer 1 — Rule Engine (deterministic, capped at 100)

| Rule | Weight | Trigger |
|---|---|---|
| `high_amount` | 35 | amount > $1,000 |
| `velocity_burst` | 30 | > 1 txn in 5 min in a risky category |
| `high_velocity` | 25 | > 3 txns in 5 minutes |
| `off_hours_crypto` | 25 | night hours (0–6) + risky category |
| `unusual_merchant` | 20 | blacklisted merchant or risky category |
| `card_mismatch` | 20 | card not among the user's known cards |
| `country_mismatch` | 15 | txn country ≠ user home country |
| `near_fraud` | 15 | user ≤ 2 hops from a known fraudster (graph) |
| `unusual_hours` | 10 | txn between 00:00–06:00 |

Risky categories: `btc`, `crypto`, `gambling`, `casino`, `money_transfer`.

### Layer 2 — ML Model (XGBoost)

10 features: `amount`, `amount_vs_user_avg`, `amount_vs_user_std`, `tx_count_last_5min`, `tx_count_last_1h`, `hour_of_day`, `is_weekend`, `merchant_risk_level`, `is_crypto`, `amount_round_number`.

`predict_proba` is scaled straight to 0–100 (`probability * 100.0`) and calibrated with `CalibratedClassifierCV(method="sigmoid", cv=5)` against the corpus's real 1.00% prior — 502 frauds in 50,000 transactions, which the calibrator records as `calibration_prior=0.010050` — so a score is a probability against that base rate, not a raw margin. If no model file is present, the API keeps working with `ml_score = 0`.

### Layer 3 — Context

User-level signals (recent transaction velocity) contribute the remaining 15%, computed in `scoring_service.py` as `min(recent_txns / 10 × 100, 100)` and passed to the ensemble explicitly.

### What the model does and does not do

Every figure below is printed by `python scripts/evaluate_model.py`, on the 10,000-row test split that is held out of both training and SMOTE. The rows come from that split's own output block, not from a hand-kept total.

| | |
|---|---|
| Held-out ROC-AUC / PR-AUC | 0.9181 / 0.7728 |
| At the production threshold | precision 0.8353 · recall 0.7100 · F1 0.7676 |
| Confusion at that threshold | TP=71 · FP=14 · FN=29 · TN=9886 |
| False positives | 14 in 9,900 legitimate |
| Missed frauds | 29 of 100 |
| Calibration error (ECE) | 0.0026 |

**Every rate here carries an interval, because the test split holds 100 frauds.** A point estimate without one is a claim, not a measurement. `evaluate_model.py` prints these alongside the point estimates:

| | Point | 95% CI (Wilson) | Width |
|---|---|---|---|
| Precision | 0.8353 | 0.742 – 0.899 | 15.7 pts |
| Recall | 0.7100 | 0.615 – 0.790 | 17.5 pts |

Tightening the recall interval is a data problem, not a modelling one: at ~1% prevalence, a ±3-point interval needs roughly 3,600 frauds in the test split, **36× what this corpus contains**. Any project claiming a precise recall at this prevalence is either measuring something else or showing you a number it cannot support.

It is a real classifier with real discriminative power, and it is bounded. Four limits, stated as what they are:

1. **The training data is synthetic.** No bank data was ever available, so the corpus is generated from fraud archetypes (`everyday`, `burst`, `high_value_wire`, `card_testing`, …) designed to be hard on purpose. The corpus and the features were written by the same person, so the numbers above measure self-consistency, not detection.
2. **Transfer to an independent benchmark is unmeasured here.** Public fraud corpora such as PaySim give one user per transaction, which degenerates the four user-history features (`amount_vs_user_avg`, `amount_vs_user_std`, `tx_count_last_5min`, `tx_count_last_1h`) — 4 of the 10 inputs stop carrying per-user signal. This repository makes **no claim** about how the model scores on such a corpus, because nothing in it computes that.
3. **Both headline rates rest on 100 frauds.** A 17.5-point-wide recall interval is not a rounding detail; it is the resolution of this measurement. The per-archetype error breakdown the script prints is the more informative cut — `low_signal` is missed 100% of the time, `high_value_wire` 39% — and both are classes the generator writes deliberately.
4. **Recall is 0.7100 at the shipped threshold.** 29 of 100 frauds are not flagged at that operating point; the threshold is a cost trade-off, not a free parameter.

### What It Costs — and Who Decides

A precision figure is not a decision. It is a number with the cost stripped off both sides, and a threshold trades a false alarm against a missed fraud — so the trade cannot be read off either figure alone. `scripts/evaluate_cost.py` prices it.

```
python scripts/evaluate_cost.py
```

**Neither cost figure is measured, and the script will not pretend otherwise.** What a false alarm costs is the analyst time to clear it; what a missed fraud costs is your realised loss. Both are business facts about *your* operation. So the script prices a false alarm at an arbitrary 1.0 and sweeps the ratio `C_fn/C_fp`, because only the ratio moves a decision.

On the same held-out split (TP=71 · FP=14 · FN=29 · TN=9886), in units where a false alarm costs 1.0:

| Policy | Expected cost per transaction @ `C_fn/C_fp = 10` |
|---|---|
| Flag nothing (no model) | 0.1000 |
| Flag everything (no model) | 0.9900 |
| **This model at today's tiered point** | **0.0304** |
| This model at the best flat threshold (31.00) | 0.0291 |

Two things fall out of that table. First, **the cost-optimal threshold is not a constant of the model** — across ratios from 1 to 500 it moves from 74.00 down to 0.25, two orders of magnitude, so every belief about cost gets a different operating point. That is why the script prints a sweep instead of a recommendation. The tiered production point is within 0.0013 of the swept optimum at this ratio, and the sweep is cheaper at every ratio tested.

Second, the model has to beat *both* no-model policies, and on this corpus it does at every ratio the script tests — 0.0291 against a floor of 0.1000 at ratio 10, and still 0.8052 against the 0.9900 flag-everything bar at 500×. No AUC tells you that; the cost arithmetic does.

`breakeven_cost_ratio` is **99.0** — above that, flagging every transaction becomes as cheap as flagging none, because at ~1% prevalence a miss has to be that much more expensive than wasted analyst time. It is a property of the base rate alone: the same number whether the model is excellent or inverted, which is exactly why it cannot be used as evidence either way. The model still clears the flag-everything bar at 500×, and the report says so rather than implying the opposite.

**Known simplification, printed in the report:** the swept optimum is a flat threshold while production uses an amount-tiered one, so the comparison is approximate. The volume of 50,000 transactions/day is an assumption that scales every per-day number. And the counts come from a synthetic corpus — so this is arithmetic, not evidence. The model's real-world cost per transaction is **unknown**, and this is the arithmetic to have ready the day a labelled corpus exists.

## Explainability, Monitoring & Audit

- **SHAP** (`TreeExplainer` over XGBoost): top-5 feature attributions computed async per scored transaction, rendered in the dashboard.
- **Drift detection**: Evidently `DataDriftPreset` (reference vs current distributions) plus a custom PSI implementation. `GET /api/v1/monitoring/drift`.
- **Retraining triggers**: fire when `F1 < 0.7` or `drift_score > 30` (checked in `MonitoringService`). The logic is live; the drift reference it compares against has never been populated with a full window, and it now refuses to seed from fewer than 200 rows.
- **Audit trail**: every score, analyst review and LLM report is recorded with SHA-256 checksums. Analyst activity export is admin-only.

## Async Workers (Redis Streams)

| Stream | Consumer group | Worker | Output | Retry policy |
|---|---|---|---|---|
| `fraud:llm` | `llm-workers` | `llm_worker` | `LLMReport` row + audit entry | stays PENDING, max 3 |
| `fraud:shap` | `shap-workers` | `shap_worker` | `ShapAttribution` rows (top 5) | 3 retries → DLQ |
| `fraud:embeddings` | `embedding-workers` | `embedding_worker` | Redis result key (1h TTL) | ack on success, log on failure |

Streams are trimmed (`MAXLEN ~ 100,000`). The DLQ (`fraud:dlq`, capped at 10K) stores the original stream, consumer group and error reason. A recovery loop reclaims idle pending messages every 60s via `XAUTOCLAIM` (5-min idle timeout).

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/mikelrh-dev/fraud-detector.git
cd fraud-detector
cp .env.example .env

docker compose up -d                                # 8 services: postgres, redis, ollama, api, 3 workers, frontend
docker compose exec ollama ollama pull qwen2.5:0.5b # default LLM (configurable via OLLAMA_MODEL)

# Frontend + API:  http://localhost:3000
# API docs:        http://localhost:3000/docs
# Liveness:        http://localhost:3000/health
```

The API port is deliberately **not** published to the host, so nginx is the only
ingress — that is what makes the per-IP rate limiter trustworthy (`X-Real-IP` is
overwritten, not appended). Reach the API through nginx at `:3000`, never at `:8000`.

Tables and migrations are applied automatically by the api container's
entrypoint (`alembic upgrade head`) as it starts, so there is no separate
bootstrap step.

Create your first user via the API:

```bash
curl -X POST http://localhost:3000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "analyst@example.com", "password": "...", "full_name": "Analyst"}'
```

> `scripts/create_admin.py` prints a ready-to-run SQL `INSERT` if you prefer to seed an admin directly.

### Local development

```bash
# Backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Infrastructure only
docker compose up postgres redis ollama -d

python scripts/init_db.py
uvicorn src.api.main:app --reload

# Frontend (second terminal)
cd frontend && npm install && npm run dev
```

## Training the ML Model

`models/xgboost_paysim_v1.joblib` is committed, so a fresh clone already scores with the
full ML layer — nothing to train before using the system. Retraining is optional; you need
it to change the corpus, to reproduce the metrics above, or to work on the model itself:

```bash
python scripts/train_xgboost_aligned.py       # → models/xgboost_paysim_v1.joblib
# restart the API to load the model
```

There is no separate data-generation step. The trainer generates its own corpus at
50,000 transactions and ~1% fraud if `data/synthetic_transactions.csv` is missing, then
refuses to train on any corpus it did not write itself — it checks a `corpus_schema`
stamp, so a corpus produced by another generator fails loudly instead of silently
training a corrupted model.

`scripts/generate_synthetic_data.py` is a **separate** generator for notebooks and
demo dashboards: it writes a 5%-fraud seed to `data/demo_seed_transactions.csv`, which
is not a file the trainer reads.

If the artifact is missing or unreadable the API still starts and scores, contributing
`ml_score = 0` — the rules and context layers carry the decision on their own.

`train_xgboost_aligned.py` trains on the exact `FeatureEngine` features used in production. (`scripts/train_model.py` trains a legacy Isolation Forest — kept for reference, not used in the scoring path.)

## API Endpoints

### Auth
| Method | Path | Auth |
|---|---|---|
| POST | `/api/v1/auth/register` | public |
| POST | `/api/v1/auth/login` | public |
| POST | `/api/v1/auth/refresh` | refresh token |
| POST | `/api/v1/auth/logout` | user (blacklists token) |

### Transactions
| Method | Path | Auth |
|---|---|---|
| POST | `/api/v1/transactions` | user — create + full scoring pipeline |
| GET | `/api/v1/transactions` | user — list, filters, pagination |
| GET | `/api/v1/transactions/{id}` | user — detail + SHAP attributions |
| DELETE | `/api/v1/transactions/{id}` | **admin** — soft delete |
| GET | `/api/v1/transactions/graph/stats` | user — fraud network stats |
| GET | `/api/v1/transactions/{uid}/graph-features` | user — graph features per user |
| GET | `/api/v1/transactions/{id}/embedding` | user — merchant embedding analysis |

### Alerts
| Method | Path | Auth |
|---|---|---|
| GET | `/api/v1/alerts` | user |
| POST | `/api/v1/alerts/{id}/review` | user |
| POST | `/api/v1/alerts/{id}/false-positive` | user |
| POST | `/api/v1/alerts/{id}/revert` | user |

### Reports · Monitoring · Audit
| Method | Path | Auth |
|---|---|---|
| GET | `/api/v1/transactions/{id}/report` | user — LLM report (200 / 202 / 404) |
| GET | `/api/v1/monitoring/drift` | user — drift analysis |
| GET | `/api/v1/audit/transactions/{id}` | user — decision trail |
| GET | `/api/v1/audit/analysts/{uid}` | **admin** — analyst activity |
| POST | `/api/v1/audit/export` | **admin** — export by date range |

Health: `GET /health`, `GET /api/v1/health`, `GET /api/v1/status` (public).

**Rate limits:** login & register 10/min · transactions 100/min · alerts 60/min.

## Project Structure

```
fraud-detector/
├── src/
│   ├── api/                # FastAPI: main, rate_limit, v1/ (auth, transactions, alerts, reports, monitoring, audit)
│   ├── core/               # config, database, redis, security + stream_publisher / stream_manager / stream_dlq
│   ├── models/             # 10 SQLAlchemy models (transaction, user, fraud_score, fraud_alert, llm_report,
│   │                       #   ml_model_run, audit_entry, shap_attribution, rule_metadata, base)
│   ├── schemas/            # Pydantic v2 schemas
│   ├── services/           # rule_engine, feature_engine, ml_model, ensemble, shap_service,
│   │                       #   graph_service, merchant_embedding_service, velocity_store,
│   │                       #   llm, drift_service, monitoring, audit, transaction, auth
│   └── workers/            # llm_worker, shap_worker, embedding_worker (Redis Streams consumers)
├── frontend/               # React 19 + TS + Vite + Tailwind 4 (8 pages, 7 components, vitest + MSW)
├── tests/                  # unit + integration (846 backend tests)
├── scripts/                # init_db, create_admin, generate_synthetic_data, train_xgboost_aligned
├── notebooks/              # PaySim exploration / training notebooks
├── docker/                 # Dockerfiles (api, frontend) + nginx.conf
├── alembic/                # migrations
└── docker-compose.yml      # 8 services
```

## Testing

```bash
# Backend (846 tests)
pytest tests/ -v --cov=src --cov-report=term
pytest tests/unit -v            # unit only
pytest tests/integration -v     # integration only (needs postgres + redis)

# Frontend
cd frontend && npm test         # vitest
```

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`), triggered on push/PR to `main`:

| Job | What it does |
|---|---|
| `backend-lint` | ruff + mypy |
| `backend-test` | pytest with PostgreSQL 16 + Redis 7 service containers |
| `frontend-lint-test` | ESLint + vitest |
| `frontend-build` | production build (after lint+test) |
| `docker-build` | Docker image smoke build (PRs only) |

## Environment Variables

See [.env.example](.env.example). Key settings (defaults from `src/core/config.py`):

```env
# Database
DB_USER=fraud
DB_PASSWORD=change_me_in_production
DB_NAME=fraud_detector
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0

# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:0.5b        # any local tag works
OLLAMA_TIMEOUT=30

# JWT
JWT_SECRET_KEY=change-me-in-production
JWT_ALGORITHM=HS256
JWT_EXP_MINUTES=15

# Ensemble weights
ENSEMBLE_RULE_WEIGHT=0.60
ENSEMBLE_ML_WEIGHT=0.25
ENSEMBLE_CONTEXT_WEIGHT=0.15

# Feature flags
FRAUD_DETECTION_ENABLED=true     # false → scoring endpoints return 503
VELOCITY_STORE_ENABLED=true

# CORS
FRONTEND_URL=http://localhost:3000
```

## Design Decisions

**Why 3 layers?** Rules are fast, deterministic and explainable — they capture known fraud patterns. ML catches what rules can't express. Context adapts the score to each user's baseline. If one layer fails, the others still produce a score.

**Why doesn't the LLM decide?** LLMs are non-deterministic and can hallucinate. No fraud-blocking decision should depend on one. The LLM's job is strictly to *explain* an already-made decision to a human analyst — value without risk.

**Why XGBoost?** Supervised, fast on CPU, and its tree structure plugs directly into `TreeExplainer` for per-transaction SHAP attributions.

**Why Redis Streams (not just lists)?** Consumer groups give at-least-once delivery, pending-message recovery (`XAUTOCLAIM`) and a dead-letter queue — the difference between "usually works" and an auditable pipeline.

**Why soft delete?** Transactions are financial records. `DELETE` flags rows as deleted; history stays queryable for audit and retraining.

## License

MIT

## Author

Portfolio project by [mikelrh-dev](https://github.com/mikelrh-dev) demonstrating:

- Hybrid architecture: deterministic rules + ML + local LLM (with strict separation of decision vs explanation)
- ML in production: feature engineering aligned between training and serving, SHAP explainability, drift monitoring, retraining triggers
- Reliable async pipelines: Redis Streams, consumer groups, retries, DLQ
- Security: JWT with refresh + blacklist, RBAC, rate limiting, immutable SHA-256 audit trail
- Testing discipline: 846 backend tests + frontend vitest suite (746 tests), 5-job CI
