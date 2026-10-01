# 🛡️ Fraud Detector Hybrid

[![CI](https://github.com/mikelrh-dev/fraud-detector/actions/workflows/ci.yml/badge.svg)](https://github.com/mikelrh-dev/fraud-detector/actions/workflows/ci.yml)

**English** | [Español](README.es.md)

> 📖 **Read the [technical case study](case-study/en/index.html)** — an 11-chapter walkthrough of how this system works, every number traced to a real artifact.
>
> 🧭 **Technical wiki:** [browse the developer wiki](docs/wiki/index.md) for the system model, architecture, scoring pipeline, workers, ML and operations.

Hybrid fraud detection system for financial transactions. A **deterministic rule engine** (7 rules), a **supervised ML model** (XGBoost) and a **local LLM** (Ollama) that writes explanatory reports for analysts — the LLM never decides, it only explains.

> **On the ML model, plainly:** it is trained on a **synthetic corpus** of fraud archetypes generated in this repo — not on PaySim, and not on bank data. The rules decide; the ML layer contributes a calibrated 25%. The measured numbers, and the limits we know about, are in [What the model does and does not do](#what-the-model-does-and-does-not-do).

Every transaction gets a 0–100 risk score, a classification (`legitimate | review | fraud`), SHAP feature attributions, and — when flagged — an async LLM-generated technical report.

## Highlights

- **3-layer ensemble scoring**: rules 60% + ML 25% + context 15%, with dynamic fraud thresholds by amount tier
- **7 deterministic rules** covering amount, velocity, merchant risk, off-hours patterns and fraud-ring proximity
- **XGBoost** with 10 engineered features, graceful degradation (system works with `ml_score = 0` if no model is loaded)
- **SHAP explainability**: top-5 feature contributions persisted per transaction
- **Fraud ring detection**: directed graph (NetworkX), flags users within 2 hops of a known fraudster
- **Merchant spoofing detection**: sentence-transformers embeddings + cosine similarity (catches `AMAZ0N_STORE` → `Amazon`)
- **Redis Streams** with consumer groups, pending-message recovery (`XAUTOCLAIM`) and a dead-letter queue
- **Model monitoring**: PSI data drift, automatic retraining triggers (F1 < 0.7 or drift > 30) — implemented, not yet exercised against a populated reference
- **Immutable audit trail** with SHA-256 checksums on every scoring decision and analyst action
- **JWT auth** (access + refresh + blacklist), role-based access (user/admin), per-route rate limiting
- **React 19 dashboard** with score trends, SHAP cards and alert workflow
- **1259 backend tests** (unit + integration) and 789 frontend tests, CI with 5 jobs (ruff, mypy, pytest, ESLint, vitest, Docker smoke build). `pytest tests/ -q` reports the backend figure as **1221 passed, 30 skipped, 8 xfailed**; `cd frontend && npm test` reports the frontend figure as 789 passed

## Architecture

```mermaid
flowchart TB
    FE["React 19 Dashboard"] -->|"REST + JWT"| API["FastAPI (async)"]

    API --> RE["Layer 1 · Rule Engine<br/>7 deterministic rules"]
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

**Stack:** Python 3.11 · FastAPI · PostgreSQL 16 (asyncpg) · Redis 7 (Streams) · XGBoost · SHAP · NetworkX · sentence-transformers · Ollama · React 19 + TypeScript + Vite + Tailwind 4 · Docker Compose (8 services)

## How a Transaction Is Scored

```
risk_score = 0.60 × rule_score + 0.25 × ml_score + 0.15 × context_score
```

Classification against a dynamic threshold that tightens for larger amounts:

| Amount tier | Fraud threshold |
|---|---|
| $0 – $1,000 | > 70 |
| $1,001 – $10,000 | > 50 |
| $10,001 – $50,000 | > 45 |
| $50,001+ | > 40 |

A score must be **strictly greater** than the tier threshold to be `fraud`; the tiers are
half-open `[min, max)` so there is no gap at a boundary. `review` starts at 75% of the tier
threshold (`>=`, since that is the start of the band). Everything below is `legitimate`.

### Layer 1 — Rule Engine (deterministic, capped at 100)

| Rule | Weight | Trigger |
|---|---|---|
| `high_amount` | 35 | amount > $1,000 |
| `velocity_burst` | 30 | > 1 txn in 5 min in a risky category |
| `high_velocity` | 25 | > 3 txns in 5 minutes |
| `off_hours_crypto` | 25 | night hours (0–6) **and** an adversarial category |
| `unusual_merchant` | 20 | blacklisted merchant **or** adversarial category **or** regulated category with corroboration |
| `near_fraud` | 15 | user ≤ 2 hops from a known fraudster (graph) |
| `unusual_hours` | 10 | txn between 00:00–06:00 |

The total is the sum of fired weights, capped at 100.

Merchant categories are tiered, and the tier decides how much the category alone is worth
(`src/core/ml_constants.py`):

- **Adversarial** — the category is itself evidence of risk, so `off_hours_crypto` and
  `unusual_merchant` fire on it alone: `cryptocurrency`, `gambling`, `casino`, `adult`
  (`crypto` and `btc` are alias spellings that normalise to `cryptocurrency`).
- **Regulated** — normal for the business, so it only counts as *corroboration*:
  `unusual_merchant` fires on `pharmacy` or `money_transfer` only when paired with velocity,
  a night hour, or a blacklisted merchant.
- **Risk set** (`MERCHANT_RISK_CATEGORIES`, 8 spellings — the union of both tiers) — what
  `velocity_burst` and the feature engine test against.

The split is deliberate. One flat "risky" list charged 20 rule points to every pharmacy
purchase and every remittance with no evidence at all.

### Layer 2 — ML Model (XGBoost)

10 features: `amount`, `amount_vs_user_avg`, `amount_vs_user_std`, `tx_count_last_5min`, `tx_count_last_1h`, `hour_of_day`, `is_weekend`, `merchant_risk_level`, `is_crypto`, `amount_round_number`.

`predict_proba` is scaled straight to 0–100 (`probability * 100.0`) and calibrated with `CalibratedClassifierCV(method="sigmoid", cv=5)` against the corpus's real 1.00% prior — 502 frauds in 50,000 transactions, which the calibrator records as `calibration_prior=0.010050` — so a score is a probability against that base rate, not a raw margin. If no model file is present, the API keeps working with `ml_score = 0`.

### Layer 3 — Context

User-level signals (recent transaction velocity) contribute the remaining 15%, computed in `scoring_service.py` as `min(recent_txns / 10 × 100, 100)` and passed to the ensemble explicitly.

### What the model does and does not do

Every figure below is printed by `python scripts/evaluate_model.py`, on the 10,000-row test split that is held out of both training and SMOTE. The rows come from that split's own output block, not from a hand-kept total.

| | |
|---|---|
| Held-out ROC-AUC / PR-AUC | 0.9248 / 0.7740 |
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
| This model at the best flat threshold (15.50) | 0.0289 |

Two things fall out of that table. First, **the cost-optimal threshold is not a constant of the model** — across ratios from 1 to 500 it moves from 75.00 down to 0.20, two orders of magnitude, so every belief about cost gets a different operating point. That is why the script prints a sweep instead of a recommendation. The tiered production point is within 0.0015 of the swept optimum at this ratio, and the sweep is cheaper at every ratio tested.

Second, the model has to beat *both* no-model policies, and on this corpus it does at every ratio the script tests — 0.0289 against a floor of 0.1000 at ratio 10, and still 0.7787 against the 0.9900 flag-everything bar at 500×. No AUC tells you that; the cost arithmetic does.

`breakeven_cost_ratio` is **99.0** — above that, flagging every transaction becomes as cheap as flagging none, because at ~1% prevalence a miss has to be that much more expensive than wasted analyst time. It is a property of the base rate alone: the same number whether the model is excellent or inverted, which is exactly why it cannot be used as evidence either way. The model still clears the flag-everything bar at 500×, and the report says so rather than implying the opposite.

**Known simplification, printed in the report:** the swept optimum is a flat threshold while production uses an amount-tiered one, so the comparison is approximate. The volume of 50,000 transactions/day is an assumption that scales every per-day number. And the counts come from a synthetic corpus — so this is arithmetic, not evidence. The model's real-world cost per transaction is **unknown**, and this is the arithmetic to have ready the day a labelled corpus exists.

## Explainability, Monitoring & Audit

- **SHAP** (`TreeExplainer` over XGBoost): top-5 feature attributions computed async per scored transaction, rendered in the dashboard.
- **Drift detection**: a custom PSI implementation (reference vs current distributions). `GET /api/v1/monitoring/drift`.
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
docker compose exec ollama ollama pull llama3.2:1b  # default LLM (configurable via OLLAMA_MODEL)

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

Create your first user and log in. `RegisterRequest` requires `username`
(letters, digits, `_`, `.`, `-`), `email`, and a `password` of at least 8
characters that is neither a common password nor a fragment of the username or
the email. `role` defaults to `analyst`, and self-service registration cannot
grant anything else:

```bash
curl -X POST http://localhost:3000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","email":"demo@example.com","password":"Str0ng-Pass-2026","role":"analyst"}'

curl -X POST http://localhost:3000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"Str0ng-Pass-2026"}'
```

Every endpoint outside auth needs the `access_token` from that login as
`Authorization: Bearer <token>`; without it they return 401.

> `scripts/create_admin.py` prints a ready-to-run SQL `INSERT` if you prefer to seed an admin directly.

### Local development

```bash
# Backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Required: Settings has three fields with no default (DB_PASSWORD, REDIS_PASSWORD,
# REDIS_URL), so the app cannot import until a .env exists.
cp .env.example .env

# Infrastructure only
docker compose up postgres redis ollama -d

python scripts/init_db.py    # create_all; the dev loop does not run alembic
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

`train_xgboost_aligned.py` trains on the exact `FeatureEngine` features used in production. (`scripts/train_model.py` trains a plain uncalibrated XGBoost baseline to diff against; it writes to its own `models/xgboost_reference_v1.joblib` and is not the served model.)

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
| GET | `/api/v1/transactions/graph/stats` | **admin** — whole-graph fraud network stats (403 without admin) |
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
| GET | `/api/v1/monitoring/dashboard` | user — dashboard aggregates |
| GET | `/api/v1/monitoring/metrics` | analyst + admin — ML run metrics |
| POST | `/api/v1/monitoring/reference-data` | **admin** — seed the drift reference window |
| GET | `/api/v1/audit/transactions/{id}` | user — decision trail |
| GET | `/api/v1/audit/analysts/{uid}` | **admin** — analyst activity |
| POST | `/api/v1/audit/export` | **admin** — export by date range |

Health, all public: `GET /health` (static liveness) · `GET /health/ready` (runs `SELECT 1`
against Postgres and `PING` against Redis — this is what the compose healthcheck calls) ·
`GET /health/workers` (per-worker topology) · `GET /api/v1/health` · `GET /api/v1/status`.

**Rate limits** (fixed 60s window, per client IP, fail-open if Redis is down):

| Route | Limit |
|---|---|
| `/api/v1/auth/login`, `/api/v1/auth/register` | 10/min |
| `/api/v1/auth/refresh` | 5/min |
| `/api/v1/auth/logout` | 20/min |
| `/api/v1/transactions` | 100/min |
| `/api/v1/alerts` | 60/min |
| `/api/v1/audit` | 60/min |
| `/api/v1/monitoring` | 30/min |

`/metrics` reports worker topology with no auth. It is deliberately **not** proxied by
nginx, so it is unreachable from outside the compose network — see ADR-006.

## Project Structure

```
fraud-detector/
├── src/
│   ├── api/                # FastAPI: main, rate_limit, v1/ (auth, transactions, alerts, reports, monitoring, audit)
│   ├── core/               # config, database, redis, security + stream_publisher / stream_manager / stream_dlq
│   ├── models/             # 12 SQLAlchemy models (transaction, user, fraud_score, fraud_alert, llm_report,
│   │                       #   ml_model_run, audit_entry, shap_attribution, rule, drift_reference,
│   ├── schemas/            # Pydantic v2 schemas
│   ├── services/           # rule_engine, feature_engine, ml_model, ensemble, shap_service,
│   │                       #   graph_service, merchant_embedding_service, velocity_store,
│   │                       #   llm, drift_service, monitoring, audit, transaction, auth
│   └── workers/            # llm_worker, shap_worker, embedding_worker (Redis Streams consumers)
├── frontend/               # React 19 + TS + Vite + Tailwind 4 (8 pages, 24 components, vitest + MSW)
├── tests/                  # unit + integration (1259 backend tests)
├── scripts/                # init_db, create_admin, generate_synthetic_data, train_xgboost_aligned
├── notebooks/              # PaySim exploration / training notebooks
├── docker/                 # Dockerfiles (api, frontend) + nginx.conf
├── alembic/                # migrations
└── docker-compose.yml      # 8 services
```

## Testing

```bash
# Backend (1259 tests — `pytest tests/ -q` prints 1221 passed, 30 skipped, 8 xfailed)
pytest tests/ -v --cov=src --cov-report=term
pytest tests/unit -v            # unit only
pytest tests/integration -v     # integration only — runs against MOCKED db and redis (see conftest)

# Frontend
cd frontend && npm test         # vitest
```

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`), triggered on push/PR to `main`, `master` or `enhanced-proyecto`:

| Job | What it does |
|---|---|
| `backend-lint` | ruff + mypy |
| `backend-test` | pytest with PostgreSQL 16 + Redis 7 service containers |
| `frontend-lint-test` | ESLint + vitest |
| `frontend-build` | production build (after lint+test) |
| `docker-build` | builds the backend and frontend images (push + PR). Builds only — it never runs them |

## Environment Variables

[.env.example](.env.example) is the authoritative list — copy it and adjust, rather than
hand-assembling one:

```bash
cp .env.example .env
```

Three settings have **no default** in `Settings` and the app will not start without them:
`DB_PASSWORD`, `REDIS_PASSWORD` and `REDIS_URL`. Under compose, `REDIS_PASSWORD` is also
injected into `REDIS_URL` for you.

```env
# No default — the app refuses to boot without these three
DB_PASSWORD=...
REDIS_PASSWORD=...
REDIS_URL=redis://:...@localhost:6379/0

# Defaults to a fresh secrets.token_urlsafe(32) on every process start.
# Unset is fine for local dev; production must set it explicitly or boot fails.
JWT_SECRET_KEY=

# ENVIRONMENT (alias: API_ENV) silently selects the production branch,
# which turns CORS from "*" to FRONTEND_URL only, disables /docs and
# /openapi.json, and requires JWT_SECRET_KEY + API_SECRET_KEY to be injected.
ENVIRONMENT=development

# Only safe behind a proxy that OVERWRITES X-Real-IP / X-Forwarded-For.
# docker/nginx.conf overwrites them, so compose sets this to true itself.
# Set it false if you expose the API port directly, or clients can spoof
# their IP and bypass the per-IP rate limiter.
TRUST_PROXY_HEADERS=false
```

Everything else has a real default in `src/core/config.py`: `DB_USER=fraud`,
`DB_NAME=fraud_detector`, `DB_HOST=localhost`, `DB_PORT=5432`, `OLLAMA_HOST=http://localhost:11434`,
`OLLAMA_MODEL=llama3.2:1b`, `OLLAMA_TIMEOUT=30`, `JWT_ALGORITHM=HS256`, `JWT_EXP_MINUTES=15`,
the ensemble weights `0.60 / 0.25 / 0.15`, `FRAUD_DETECTION_ENABLED=true`,
`VELOCITY_STORE_ENABLED=true` and `FRONTEND_URL=http://localhost:3000`.

Those are the defaults for running the API on your own machine. Under compose
the service names replace the host ones — `DB_HOST=postgres`,
`REDIS_URL=redis://:…@redis:6379/0`, `OLLAMA_HOST=http://ollama:11434` — and
nothing except port 3000 is reachable from the host.

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
- Testing discipline: 1259 backend tests (`pytest tests/ -q`) + frontend vitest suite (789 tests), 5-job CI
