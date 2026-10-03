# Comercio, magnitud y categoria: tres arreglos de una vez

## Como se descubrio

Una transaccion real via HTTP: `400000 USD`, comercio `binance`, categoria
`retail`, tarjeta `1232`. Resultado: ensemble 24,1 / 100, "Legitimo", regla
`high_amount` disparada, ML 0,3.

Un cuarto de bitcoin en un intercambio de cripto no es un caso limite. Es
fraude con todas las letras, y el sistema lo dio por bueno.

## Los tres defectos

### D1 - el nombre del comercio no llega a las features

`src/services/feature_engine.py:175-178`

```python
f_merchant_risk = 1.0 if category in MERCHANT_RISK_CATEGORIES else 0.0
f_is_crypto = 1.0 if category == "cryptocurrency" else 0.0
```

El nombre del comercio no aparece. La transaccion de arriba lleva `binance` en
el nombre y `retail` en la categoria, asi que el sistema la puntuo como una
compra de retail: `is_crypto = 0.0` y `merchant_risk_level = 0.0`.

Dos de las diez features, y son las unicas que conocen el tipo de comercio. El
nombre del comercio es cosmetico: escribir "binance" no cambia nada.

El motor de reglas tiene la misma dependencia: `is_adversarial` y `is_regulated`
se derivan solo de la categoria.

**Reparar:** un vocabulario compartido de comercios conocidos, en
`src/core/ml_constants.py`, junto a `CATEGORY_ALIASES` y
`MERCHANT_RISK_CATEGORIES`. Se sigue el principio D7-3 que ya rige el archivo:
reglas y features comparten un solo vocabulario, nunca una segunda lista.
La coincidencia es por token y sin distinguir mayusculas, para que
`"binance"` en `"binance exchange"` cuente, pero un comercio que solo contenga
la cadena por casualidad no.

### D2 - `high_amount` es un interruptor, no una magnitud

`src/services/rule_engine.py:55,108`

```python
HIGH_AMOUNT_THRESHOLD: float = 1000.0
if amount > self.HIGH_AMOUNT_THRESHOLD:
    fired.append("high_amount")   # WEIGHTS["high_amount"] = 35
```

1.001 EUR y 400.000 USD reciben los mismos 35 puntos. Un cafe y un Fourth de
Bitcoin son la misma evidencia.

Existe `tests/test_model_amount_monotonicity.py` para el MODELO. El motor de
reglas no tiene equivalente, y por eso nadie lo noto.

**Reparar:** 35 puntos por cruzar el umbral, mas un termino por cada orden de
magnitud por encima, con techo. Un salto de 400.000 tiene que pesar mas que un
salto de 1.100, y el techo evita que una sola regla domina el ensemble.

El techo importa: sin el, una regla sola cruza el umbral de fraude y se pierde la
distincion entre "sospechoso" y "claramente fraude". El test
`test_no_single_regulated_category_reaches_the_fraud_threshold` protege esa
distincion para las categorias reguladas y debe seguir verde.

### D3 - la categoria es texto libre y decide las features

Quien envia el payload elige que caracteristicas se activan. No es un fallo de
logica: es
un problema de diseno. Un campo que decide el riesgo no puede ser texto libre.

**Reparar en el borde:** el endpoint valida `merchant_category` contra
`KNOWN_MERCHANT_CATEGORIES` y responde 422 si no existe. El selector del
frontend pasa a lista cerrada.

La ruta de advertencia y el contador de categoria desconocida **se conservan en
el motor**: el motor tambien lo llaman consumidores por lotes y otros que no
pasan por el endpoint. Validar en el borde no autoriza a relajar la defensa en
profundidad, y el codigo que la implementa es la instrumentacion de por que D1
existe.

## Fuera de alcance

- El rango bajo de ML en ese caso concreto: se analiza aparte.
- El selector de categoria del frontend se construye contra el mismo vocabulario
  del backend, no contra una copia.

## Criterio de terminado

1. La transaccion `400000 USD / binance / retail` deja de puntuar como legitima.
2. Un cafe de 1.100 EUR puntua menos que 400.000, y ambos mas que 900.
3. Una categoria inventada se rechaza con 422 en el endpoint.
4. `origin/master` intacto.
5. `docs/published_metrics.json` sin tocar: el manifiesto publica metricas del
   harness ML y ninguna de ellas depende de los pesos de reglas.