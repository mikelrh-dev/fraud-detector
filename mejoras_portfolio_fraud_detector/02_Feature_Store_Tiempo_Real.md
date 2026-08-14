# 2. Ingeniería de Datos: Feature Store en Tiempo Real

## El Problema Actual
El modelo XGBoost toma decisiones basadas en características (features) estáticas de la transacción (ej. monto, saldo origen, saldo destino). El fraude sofisticado no ataca con una gran transacción, sino con micro-transacciones repetidas (*Velocity Attacks*).

## La Solución Open Source: Velocity Features con Redis
Necesitas implementar un "Feature Store" ligero. Un Feature Store calcula variables temporales al vuelo para dárselas al modelo.

### Implementación con Redis (ZSETs)
Usa los "Sorted Sets" de Redis para mantener ventanas de tiempo deslizantes (Sliding Windows) sin saturar PostgreSQL.
* **Variables a crear:**
  * `tx_count_1h`: Número de transacciones del usuario en la última hora.
  * `amount_sum_24h`: Dinero total movido en las últimas 24 horas.
  * `ip_distinct_count_1h`: Número de IPs distintas usadas en la última hora.
* **¿Cómo se hace?:** Cada vez que entra una transacción, haces un `ZADD` en Redis con el timestamp como score. Para saber cuántas transacciones hizo en la última hora, haces un `ZCOUNT` restando 3600 segundos al timestamp actual. Es una operación $O(\log(N))$, rapidísima.

## 💡 Cómo venderlo a un Recruiter
> *"Para simular el comportamiento de redes como Mastercard, construí un Feature Store casero utilizando Sorted Sets de Redis. Esto me permite alimentar al modelo XGBoost con 'Velocity Features' (agregaciones en tiempo real como el gasto en los últimos 5 minutos) manteniendo latencias sub-milisequndo."*
