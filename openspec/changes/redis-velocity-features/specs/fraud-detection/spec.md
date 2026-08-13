# Delta for fraud-detection

## Purpose

Wires the fraud scoring pipeline to the `velocity-store` capability: hot-path velocity counts come from Redis Sorted Sets instead of a per-request Postgres 5-minute scan, `tx_count_last_1h` becomes a true 1-hour count (fixing the bug where it duplicated the 5-minute count), and training data propagates real velocity features so train/serve stay aligned. All behavioral changes are ADDED — no existing requirement text is modified.

## ADDED Requirements

### Requirement: Velocity Context from VelocityStore (FD-VEL-001)

The scoring pipeline MUST populate `context.recent_transactions` and `user_history.tx_count_last_5min`/`tx_count_last_1h` from the VelocityStore, and MUST NOT execute the 5-minute Postgres scan (Query A) on the hot path. The all-user transactions query (Query B) that feeds known cards and amount statistics SHALL remain.

#### Scenario: Recent transactions count from velocity store

- GIVEN a user with 3 transactions in the last 5 minutes
- WHEN a POST /api/v1/transactions request is scored
- THEN `context.recent_transactions` is 3 AND `tx_count_last_5min` is 3

#### Scenario: Query A removed from hot path

- GIVEN a scoring request for an existing user
- WHEN the pipeline executes
- THEN exactly one Postgres user-history query (Query B) runs AND no 5-minute Postgres scan is executed

### Requirement: Real 1-Hour Velocity Count (FD-VEL-002)

`user_history.tx_count_last_1h` MUST be a true one-hour velocity count, distinct from the 5-minute count.

#### Scenario: Transactions older than 5 minutes counted in the hour

- GIVEN a user with 2 transactions in the last 5 minutes and 5 transactions between 5 minutes and 1 hour old
- WHEN the transaction is scored
- THEN `tx_count_last_1h` is 7 AND `tx_count_last_5min` is 2

#### Scenario: No recent transactions

- GIVEN a user with no transactions in the last hour
- WHEN the transaction is scored
- THEN `tx_count_last_5min` and `tx_count_last_1h` are both 0

### Requirement: Scoring Resilient to Velocity Store Failure (FD-VEL-003)

When the VelocityStore is unavailable, the scoring pipeline MUST complete using Postgres-derived velocity values and MUST return HTTP 201 (never 500).

#### Scenario: Redis down during scoring

- GIVEN Redis is unreachable
- WHEN a POST /api/v1/transactions request is scored
- THEN the response is HTTP 201 with velocity features from Postgres AND a warning is logged

### Requirement: Velocity-Aware Training Data (FD-VEL-004)

Training data MUST propagate the generated `velocity_5min`/`velocity_1h` values into FeatureEngine history (non-zero for fraud samples), and the regenerated synthetic CSV MUST persist both columns. The retrained model SHALL be validated through the production-aligned feature pipeline, and the train/serve alignment check (ML-ALIGN) MUST be revalidated with updated thresholds.

#### Scenario: CSV persists velocity columns

- GIVEN the synthetic dataset is regenerated
- THEN the CSV contains `velocity_5min` and `velocity_1h` columns AND training features use their values

#### Scenario: Train/serve parity revalidated

- GIVEN a retrained model
- WHEN alignment is checked against the production FeatureEngine
- THEN the ML-ALIGN check passes AND thresholds are revalidated on the updated distribution