---
title: Fraud Detector Concept Table
type: synthesis
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - index
project: fraud-detector
sources:
  - src/
aliases:
  - concept map
source_repository: .
source_revision: 44829d2
source_paths:
  - src/
---

# Fraud Detector Concept Table

| Concepto | Página | Tipo | Fuente primaria |
|---|---|---|---|
| sistema híbrido | [[concepts/hybrid-fraud-detection]] | concept | `src/services/scoring_service.py` |
| scoring | [[concepts/fraud-scoring-pipeline]] | concept | `src/services/scoring_service.py` |
| clasificación | [[concepts/risk-classification]] | concept | `src/services/ensemble.py` |
| sesiones JWT | [[concepts/jwt-session-lifecycle]] | concept | `src/core/security.py` |
| auditoría | [[concepts/immutable-audit-trail]] | concept | `src/services/audit.py` |
| entrega at-least-once | [[concepts/at-least-once-processing]] | concept | `src/core/stream_dlq.py` |
| features ML | [[entities/ml-feature-contract]] | entity | `src/services/feature_engine.py` |
| eventos | [[entities/redis-event-contracts]] | entity | `src/api/v1/transactions.py` |
| workers | [[runbooks/worker-recovery]] | runbook | `src/workers/` |
| API | [[tools/fraud-detector-api-contract]] | tool | `src/api/v1/` |
| monitorización | [[entities/model-monitoring-contract]] | entity | `src/services/monitoring.py` |
