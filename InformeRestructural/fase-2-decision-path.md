# Fase 2 — Decision Path (Completada)

**Fecha:** 2026-09-27
**Estado:** Completada
**Tests:** 93 passed, 0 failed

---

## Resumen

Se corrigieron los fallos estructurales en la cadena de decisión de fraude. El ML ahora puede influir en la clasificación, las reglas muertas fueron eliminadas, el ensemble normaliza sus weights, y el frontend usa los thresholds dinámicos del backend.

---

## Cambios Prácticos

### 1. ML: Eliminado "smoothing" que destruía la señal (C1)

**Problema:** La transformación cúbica `0.5 + 0.7*(p-0.5)^3 + 0.3*(p-0.5)` comprimía el rango del ML a [26.25, 73.75]. Con peso 0.25, el máximo aporte era 18.44 puntos. El threshold más bajo es 40. **El ML no podía cambiar ninguna decisión.**

**Cambio:**
- `src/services/ml_model.py`: eliminada la transformación. Ahora `predict()` retorna `probability * 100.0` directamente.

**Efecto práctico:**
- El ML ahora tiene rango completo [0, 100]
- Un modelo 100% seguro de fraude aporta 25 puntos al ensemble (antes: 18.44)
- Un modelo 100% seguro de legítimo aporta 0 puntos (antes: 6.56)
- **El ML ahora puede influir en la clasificación de fraude**

---

### 2. Reglas Muertas: Eliminadas `card_mismatch` y `country_mismatch` (C2/C3)

**Problema:**
- `card_mismatch` (20 pts): el `flush()` hacía visible la transacción actual al query que busca `known_cards`. La regla nunca se disparaba.
- `country_mismatch` (15 pts): ambos países hardcodeados a `"AR"`. La regla nunca se disparaba.

**Cambio:**
- `src/services/rule_engine.py`: eliminadas de `WEIGHTS` y de `evaluate()`
- `tests/test_rule_engine.py`: actualizados tests para reflejar la nueva realidad

**Efecto práctico:**
- 35 puntos de reglas muertas eliminados del sistema
- El score máximo posible bajó de 135 a 100 (ya estaba capped)
- Los tests ahora reflejan el comportamiento real

---

### 3. Ensemble: Weights Normalizados (I2)

**Problema:** El ensemble era un weighted SUM no normalizado. Si un layer caía (ML sin modelo, sin velocity), su peso se evaporaba en vez de redistribuirse. Un modelo caído = 25% del score desaparecía silenciosamente.

**Cambio:**
- `src/services/ensemble.py`: `combine()` ahora normaliza los weights activos para que siempre sumen 1.0

**Efecto práctico:**
- Si el ML está caído, su 25% se redistribuye entre rule y context
- El score no se degrada silenciosamente cuando un layer falla
- El ensemble es ahora un verdadero weighted average

---

### 4. Frontend: Alineado con Thresholds Dinámicos (I7)

**Problema:** El frontend usaba umbrales fijos (45/60) mientras el backend usa thresholds dinámicos (70/50/45/40). Una transacción bloqueada (score 42, threshold 40) se veía verde en el frontend.

**Cambio:**
- `frontend/src/components/RiskMeter.tsx`: añadido `classificationToTone()` y prop `classification`
- `frontend/src/pages/ScoreResultCard.tsx`: usa `classificationToTone(classification)` en vez de `riskTone(score)`

**Efecto práctico:**
- El color del gauge ahora refleja la clasificación real del backend
- Una transacción bloqueada se ve roja, no verde
- No hay más divergencia entre lo que el backend decide y lo que el usuario ve

---

### 5. Timestamps: Manejo Robusto (I4/I12)

**Problema:**
- `rule_engine.py`: `datetime.fromisoformat()` no acepta sufijo `Z` en Python 3.10 → `unusual_hours` y `off_hours_crypto` no se disparaban
- `feature_engine.py`: parseaba el timestamp dos veces, y si fallaba asignaba `hour=0` (medianoche) → aumentaba el score de riesgo

**Cambio:**
- `src/services/rule_engine.py`: `str(ts_str).replace("Z", "+00:00")` para soportar sufijo `Z`
- `src/services/feature_engine.py`: parse una sola vez, deriva `hour` e `is_weekend` del mismo `dt`. Si falla, usa `hour=12` (mediodía, neutral) en vez de `hour=0` (medianoche, sospechoso)

**Efecto práctico:**
- Los timestamps con `Z` ahora se parsean correctamente
- Un error de parseo ya no aumenta el score de riesgo artificialmente
- El feature engine es más consistente

---

## Archivos Modificados

| Archivo | Cambio |
|---|---|
| `src/services/ml_model.py` | Eliminado "smoothing", ML con rango completo |
| `src/services/rule_engine.py` | Eliminadas reglas muertas, timestamps robustos |
| `src/services/ensemble.py` | Weights normalizados |
| `src/services/feature_engine.py` | Parse una vez, defaults neutrales |
| `frontend/src/components/RiskMeter.tsx` | `classificationToTone()` |
| `frontend/src/pages/ScoreResultCard.tsx` | Usa `classification` del backend |
| `tests/test_rule_engine.py` | Actualizados tests de reglas muertas |

---

## Verificación

```
tests/test_rule_engine.py ................. 29 passed
tests/test_ensemble.py .................... 17 passed
tests/test_ml_model.py .................... 10 passed
tests/unit/test_transaction_service.py .... 8 passed
tests/integration/test_transaction_api.py .. 29 passed

Total: 93 passed, 0 failed
```

---

## Impacto en el Sistema

### Antes de la Fase 2
- ML: rango [26.25, 73.75], no podía cambiar decisiones
- Reglas muertas: 35 puntos que nunca se disparaban
- Ensemble: weights no normalizados, layers caídos evaporaban score
- Frontend: umbrales fijos, transacciones bloqueadas se veían verdes
- Timestamps: `Z` no soportado, errores de parseo aumentaban riesgo

### Después de la Fase 2
- ML: rango [0, 100], puede influir en decisiones
- Reglas muertas: eliminadas, solo reglas funcionales
- Ensemble: weights normalizados, layers caídos redistribuyen score
- Frontend: usa clasificación real del backend
- Timestamps: `Z` soportado, errores de parseo son neutrales

---

## Pendiente de la Fase 2

- Verificar que el modelo XGBoost esté bien entrenado (Fase 3)
- Considerar añadir `country` como columna persistida si se quiere la regla `country_mismatch`
- Considerar añadir protección contra transacciones duplicadas (idempotency key)
