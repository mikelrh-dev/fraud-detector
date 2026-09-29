---
title: XGBoost Serving
type: tool
status: active
created: 2026-08-29
updated: 2026-08-29
tags:
  - xgboost
  - ml
project: fraud-detector
sources:
  - src/services/ml_model.py
  - src/services/feature_engine.py
  - scripts/train_xgboost_aligned.py
aliases:
  - ML serving
source_repository: .
source_revision: 44829d2
source_paths:
  - src/services/ml_model.py
  - src/services/feature_engine.py
  - scripts/train_xgboost_aligned.py
---

# XGBoost Serving

## Context

`MLModelService` carga un artefacto joblib y convierte `predict_proba` en score 0–100.

## Key facts

Acepta modelo bare legacy o dict con `model` y `feature_names`. Comprueba shape y aplica una transformación suavizada de la probabilidad.

## Interfaces

Consume el vector de [[entities/ml-feature-contract]] y entrega `ml_score` a [[concepts/fraud-scoring-pipeline]].

## Interpretation

El fallback sin modelo preserva disponibilidad, pero no equivale a detección ML activa.

## Practical application

Entrenar con `scripts/train_xgboost_aligned.py`, cargar el artefacto y validar alineación antes de usarlo.

## Uncertainty

La calidad del score depende del artefacto instalado y de la distribución de datos; revisar [[entities/model-monitoring-contract]].

## Related

- [[concepts/fraud-explainability]]
- [[runbooks/testing-and-ci]]

## Sources

- `src/services/ml_model.py`
- `src/services/feature_engine.py`
- `scripts/train_xgboost_aligned.py`
