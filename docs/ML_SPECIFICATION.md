# 🤖 ML Technical Specification

> **Documento técnico:** Especificación detallada de los modelos de Machine Learning
> **Fecha:** 2026-06-11
> **Autor:** OWL (Hermes) + Mikel

---

## 📊 Dataset Sintético

### Características del dataset

| Parámetro | Valor |
|---|---|
| **Total transacciones** | 100.000 |
| **Distribución** | 95% legítimas, 5% fraudulentas |
| **Features** | 50+ variables |
| **Target** | `is_fraud` (0/1) |
| **Split** | 80% train, 20% test |

### Features generadas

#### Features básicas (15)
- `amount` — monto de la transacción (10€ - 50.000€)
- `hour` — hora del día (0-23)
- `day_of_week` — día de la semana (0-6)
- `is_weekend` — booleano
- `merchant_category` — categoría (electronics, travel, gambling, retail, etc.)
- `merchant_risk_level` — nivel de riesgo del merchant (1-5)
- `card_country` — país de emisión de tarjeta
- `ip_country` — país de la IP
- `country_match` — booleano (card_country == ip_country)
- `device_age_days` — antigüedad del dispositivo
- `user_age_days` — antigüedad del usuario
- `transaction_count_24h` — transacciones del usuario en últimas 24h
- `transaction_count_7d` — transacciones del usuario en últimos 7d
- `avg_amount_30d` — promedio de montos últimos 30d
- `is_new_device` — booleano (dispositivo usado < 7 días)

#### Features de agregación (20)
- `amount_vs_avg_30d` — ratio amount / avg_amount_30d
- `amount_percentile` — percentil del monto respecto al usuario
- `time_since_last_transaction` — minutos desde última transacción
- `unique_countries_7d` — países únicos en últimos 7 días
- `unique_merchants_7d` — merchants únicos en últimos 7 días
- `max_amount_7d` — monto máximo en últimos 7 días
- `std_amount_30d` — desviación estándar de montos últimos 30d
- `transaction_frequency_score` — score de frecuencia anormal
- `amount_frequency_score` — score de monto anormal
- `distance_country_risk` — riesgo asociado al país
- `merchant_risk_score` — score de riesgo del merchant
- `user_risk_score` — score de riesgo histórico del usuario
- `device_risk_score` — score de riesgo del dispositivo
- `hour_risk_score` — score de riesgo por hora (3-6 AM = alto)
- `weekend_risk_score` — score de riesgo por fin de semana
- `amount_category_risk` — riesgo por categoría de monto
- `velocity_score` — velocidad de transacciones
- `geographic_anomaly_score` — anomalía geográfica
- `behavioral_anomaly_score` — anomalía comportamental
- `composite_risk_score` — score compuesto de features de riesgo

#### Features de interacción (10)
- `amount_x_new_device` — amount * is_new_device
- `amount_x_country_mismatch` — amount * (1 - country_match)
- `amount_x_high_risk_merchant` — amount * (merchant_risk_level > 3)
- `amount_x_unusual_hour` — amount * (hour < 6 or hour > 22)
- `velocity_x_amount` — transaction_count_24h * amount
- `country_x_device` — (1 - country_match) * is_new_device
- `merchant_x_amount` — merchant_risk_level * amount
- `user_history_x_amount` — user_age_days * amount
- `frequency_x_velocity` — transaction_count_24h * transaction_frequency_score
- `multi_anomaly_score` — suma de scores de anomalía

### Patrones de fraude inyectados

| Patrón | % del fraude | Descripción |
|---|---|---|
| **High amount + foreign country** | 25% | Transacción > 5.000€ en país no habitual |
| **Rapid succession** | 20% | 5+ transacciones en < 1 hora |
| **New device + high amount** | 15% | Dispositivo nuevo con monto > 3.000€ |
| **High risk merchant** | 15% | Merchant con risk_level = 5 |
| **Unusual hour + amount spike** | 10% | Transacción 3-6 AM con amount > 2x promedio |
| **Geographic anomaly** | 10% | País IP diferente al país tarjeta + monto alto |
| **Behavioral shift** | 5% | Cambio brusco en patrón de gasto del usuario |

---

## 🧠 Modelos de ML

### Modelo 1: XGBoost Classifier (Principal)

**Objetivo:** Clasificación binaria (fraude / no fraude)

#### Hiperparámetros

```python
{
    "max_depth": 6,
    "learning_rate": 0.1,
    "n_estimators": 200,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "gamma": 0.1,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "scale_pos_weight": 19,  # ratio 95:5 (clases desbalanceadas)
    "eval_metric": "auc",
    "early_stopping_rounds": 10
}
```

#### Métricas objetivo

| Métrica | Objetivo | Por qué |
|---|---|---|
| **AUC-ROC** | > 0.95 | Discriminación general |
| **F1-Score** | > 0.85 | Balance precision/recall |
| **Precision** | > 0.80 | Minimizar falsos positivos |
| **Recall** | > 0.90 | No dejar pasar fraude |
| **Accuracy** | > 0.95 | Exactitud general |

#### Feature Importance (esperada)

Top 10 features predictivas:
1. `amount_vs_avg_30d`
2. `country_match`
3. `merchant_risk_level`
4. `is_new_device`
5. `transaction_count_24h`
6. `hour_risk_score`
7. `amount`
8. `velocity_score`
9. `geographic_anomaly_score`
10. `user_risk_score`

#### Validación

- **Cross-validation:** 5-fold stratified
- **Métricas por fold:** AUC, F1, precision, recall
- **Curva ROC:** Visualización
- **Matriz de confusión:** Análisis de errores
- **Learning curves:** Detectar overfitting

---

### Modelo 2: Random Forest (Baseline)

**Objetivo:** Comparación con XGBoost

#### Hiperparámetros

```python
{
    "n_estimators": 200,
    "max_depth": 10,
    "min_samples_split": 5,
    "min_samples_leaf": 2,
    "class_weight": "balanced",
    "random_state": 42
}
```

#### Comparación con XGBoost

| Aspecto | XGBoost | Random Forest |
|---|---|---|
| Velocidad entrenamiento | Rápido | Más lento |
| Velocidad predicción | Muy rápido | Rápido |
| Manejo overfitting | Mejor | Peor |
| Interpretabilidad | Feature importance | Feature importance |
| Robustez | Alta | Alta |

**Decisión:** Usar XGBoost como modelo principal, Random Forest como baseline.

---

### Modelo 3: Isolation Forest (Anomalías)

**Objetivo:** Detectar transacciones anómalas no cubiertas por reglas o XGBoost

#### Hiperparámetros

```python
{
    "n_estimators": 100,
    "contamination": 0.05,  # esperamos 5% de anomalías
    "max_samples": "auto",
    "random_state": 42
}
```

#### Uso

- **No supervisado:** No usa target `is_fraud`
- **Score:** -1 (anomalía) o 1 (normal)
- **Integración:** Score de anomalía se combina con scores de reglas y XGBoost

#### Detección de casos edge

Isolation Forest detecta patrones que:
- No están en las reglas definidas
- No fueron vistos en el dataset de entrenamiento de XGBoost
- Son estadísticamente atípicos

---

## 🔄 Pipeline de Predicción

### Flujo completo

```python
def predict_fraud(transaction: Transaction) -> FraudPrediction:
    """
    Evalúa una transacción con los 3 modelos y combina scores.
    """
    # 1. Feature engineering
    features = feature_engineering_pipeline.transform(transaction)

    # 2. Motor de reglas (determinista)
    rules_score = rules_engine.evaluate(transaction)  # 0-100

    # 3. XGBoost (clasificación supervisada)
    xgb_prob = xgboost_model.predict_proba(features)[0][1]  # probabilidad fraude
    xgb_score = xgb_prob * 100  # 0-100

    # 4. Isolation Forest (detección de anomalías)
    iso_pred = isolation_forest.predict(features)  # -1 o 1
    iso_score = 100 if iso_pred == -1 else 0  # 0 o 100

    # 5. Combinación de scores
    final_score = (
        0.40 * rules_score +   # Motor de reglas
        0.40 * xgb_score +     # XGBoost
        0.20 * iso_score       # Isolation Forest
    )

    # 6. Decisión
    if final_score >= 80:
        decision = "BLOCK"
    elif final_score >= 60:
        decision = "REVIEW"
    else:
        decision = "APPROVE"

    return FraudPrediction(
        rules_score=rules_score,
        xgb_score=xgb_score,
        iso_score=iso_score,
        final_score=final_score,
        decision=decision,
        features_used=features.columns.tolist()
    )
```

### Pesos de combinación

| Modelo | Peso | Justificación |
|---|---|---|
| Motor de reglas | 40% | Determinista, explicabile, rápido |
| XGBoost | 40% | Aprende patrones complejos, alta precisión |
| Isolation Forest | 20% | Detecta anomalías no vistas, complementa |

**Nota:** Los pesos son configurables y se pueden ajustar según resultados en producción.

---

## 📁 Estructura de archivos ML

```
src/ml/
├── __init__.py
├── data_generator.py          # Generación de datos sintéticos
├── feature_engineering.py     # Pipeline de features
├── model_trainer.py           # Entrenamiento de modelos
├── model_evaluator.py         # Evaluación y métricas
├── model_loader.py            # Carga de modelos en memoria
└── models/
    ├── classifier.py          # XGBoost + Random Forest
    └── anomaly_detector.py    # Isolation Forest

models/
├── xgboost_fraud_v1.pkl       # Modelo XGBoost entrenado
├── random_forest_v1.pkl       # Modelo Random Forest (baseline)
├── isolation_forest_v1.pkl    # Modelo Isolation Forest
└── metadata.json              # Metadata de modelos (versiones, métricas)

data/
├── synthetic_transactions.csv # Dataset sintético completo
├── X_train.csv                # Features de entrenamiento
├── X_test.csv                 # Features de test
├── y_train.csv                # Target de entrenamiento
└── y_test.csv                 # Target de test

notebooks/
├── 01_data_exploration.ipynb  # EDA del dataset
├── 02_feature_engineering.ipynb  # Desarrollo de features
├── 03_model_training.ipynb    # Entrenamiento y tuning
└── 04_model_evaluation.ipynb  # Evaluación y comparación
```

---

## 🎯 Criterios de Aceptación ML

### Dataset
- [ ] 100.000 transacciones generadas
- [ ] Distribución 95/5 respetada
- [ ] 7 patrones de fraude inyectados
- [ ] 50+ features calculadas

### XGBoost
- [ ] AUC-ROC > 0.95 en test set
- [ ] F1-Score > 0.85 en test set
- [ ] Precision > 0.80 (no muchos falsos positivos)
- [ ] Recall > 0.90 (no dejar pasar fraude)
- [ ] Feature importance calculada y visualizada

### Isolation Forest
- [ ] Detecta al menos 80% de anomalías sintéticas
- [ ] Falsa alarma < 10%

### Integración
- [ ] Predicción en < 50ms por transacción
- [ ] Modelos cargados en memoria al iniciar API
- [ ] Endpoint de reentrenamiento manual
- [ ] Metadata de modelos guardada en BD

---

## 📈 Plan de Reentrenamiento

### Cuándo reentrenar

1. **Cada 30 días** con datos nuevos (si hay suficientes)
2. **Cuando F1-Score cae < 0.80** en producción
3. **Cuando aparecen nuevos patrones de fraude** no detectados
4. **Manualmente** vía endpoint POST /api/v1/ml/retrain

### Proceso de reentrenamiento

```python
# 1. Recopilar datos nuevos (últimos 30 días)
new_data = get_recent_transactions(days=30)

# 2. Etiquetar (transacciones marcadas manualmente como fraude/legítimas)
labeled_data = label_transactions(new_data)

# 3. Combinar con dataset original
combined_data = combine_datasets(original_data, labeled_data)

# 4. Reentrenar modelos
new_xgb = train_xgboost(combined_data)
new_iso = train_isolation_forest(combined_data)

# 5. Evaluar en test set
metrics = evaluate_models(new_xgb, new_iso)

# 6. Si métricas mejoran → desplegar nuevos modelos
if metrics["f1"] > current_model_metrics["f1"]:
    deploy_models(new_xgb, new_iso, version="v2")
```

---

## 🔒 Consideraciones de Seguridad

- **No exponer modelos:** Los modelos .pkl no se suben a GitHub
- **Versionado:** Cada modelo tiene versión y metadata
- **Rollback:** Si un modelo nuevo falla, volver al anterior
- **Validación:** Todo modelo nuevo pasa por tests antes de deploy
- **Datos sensibles:** El dataset sintético no contiene datos reales

---

## 📚 Librerías Python

```txt
# ML
scikit-learn==1.5.*
xgboost==2.1.*
imbalanced-learn==0.12.*  # SMOTE para balanceo de clases

# Análisis
pandas==2.2.*
numpy==1.26.*

# Visualización
matplotlib==3.9.*
seaborn==0.13.*

# Notebooks
jupyter==1.1.*
ipykernel==6.29.*
```

---

*Especificación técnica ML — OWL (Hermes) + Mikel — 2026-06-11*
