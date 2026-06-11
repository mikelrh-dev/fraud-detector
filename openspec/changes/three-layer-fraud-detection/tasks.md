# Tasks: Three-Layer Fraud Detection

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 2500-3500 (8 phases, 40+ files, full TDD suite) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Foundation+Auth) → PR 2 (Rule Engine+Ensemble) → PR 3 (ML+LLM) → PR 4 (Monitoring+Audit) → PR 5 (Frontend) → PR 6 (Polish+Docker) |
| Delivery strategy | ask-always |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Core infrastructure: models, config, DB, Redis, security, test fixtures | PR 1 | Base = feature/three-layer; independently testable |
| 2 | Rule engine + ensemble scoring + transaction CRUD + alerts | PR 2 | Base = PR 1 branch; core scoring pipeline |
| 3 | ML pipeline + LLM worker + report generation | PR 3 | Base = PR 2 branch; async components |
| 4 | Monitoring + audit trail + API wiring | PR 4 | Base = PR 3 branch; observability layer |
| 5 | React dashboard + auth integration | PR 5 | Base = PR 4 branch; frontend service |
| 6 | Docker config, rate limiting, docs, polish | PR 6 | Base = PR 5 branch; deployment ready |

## Phase 1: Foundation (Infrastructure, Models, Auth, Test Setup)

- [x] 1.1 Update `src/core/config.py` — Add JWT settings (secret, algorithm, exp), ensemble weights, threshold tiers dict, Ollama timeout, feature flag `FRAUD_DETECTION_ENABLED`
- [x] 1.2 Create `src/core/database.py` — Async SQLAlchemy engine, async_sessionmaker, Base declarative, `get_async_session` dependency
- [x] 1.3 Create `src/core/redis.py` — Redis async connection pool, `get_redis` dependency, queue helpers (LPUSH, BRPOP)
- [x] 1.4 Create `src/core/security.py` — JWT encode/decode with python-jose, bcrypt password hashing, token blacklist check in Redis
- [x] 1.5 Create `src/core/dependencies.py` — FastAPI deps: `get_db`, `get_redis`, `get_current_user`, `require_role(role)`
- [x] 1.6 Create `src/models/base.py` — BaseModel with UUID id, created_at, updated_at, soft_delete flag, deleted_at
- [x] 1.7 Create `src/models/user.py` — User(id, username, email, hashed_password, role, is_active)
- [x] 1.8 Create `src/models/transaction.py` — Transaction(id, amount, currency, merchant_name, card_last4, status, deleted_at)
- [x] 1.9 Create `src/models/fraud_score.py` — FraudScore(id, transaction_id FK, rule_score, ml_score, ensemble_score, threshold, classification)
- [x] 1.10 Create `src/models/fraud_alert.py` — FraudAlert(id, transaction_id FK, status, score, threshold, reviewed_by, reviewed_at)
- [x] 1.11 Create `src/models/rule.py` — RuleMetadata(id, name, weight, description, is_active)
- [x] 1.12 Create `src/models/llm_report.py` — LLMReport(id, transaction_id FK, report_text, model_name, status, generation_time_ms, retry_count)
- [x] 1.13 Create `src/models/ml_model_run.py` — MLModelRun(id, model_version, metrics JSON, status, drift_detected, created_at)
- [x] 1.14 Create `src/models/audit_entry.py` — AuditEntry(id, transaction_id FK nullable, user_id FK nullable, action_type, metadata JSON nullable, sha256_checksum) — immutable
- [x] 1.15 Update `src/models/__init__.py` — Export all model classes
- [x] 1.16 Create `src/schemas/auth.py` — LoginRequest, RegisterRequest, TokenResponse, UserResponse Pydantic schemas
- [x] 1.17 Create `src/services/auth.py` — register_user, login, verify_password, hash_password, token blacklist management
- [x] 1.18 Create `src/services/transaction.py` — create_transaction, get_transaction, list_transactions, soft_delete_transaction
- [x] 1.19 Create `tests/conftest.py` — pytest fixtures: async_test_db, test_client, mock_redis, test_user_factory, auth_headers
- [x] 1.20 Create `tests/test_auth.py` — Unit tests: password hashing, JWT encode/decode, token expiration, blacklist check
- [x] 1.21 Create `tests/test_models.py` — Unit tests: model creation, soft delete behavior, timestamp auto-set
- [x] 1.22 Update `src/api/main.py` — Add lifespan (DB init on startup), mount v1 router placeholder

## Phase 2: Rule Engine + Ensemble + Transaction Scoring

- [x] 2.1 Create `src/services/rule_engine.py` — RuleEngine class with evaluate(transaction) → (rule_score, fired_rules); implement high_amount, high_velocity, unusual_merchant, card_mismatch rules
- [x] 2.2 Create `src/services/ensemble.py` — EnsembleScorer with combine(rule_score, ml_score, weights) → ensemble_score; get_threshold(amount) → dynamic tier lookup
- [x] 2.3 Create `src/schemas/transaction.py` — TransactionCreate, TransactionResponse, TransactionListResponse Pydantic schemas
- [x] 2.4 Create `src/schemas/scoring.py` — ScoreResponse(transaction_id, rule_score, ml_score, ensemble_score, threshold, classification, fired_rules, created_at)
- [x] 2.5 Create `src/schemas/alert.py` — AlertResponse, AlertListResponse, AlertActionRequest Pydantic schemas
- [x] 2.6 Create `src/api/v1/__init__.py` — Empty init (already exists)
- [x] 2.7 Create `src/api/v1/router.py` — APIRouter aggregation: include auth, transactions, alerts, reports, monitoring, audit routers (reports/monitoring/audit as TODOs)
- [x] 2.8 Create `src/api/v1/transactions.py` — POST /transactions (create+score), GET /transactions/{id}, GET /transactions (list), DELETE /transactions/{id} (admin only)
- [x] 2.9 Create `src/api/v1/auth.py` — POST /auth/login, POST /auth/register, POST /auth/refresh, POST /auth/logout
- [x] 2.10 Create `src/api/v1/alerts.py` — GET /alerts, POST /alerts/{id}/review, POST /alerts/{id}/false-positive, POST /alerts/{id}/revert
- [x] 2.11 Create `tests/test_rule_engine.py` — Unit tests: single rule fires, multiple rules, no rules, determinism, score cap at 100
- [x] 2.12 Create `tests/test_ensemble.py` — Unit tests: weighted math exact (60*0.4+80*0.6=72), threshold tiers (low=70, high=50), classification logic
- [x] 2.13 Create `tests/test_transaction_api.py` — Integration tests: CRUD + scoring pipeline, 422 on invalid payload, soft delete excludes from list
- [x] 2.14 Create `tests/test_auth_api.py` — Integration tests: register→login→protected access→refresh→logout→token rejected, role enforcement 403

## Phase 3: ML Pipeline + LLM Worker

- [x] 3.1 Create `src/services/feature_engine.py` — Scikit-learn Pipeline for feature extraction from transaction; fixed-dimensionality output
- [x] 3.2 Create `src/services/ml_model.py` — MLModelService: load serialized IsolationForest, predict(transaction) → ml_score (0-100), handle missing model gracefully
- [x] 3.3 Create `src/services/llm.py` — LLMService: async Ollama client wrapper, build_prompt(score_breakdown) → structured prompt, generate_report() with 15s timeout
- [x] 3.4 Create `src/workers/llm_worker.py` — Async Redis consumer: BRPOP from "fraud:reports", call Ollama, persist LLMReport, retry with exponential backoff (max 3)
- [x] 3.5 Create `src/schemas/report.py` — ReportResponse(transaction_id, report_text, model_name, status, generation_time_ms) Pydantic schema
- [x] 3.6 Create `src/api/v1/reports.py` — GET /transactions/{id}/report → 200 (completed), 202 (pending), 200 (failed with error details)
- [x] 3.7 Create `tests/test_feature_engine.py` — Unit tests: feature extraction consistency, fixed dimensionality, deterministic output for same input
- [x] 3.8 Create `tests/test_ml_model.py` — Unit tests: score with serialized mock model, missing model returns 0 with warning, score range 0-100
- [x] 3.9 Create `tests/test_llm_service.py` — Unit tests: prompt template contains all scores/rules, timeout handling, service unavailable retry
- [x] 3.10 Create `tests/test_llm_worker.py` — Integration tests: enqueue→consume→mock Ollama→persist report, retry logic, max retries exhausted

## Phase 4: Monitoring + Audit Trail + Integration

- [x] 4.1 Create `src/services/monitoring.py` — MonitoringService: drift detection (numpy PSI), compute_metrics(), track_model_run(), check_retraining_trigger()
- [x] 4.2 Create `src/services/audit.py` — AuditService: create_entry with SHA-256 checksum, query by transaction/analyst, export
- [x] 4.3 Create `src/schemas/monitoring.py` — DriftReportResponse, ModelRunResponse, DashboardMetricsResponse, ReferenceDataRequest
- [x] 4.4 Create `src/schemas/audit.py` — AuditEntryResponse, AuditListResponse, AuditExportResponse, AuditExportRequest
- [ ] 4.5 Not needed — monitoring is synchronous/on-demand for v1
- [x] 4.6 Create `src/api/v1/monitoring.py` — GET /monitoring/drift, /metrics, /dashboard, POST /monitoring/reference-data (admin)
- [x] 4.7 Create `src/api/v1/audit.py` — GET /audit/transactions/{id}, /audit/analysts/{id} (admin), POST /audit/export (admin)
- [x] 4.8 Wire scoring pipeline to audit — In transactions.py, after scoring call AuditService.create_entry with full chain
- [x] 4.9 Wire LLM worker to audit — In llm_worker.py, on success/failure create audit entry with model, generation_time, status
- [x] 4.10 Wire analyst actions to audit — In alerts.py, on review/false-positive/revert create audit entry with user_id, action_type, reason
- [x] 4.11 Create `tests/test_monitoring.py` — Unit tests: drift detection, metric computation, retraining trigger logic, edge cases
- [x] 4.12 Create `tests/test_audit.py` — Unit tests: checksum consistency, immutability, query by transaction/analyst, export format
- [x] 4.13 Create `tests/test_integration_pipeline.py` — E2E integration test: POST → score → audit chain (scoring + analyst actions + checksums)

## Phase 5: Frontend Dashboard

- [x] 5.1 Create `frontend/package.json` — React 19, Vite 6+, TypeScript, Recharts, Zustand, TanStack React Query, TailwindCSS v4
- [x] 5.2 Create `frontend/tsconfig.json` — Strict mode, path aliases (@/ → src/), target ES2022
- [x] 5.3 Create `frontend/vite.config.ts` — Vite config with React plugin, API proxy /api → localhost:8000, TailwindCSS v4 plugin
- [x] 5.4 Create `frontend/src/api/client.ts` — Axios instance: baseURL /api/v1, JWT interceptor (localStorage), 401 → /login
- [x] 5.5 Create `frontend/src/api/auth.ts` — login(username, password), register, refresh, logout, JWT decode helper
- [x] 5.6 Create `frontend/src/api/transactions.ts` — listTransactions(filters), getTransaction(id), createTransaction(data), statusToClassification helper
- [x] 5.7 Create `frontend/src/api/alerts.ts` — listAlerts(filters), reviewAlert(id), markFalsePositive(id), revertBlock(id)
- [x] 5.8 Create `frontend/src/store/authStore.ts` — Zustand persist (localStorage), token + refreshToken + user derived from JWT, login/logout actions
- [x] 5.9 Create `frontend/src/pages/LoginPage.tsx` — Login form (usuario + contraseña), error/loading states, redirect to /dashboard
- [x] 5.10 Create `frontend/src/pages/DashboardPage.tsx` — Sidebar nav, header with user+logout, metric cards, ScoreHistogram, ScoreTrendChart, TransactionTable (last 10)
- [x] 5.11 Create `frontend/src/pages/TransactionDetail.tsx` — Detail panel: all fields, risk score bar, LLM report with pending/complete/failed states + polling
- [x] 5.12 Create `frontend/src/pages/AlertsPage.tsx` — Alerts table with status badges, review/false-positive/revert actions, confirmation modal with reason
- [x] 5.13 Create `frontend/src/components/ScoreHistogram.tsx` — Recharts BarChart (buckets 0-100), color-coded by fraud score zones
- [x] 5.14 Create `frontend/src/components/ScoreTrendChart.tsx` — Recharts LineChart, daily average over 7 days, buildDailyAverages helper
- [x] 5.15 Create `frontend/src/components/TransactionTable.tsx` — Paginated table, sortable (amount, score, date), filterable by classification, color-coded badges
- [x] 5.16 Create `frontend/index.html` — Vite entry, dark theme meta tag, title "Fraud Detector"
- [x] 5.17 Create `frontend/src/main.tsx` — React root: StrictMode, QueryClientProvider (30s staleTime, retry 1), BrowserRouter
- [x] 5.18 Create `frontend/src/App.tsx` — Route definitions: /login, /dashboard, /transactions/:id, /alerts; ProtectedRoute redirects to /login if unauthenticated
- [x] 5.19 Create `frontend/eslint.config.js` — ESLint flat config for TypeScript + React hooks
- [x] 5.20 Create `frontend/src/index.css` — TailwindCSS v4 @import + custom theme colors (fraud classification colors, slate palette)

## Phase 6: Polish, Docker, Deployment

- [x] 6.1 Update `requirements.txt` — Add scikit-learn, joblib, evidently, python-jose, passlib, numpy, pandas, bcrypt
- [x] 6.2 Create `docker/Dockerfile.api` — Multi-stage Python 3.11: deps build, source copy, uvicorn CMD
- [x] 6.3 Create `docker/Dockerfile.frontend` — Node 20 build stage, nginx serve stage
- [x] 6.4 Update `docker-compose.yml` — Add api service, frontend service, llm-worker service, model volume, healthchecks
- [x] 6.5 Add feature flag guard — All scoring endpoints return 503 if `FRAUD_DETECTION_ENABLED=false`
- [x] 6.6 Add rate limiting — FastAPI slowapi or middleware for /auth/login (10 req/min), /api/v1/transactions (100 req/min)
- [x] 6.7 Run `ruff check src/` — Fix all lint errors
- [x] 6.8 Run `mypy src/` — Fix all type errors
- [x] 6.9 Run `pytest tests/ -v --cov=src` — Verify ≥80% coverage, all tests pass
- [x] 6.10 Update `README.md` — Setup instructions, architecture diagram, API docs link, dashboard access
