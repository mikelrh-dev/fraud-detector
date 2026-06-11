# Exploration: Three-Layer Fraud Detection

## Current State

The project is in **scaffolding phase** with minimal implementation:

- **API layer**: `src/api/main.py` — 2 endpoints (`/health`, `/api/v1/status`), CORS configured
- **Config**: `src/core/config.py` — pydantic-settings with DB, Redis, Ollama, frontend URLs
- **Infrastructure**: `docker-compose.yml` — PostgreSQL 16, Redis 7, Ollama, frontend service defined
- **Empty directories**: `src/models/`, `src/schemas/`, `src/services/`, `src/workers/`
- **No tests**: `tests/unit/` and `tests/integration/` are empty (only `__init__.py`)
- **No frontend**: `frontend/` directory does not exist
- **No openspec specs**: `openspec/specs/` is empty
- **PLAN.md**: 21-day development plan exists, describes a simpler 2-layer architecture (rules + LLM only)

The current PLAN.md describes a **2-layer** system (rules + LLM). The change intent expands this to a **3-layer** system (rules + ML model + LLM) with ensemble scoring, model monitoring, dataset integration, and a React dashboard.

## Affected Areas

- `src/models/` — New SQLAlchemy models: Transaction, FraudAlert, Rule, FraudScore, MLModelRun, LLMReport, User
- `src/schemas/` — Pydantic request/response schemas for all new endpoints
- `src/services/` — RuleEngine, FeatureEngine, MLModelService, EnsembleScorer, LLMService
- `src/workers/` — Async LLM worker consuming Redis queue, ML model retraining worker
- `src/api/` — New endpoints: transactions CRUD, fraud scoring, alerts, reports, model management, auth
- `src/core/` — Database session, Redis connection, JWT auth middleware
- `requirements.txt` — New dependencies: scikit-learn, joblib, evidently, python-jose, passlib, numpy, pandas
- `frontend/` — Entire React application (new directory)
- `docker/` — Dockerfile.frontend (new)
- `tests/` — Full test suite (unit + integration)
- `openspec/specs/` — Main specs for fraud-detection, auth, monitoring domains

## Approaches

### 1. Layer 1 — Rule Engine

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **Database-driven rules** (rules stored in PostgreSQL, loaded at startup) | Admins can modify rules without code changes; auditable; versionable | Slight startup latency; needs cache invalidation | Medium |
| **Code-based rules** (Python classes/functions) | Fastest execution; type-safe; testable | Requires code deployment to change rules; less flexible | Low |
| **Hybrid: code-based base rules + DB overrides** | Best of both: safe defaults + runtime customization | More complex architecture | Medium-High |

**Recommendation**: Start with **code-based rules** for v1. The system needs to be stable before adding runtime rule management. DB-driven rules can be added later as an enhancement.

### 2. Layer 2 — ML Model (Anomaly Detection)

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **Isolation Forest** (scikit-learn) | Fast training; handles high dimensions; no labeled data needed; interpretable anomaly scores | Assumes features are independent; struggles with correlated features | Medium |
| **Autoencoder** (neural network) | Captures complex non-linear patterns; handles correlated features | Needs more data; harder to debug; slower inference; requires GPU for training | High |
| **One-Class SVM** | Good for small datasets; mathematically rigorous | O(n²) to O(n³) training; doesn't scale well; hard to tune | Medium |
| **XGBoost/LightGBM** (supervised, if labeled data available) | Highest accuracy with labeled data; fast inference | Requires labeled fraud/legitimate data; supervised learning needs quality labels | Medium |

**Recommendation**: **Isolation Forest** for v1. It's the best fit for unsupervised anomaly detection with the Kaggle dataset. It's fast, explainable, and serializes cleanly with joblib. If labeled data becomes available, XGBoost can be added as a parallel model in the ensemble.

### 3. Layer 3 — LLM (Explanatory Reports)

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **Redis queue + async worker** (current architecture) | Non-blocking; scalable; retry-friendly | More infrastructure; eventual consistency | Medium |
| **Direct API call** (synchronous) | Simpler; immediate results | Blocks API response; poor UX; timeout risk | Low |
| **Background task** (FastAPI BackgroundTasks) | Simple; no Redis needed | No retry; lost on restart; no queue visibility | Low |

**Recommendation**: **Redis queue + async worker** — already in the architecture decision. The LLM is slow (3-5s for Llama 3.2 3B), so queue-based processing is mandatory for API responsiveness.

### 4. Ensemble Scoring Strategy

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **Weighted average** (e.g., 40% rules + 40% ML + 20% context) | Simple; tunable; explainable | Weights are arbitrary; may not capture interactions | Low |
| **Stacking meta-model** (train a classifier on layer outputs) | Learns optimal combination; adapts to data | Needs labeled data; adds another model to maintain | High |
| **Rule-gated** (rules first, ML only if rules are uncertain) | Efficient; ML used only when needed | May miss anomalies that rules don't flag | Medium |

**Recommendation**: **Weighted average** for v1. It's simple, explainable, and tunable. The weights can be stored in config and adjusted based on precision/recall analysis. Stacking can be added later if labeled data quality justifies it.

### 5. Feature Engineering Pipeline

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **Scikit-learn Pipeline** (ColumnTransformer + custom transformers) | Prevents data leakage; serializable; consistent train/inference | Steeper learning curve for custom transformers | Medium |
| **Pandas-based preprocessing** | Flexible; easy to debug | Risk of train/test leakage; harder to serialize; inconsistent inference | Low |
| **Feature store** (dedicated service) | Reusable; versioned; auditable | Overkill for v1; adds infrastructure | High |

**Recommendation**: **Scikit-learn Pipeline**. It prevents the #1 ML mistake (data leakage), serializes cleanly with joblib alongside the model, and ensures identical transformations during training and inference.

### 6. Model Monitoring

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **Evidently AI** | 100+ built-in metrics; drift detection; Grafana integration; open-source | Requires reference dataset; adds dependency | Medium |
| **Custom metrics** (hand-coded) | Full control; no dependencies | Reinventing the wheel; easy to miss edge cases | Medium |
| **MLflow** | Full ML lifecycle; experiment tracking; model registry | Heavy infrastructure; overkill for single model | High |

**Recommendation**: **Evidently AI**. It's purpose-built for drift detection, has excellent Grafana integration, and covers the exact monitoring needs (data drift, prediction drift, model performance).

### 7. Dataset Integration

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **Kaggle dataset + synthetic augmentation** | Real patterns + controlled edge cases; good coverage | Synthetic data may not match real distribution | Medium |
| **Kaggle dataset only** | Real patterns; simpler | Limited coverage; no control over edge cases | Low |
| **Synthetic data only** (Faker + rules) | Full control over scenarios; reproducible | May not capture real-world complexity | Low |

**Recommendation**: **Kaggle dataset + synthetic augmentation**. The Kaggle Credit Card Fraud Detection dataset provides real transaction patterns. Synthetic data fills gaps (edge cases, new fraud patterns, merchant risk scenarios). Use the Kaggle data for training/validation and synthetic data for stress testing.

### 8. Frontend Architecture

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **React + Vite + TypeScript + Recharts** | Fast dev; type-safe; good charting; matches PLAN.md | More boilerplate than simpler alternatives | Medium |
| **React + Next.js** | SSR; routing; full-stack | Overkill for a dashboard; adds complexity | High |
| **HTMX + Jinja2** (server-rendered) | Simple; no SPA complexity; fast | Less interactive; harder to build real-time dashboards | Low |

**Recommendation**: **React + Vite + TypeScript + Recharts** — matches the existing PLAN.md and docker-compose setup. Add **Zustand** for state management (lighter than Redux) and **React Query** for API caching.

## Recommendation

### Phased Implementation Order

1. **Phase 1: Foundation** — Database models, core services skeleton, JWT auth, test infrastructure
2. **Phase 2: Rule Engine** — Deterministic rules, scoring, transaction CRUD endpoints
3. **Phase 3: ML Pipeline** — Feature engineering, Isolation Forest training, model serialization, scoring endpoint
4. **Phase 4: Ensemble** — Weighted scoring combining rules + ML, threshold management
5. **Phase 5: LLM Worker** — Redis queue, async worker, explanatory reports
6. **Phase 6: Monitoring** — Evidently integration, drift detection, metrics endpoints
7. **Phase 7: Frontend** — React dashboard with advanced visualizations
8. **Phase 8: Polish** — Rate limiting, documentation, deployment config

### Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Rule storage | Code-based (v1) | Stability first; DB-driven rules later |
| ML model | Isolation Forest | Best unsupervised fit; fast; explainable |
| LLM processing | Redis queue | Non-blocking; already in architecture |
| Ensemble | Weighted average | Simple, tunable, explainable |
| Feature pipeline | Scikit-learn Pipeline | Prevents data leakage; serializable |
| Monitoring | Evidently AI | Purpose-built; Grafana integration |
| Dataset | Kaggle + synthetic | Real patterns + controlled edge cases |
| Frontend | React + Vite + TS + Recharts | Matches PLAN.md; good ecosystem |

## Risks

1. **RAM constraints on Oracle Cloud Free Tier**: The PLAN.md mentions 4 cores / 24GB RAM. Isolation Forest training on the full Kaggle dataset (~285K rows, 30 features) needs ~500MB-1GB. Ollama Llama 3.2 3B needs ~2.5GB. Total should fit, but training + inference simultaneously could spike. **Mitigation**: Train models offline, serve serialized models; limit Ollama concurrency.

2. **Data leakage in feature engineering**: If train/test split happens after feature computation, the model will overfit. **Mitigation**: Use scikit-learn Pipeline to enforce correct ordering.

3. **Imbalanced dataset**: The Kaggle fraud dataset is ~0.17% fraud. Isolation Forest handles this naturally (it's unsupervised), but ensemble weights need careful tuning. **Mitigation**: Use precision-recall curves, not accuracy, for evaluation.

4. **LLM hallucination**: Llama 3.2 3B may generate incorrect explanations. **Mitigation**: Constrain prompts with structured templates; never let LLM decide — only explain.

5. **Model drift in production**: Fraud patterns change over time. Without retraining, the model degrades. **Mitigation**: Evidently drift detection triggers retraining alerts; schedule periodic retraining.

6. **400-line PR review budget**: This is a large change. The full implementation will likely exceed 2000+ lines. **Mitigation**: Use chained PRs per phase; each phase should be independently reviewable.

7. **TDD discipline**: Strict TDD with ML components is challenging. **Mitigation**: Test the pipeline structure, feature computation, and scoring logic deterministically. ML model training tests use mocked/fixed data with known outputs.

## Ready for Proposal

**Yes** — the exploration is complete. The orchestrator should proceed to `sdd-propose` with this analysis. The scope is well-defined, technical decisions have clear rationales, and risks are identified with mitigations.

Recommended next step: Create the SDD change proposal with the phased approach above, starting with Phase 1 (Foundation: models, auth, test infrastructure).
