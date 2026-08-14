# 3. MLOps y Explainable AI (XAI)

## El Problema Actual
Los modelos ML en finanzas no pueden ser "cajas negras". Por ley (GDPR), si rechazas la transacción de un cliente legítimo, debes poder explicar el motivo. Además, tu entrenamiento actual (`train_xgboost_aligned.py`) se beneficiaría de un rastreo sistemático.

## La Solución Open Source: SHAP y MLflow

### 1. Explicabilidad (XAI) con SHAP
* **Herramienta:** Librería `shap` en Python (Open Source).
* **Implementación:** Integra SHAP en el endpoint de transacciones o en el worker asíncrono. SHAP desglosa matemáticamente la predicción.
* **Output:** Podrás decirle al dashboard frontend: *"Esta transacción tiene un 85% de riesgo. Los factores que más sumaron riesgo fueron: +30% por IP nueva, +25% porque el amount_sum_24h es 3 desviaciones estándar mayor a la media"*.

### 2. MLOps con MLflow
* **Herramienta:** `MLflow` (Completamente gratuito, ejecutable en local).
* **Implementación:** En lugar de exportar el modelo con `joblib` directamente, envuelve el entrenamiento en `mlflow.start_run()`. 
* **Ventaja:** MLflow guardará un registro de todos tus hiperparámetros, métricas (Recall, F1) y versionará tus modelos. Podrás mostrar capturas de la UI de MLflow en el `README.md` de tu repositorio.

### 3. Métrica de Negocio (Cost-Sensitive Learning)
* Cambia la optimización para enfocarte en el PR-AUC (Precision-Recall) en lugar del ROC-AUC. 
* Implementa una matriz de costes personalizada donde un Falso Negativo (dejar pasar un fraude de 500€) penaliza al modelo 500 veces más que un Falso Positivo (bloquear una compra legítima de 1€).

## 💡 Cómo venderlo a un Recruiter
> *"Abordé el problema de la caja negra usando valores SHAP para justificar cada rechazo, alineándome con regulaciones como GDPR. Además, sistematicé los experimentos de entrenamiento con MLflow y apliqué Cost-Sensitive Learning, optimizando el modelo no para tener más accuracy, sino para minimizar las pérdidas financieras esperadas del negocio."*
