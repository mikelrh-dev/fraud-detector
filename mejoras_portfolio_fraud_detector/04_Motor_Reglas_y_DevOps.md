# 4. Motor de Reglas Dinámico y DevOps (CI/CD)

## El Problema Actual
Las reglas duras (ej. listas negras de comercios) suelen estar cableadas en el código Python. Si hay un ataque de fraude masivo ahora mismo, tendrías que cambiar el código, hacer un commit, reconstruir los contenedores Docker y desplegar, perdiendo minutos vitales. Además, no hay integración continua.

## La Solución Open Source: Hot-Reloading y GitHub Actions

### 1. Motor de Reglas basado en Caché (Hot-Reloading)
* **Implementación:** Guarda las reglas de fraude en formato JSON dentro de Redis, no en código Python.
* Ejemplo de clave Redis (`rule:high_amount`): `{"condition": "amount > 5000", "action": "block"}`
* **Ventaja:** La API en FastAPI leerá la configuración de Redis. Puedes construir un pequeño script o endpoint que actualice estas reglas en Redis, permitiendo que el sistema de fraude se adapte en tiempo real sin reiniciar el servidor.

### 2. Pipelines de CI/CD
* **Herramienta:** `GitHub Actions` (Gratis para repositorios públicos).
* **Implementación:** Crea un archivo `.github/workflows/ci.yml`.
* **Pasos del Pipeline:**
  1. Clona el repositorio.
  2. Levanta un entorno de Python.
  3. Pasa un linter de código (`ruff` o `flake8`).
  4. Ejecuta toda la suite de tests (`pytest tests/`).
* **Insignias (Badges):** Pon un badge verde de "Build: Passing" en la parte superior de tu `README.md`. A los recruiters técnicos (CTOs, Tech Leads) se les van los ojos a ese badge verde. Demuestra limpieza y profesionalidad.

## 💡 Cómo venderlo a un Recruiter
> *"Implementé un motor de reglas con 'Hot-Reloading' respaldado por Redis, permitiendo a los analistas de riesgo modificar las políticas de bloqueo en milisegundos sin necesidad de redesplegar la API. Todo el proyecto está respaldado por integración continua vía GitHub Actions garantizando la integridad del código."*
