# Proposal: Three-Layer Fraud Detection

## Intent

Build a complete fraud detection system with three-layer architecture (Rule Engine + ML Anomaly Detection + LLM Explanatory Reports) to serve as a portfolio-grade technical showcase. The system must look and feel production-ready: JWT auth, ensemble scoring, audit trail, React dashboard, and model monitoring.

## Scope

### In Scope
- 7 new SQLAlchemy models (Transaction, FraudAlert, Rule, FraudScore, MLModelRun, LLMReport, User)
- Rule engine with code-based deterministic rules and configurable thresholds
- Isolation Forest ML pipeline with scikit-learn Pipeline (feature engineering + model)
- Ensemble weighted scoring (rules + ML + context) with dynamic amount-based thresholds
- Redis queue + async LLM worker for technical fraud reports
- JWT authentication with role-based access (admin/analyst)
- React + Vite + TypeScript dashboard with Recharts visualizations
- Evidently AI model monitoring (data drift, prediction drift)
- Kaggle Credit Card Fraud dataset + synthetic augmentation
- Full audit trail: every decision traceable (rules fired, ML score, ensemble score, LLM report, analyst actions)
- Analyst workflow: revert blocks, mark false positives

### Out of Scope
- DB-driven rule management (v1 uses code-based rules)
- Supervised ML models (XGBoost) — deferred until labeled data quality justifies it
- Stacking meta-model for ensemble — deferred
- Real-time streaming inference — batch + queue-based only
- Multi-tenant support

## Capabilities

> This section is the CONTRACT between proposal and specs phases.

### New Capabilities
- `fraud-detection`: Core fraud scoring pipeline — rule engine, ML anomaly detection, ensemble scoring, transaction CRUD, fraud alerts
- `llm-reporting`: Async LLM report generation via Redis queue — technical explanatory reports for fraud analysts
- `auth`: JWT authentication, user management, role-based access control (admin/analyst)
- `model-monitoring`: Evidently AI integration — drift detection, model performance tracking, retraining triggers
- `fraud-dashboard`: React frontend — transaction list, alert management, scoring visualizations, analyst actions (revert, false-positive)
- `audit-trail`: Immutable decision logging — traceable chain from rules → ML → ensemble → LLM → analyst actions

### Modified Capabilities
- None (no existing specs)

## Approach

Phased implementation (8 phases):
1. **Foundation** — Models, auth, test infrastructure
2. **Rule Engine** — Deterministic rules, scoring, transaction CRUD
3. **ML Pipeline** — Feature engineering, Isolation Forest, serialization
4. **Ensemble** — Weighted scoring, dynamic thresholds by amount tier
5. **LLM Worker** — Redis queue, async worker, report generation
6. **Monitoring** — Evidently drift detection, metrics endpoints
7. **Frontend** — React dashboard with visualizations
8. **Polish** — Rate limiting, docs, deployment config

Key: LLM only explains, never decides. Rule engine runs first. ML runs async. Ensemble combines scores. Analyst feedback loop captured for future retraining.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/models/` | New | 7 SQLAlchemy models with soft delete, timestamps |
| `src/schemas/` | New | Pydantic schemas for all endpoints |
| `src/services/` | New | RuleEngine, FeatureEngine, MLModelService, EnsembleScorer, LLMService |
| `src/workers/` | New | Async LLM worker, ML retraining worker |
| `src/api/` | Modified | New v1 endpoints: transactions, scoring, alerts, reports, auth |
| `src/core/` | Modified | JWT middleware, Redis connection, DB sessions |
| `requirements.txt` | Modified | scikit-learn, joblib, evidently, python-jose, passlib, numpy, pandas |
| `frontend/` | New | React + Vite + TS + Recharts + Zustand + React Query |
| `docker/` | Modified | Dockerfile.frontend, docker-compose updates |
| `tests/` | New | Full TDD suite (unit + integration) |
| `openspec/specs/` | New | 6 domain specs |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| RAM limits on Oracle Free Tier (24GB) | Medium | Train offline, serve serialized model; limit Ollama concurrency |
| Data leakage in feature pipeline | Low | Scikit-learn Pipeline enforces correct ordering |
| Class imbalance (0.17% fraud) | High | Precision-recall evaluation, not accuracy |
| LLM hallucination in reports | Medium | Structured prompt templates; LLM explains only |
| PR review budget exceeded (400 lines) | High | Chained PRs per phase; each phase independently reviewable |
| TDD with ML components | Medium | Test pipeline structure, features, scoring with fixed data |

## Rollback Plan

1. **Feature flag**: All fraud scoring behind `FRAUD_DETECTION_ENABLED` env var (default: false)
2. **Model rollback**: Keep previous serialized model (`model_vN.joblib`); revert symlink on failure
3. **Database**: All models have soft delete; migration rollback scripts included
4. **Frontend**: Standalone service; disable in docker-compose if needed
5. **Full rollback**: `git revert` the merge commit; no data loss (soft delete + audit trail)

## Dependencies

- Kaggle Credit Card Fraud Detection dataset (downloaded manually or via API)
- Ollama with Llama 3.2 3B model pulled
- Python 3.11+ with scikit-learn, joblib, evidently packages

## Success Criteria

- [ ] Rule engine scores transactions deterministically with 100% reproducibility
- [ ] Isolation Forest trained on Kaggle data, serialized, and loaded for inference
- [ ] Ensemble score combines rule + ML scores with configurable weights
- [ ] LLM worker generates technical reports within 10s via Redis queue
- [ ] JWT auth protects all endpoints; roles enforced (admin vs analyst)
- [ ] React dashboard displays transactions, alerts, scores, and allows analyst actions
- [ ] Evidently detects data drift and logs model run metrics
- [ ] Full audit trail: every decision traceable from rules → ML → ensemble → LLM → analyst
- [ ] All tests pass with ≥80% coverage
- [ ] ruff + mypy clean on all source code
