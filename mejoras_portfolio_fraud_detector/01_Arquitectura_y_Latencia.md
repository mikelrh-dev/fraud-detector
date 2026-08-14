# 1. Arquitectura y Latencia: Separación de Rutas (Fast Path vs Slow Path)

## El Problema Actual
Actualmente, el sistema acopla la validación del modelo XGBoost, el motor de reglas y la generación de reportes del LLM en un mismo flujo. Esto genera latencia. En el mundo real, una pasarela de pago (Stripe, Adyen) corta la conexión si el detector de fraude tarda más de 20-50 milisegundos. Un LLM local jamás responderá en ese tiempo.

## La Solución Open Source: Arquitectura Orientada a Eventos (Event-Driven)
Debes dividir tu API en dos rutas de ejecución.

### 1. Fast Path (Ruta Síncrona Crítica)
Es la ruta que devuelve un `HTTP 200 OK` (Transacción Aceptada) o `HTTP 403 / 400` (Rechazada) en menos de 20ms.
* **Componentes:** FastAPI + Motor de Reglas en Memoria + Inferencia XGBoost.
* **Herramienta:** `ONNX Runtime` (gratuito). Convierte tu modelo `.joblib` a formato `.onnx`. La inferencia pasará de tardar 10ms a tardar 1ms.

### 2. Slow Path (Ruta Asíncrona Out-of-Band)
Es la ruta encargada de la analítica profunda y la explicabilidad, que no bloquea la compra del usuario.
* **Componentes:** Trabajadores en segundo plano.
* **Herramientas:** `Celery` + `Redis` (como Message Broker). 
* **Flujo:** Una vez el Fast Path toma la decisión, envía un evento a Redis. Un worker de Celery lo recoge, llama a Ollama (LLM) de forma asíncrona, genera el reporte en markdown de por qué la transacción fue sospechosa y lo guarda en PostgreSQL.

## 💡 Cómo venderlo a un Recruiter
> *"En mi portfolio implementé un patrón de Fast-Path/Slow-Path usando Celery y Redis. Me di cuenta de que un LLM es demasiado lento para la autorización en tiempo real, así que la inferencia del modelo ML aprueba el pago en 15ms, mientras que el análisis forense del LLM se procesa en background de forma asíncrona."*
