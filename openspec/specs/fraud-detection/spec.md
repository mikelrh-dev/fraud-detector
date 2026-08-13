# Fraud Detection Specification

## Purpose

Core fraud scoring pipeline: rule engine, ML anomaly detection, ensemble scoring, transaction CRUD, and fraud alerts.

## Requirements

### Requirement: Transaction CRUD

The system SHALL support full lifecycle management of financial transactions with soft delete semantics.

#### Scenario: Create a valid transaction

- GIVEN a well-formed transaction payload with amount, currency, merchant, and card details
- WHEN the system receives a POST /api/v1/transactions request
- THEN a Transaction record is persisted with status "pending"
- AND `created_at` and `updated_at` timestamps are set

#### Scenario: Retrieve a transaction by ID

- GIVEN a transaction exists in the database
- WHEN a GET /api/v1/transactions/{id} request is made
- THEN the transaction details are returned with HTTP 200

#### Scenario: Soft delete a transaction

- GIVEN a transaction exists with status "pending"
- WHEN a DELETE /api/v1/transactions/{id} request is made
- THEN the transaction's `deleted_at` field is set
- AND the record remains in the database (no physical deletion)
- AND the transaction is excluded from default list queries

#### Scenario: Reject invalid transaction payload

- GIVEN a transaction payload missing required fields (amount, currency)
- WHEN a POST /api/v1/transactions request is made
- THEN the system returns HTTP 422 with validation error details

### Requirement: Rule Engine Scoring

The system MUST evaluate transactions against a deterministic set of code-based fraud rules and produce a rule score (0-100).

#### Scenario: Single rule fires

- GIVEN a transaction with amount > $10,000
- WHEN the rule engine evaluates the transaction
- THEN the "high_amount" rule fires with configured weight
- AND the rule score reflects the fired rule's contribution

#### Scenario: Multiple rules fire

- GIVEN a transaction with amount > $10,000 AND velocity > 5 transactions/hour
- WHEN the rule engine evaluates the transaction
- THEN both "high_amount" and "high_velocity" rules fire
- AND the combined rule score is the weighted sum (capped at 100)

#### Scenario: No rules fire

- GIVEN a transaction that matches no rule conditions
- WHEN the rule engine evaluates the transaction
- THEN the rule score is 0
- AND the fired_rules list is empty

#### Scenario: Rule engine is deterministic

- GIVEN the same transaction input
- WHEN the rule engine evaluates it twice
- THEN both evaluations produce identical scores and fired_rules

### Requirement: ML Anomaly Detection

The system MUST score transactions using an Isolation Forest model for anomaly detection, producing an ML score (0-100).

#### Scenario: Score transaction with trained model

- GIVEN a serialized Isolation Forest model is loaded
- WHEN a transaction is passed to the ML scorer
- THEN the system extracts features via the feature pipeline
- AND returns an ML anomaly score between 0 and 100

#### Scenario: Handle missing model gracefully

- GIVEN no serialized model file exists at the configured path
- WHEN the ML scorer is invoked
- THEN the system returns an ML score of 0 (neutral)
- AND logs a warning that the model is not available

#### Scenario: Feature extraction consistency

- GIVEN a transaction with known field values
- WHEN features are extracted
- THEN the feature vector matches the expected schema (fixed dimensionality)
- AND the extraction is deterministic for identical inputs

### Requirement: Ensemble Scoring

The system MUST combine rule score, ML score, and contextual factors into a single ensemble score (0-100) with configurable weights.

#### Scenario: Weighted combination

- GIVEN rule_score = 60, ml_score = 80, weights = {rules: 0.4, ml: 0.6}
- WHEN the ensemble scorer computes the final score
- THEN the ensemble score is 72 (0.4 * 60 + 0.6 * 80)

#### Scenario: Dynamic threshold by amount tier

- GIVEN a transaction amount of $500 (low tier)
- WHEN the system determines the fraud threshold
- THEN the threshold is 70 (low-tier default)

#### Scenario: High amount threshold

- GIVEN a transaction amount of $50,000 (high tier)
- WHEN the system determines the fraud threshold
- THEN the threshold is 50 (lower threshold for high amounts)

#### Scenario: Score classification

- GIVEN an ensemble score of 75 and threshold of 70
- WHEN the system classifies the transaction
- THEN the classification is "fraud"

### Requirement: Fraud Alert Generation

The system SHALL create a FraudAlert when a transaction's ensemble score exceeds the applicable threshold.

#### Scenario: Alert created for fraudulent transaction

- GIVEN a transaction with ensemble_score = 85 and threshold = 70
- WHEN the scoring pipeline completes
- THEN a FraudAlert record is created
- AND the alert references the transaction and includes the score, threshold, and classification

#### Scenario: No alert for legitimate transaction

- GIVEN a transaction with ensemble_score = 40 and threshold = 70
- WHEN the scoring pipeline completes
- THEN no FraudAlert is created

### Requirement: Fraud Score Persistence

The system MUST persist a FraudScore record for every scored transaction, capturing the full scoring breakdown.

#### Scenario: Score record created

- GIVEN a transaction has been scored by the pipeline
- WHEN the pipeline completes
- THEN a FraudScore record is persisted with rule_score, ml_score, ensemble_score, threshold, and classification

#### Scenario: Score record is immutable

- GIVEN a FraudScore record exists
- WHEN any update is attempted on the record
- THEN the system rejects the update (scores are append-only)

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

---

## Delta: shap-feature-attribution

### Requirement: SHAP Attribution Enqueue (FD-SHP-001)

After scoring, when classification is "fraud" or "review", the system MUST enqueue a `fraud:shap` message containing `transaction_id` and a snapshot of the exact feature vector used for scoring (the worker MUST NOT recalculate features). Enqueue MUST be best-effort: a Redis failure MUST NOT fail the request. When classification is "legitimate", the system MUST NOT enqueue.

#### Scenario: Fraud transaction enqueued with snapshot

- GIVEN a transaction classified "fraud"
- WHEN `POST /api/v1/transactions` completes
- THEN a `fraud:shap` message exists with transaction_id and the scored feature vector

#### Scenario: Legitimate transaction not enqueued

- GIVEN a transaction classified "legitimate"
- WHEN `POST /api/v1/transactions` completes
- THEN no `fraud:shap` message exists for the transaction

#### Scenario: Redis down during enqueue

- GIVEN Redis is unreachable
- WHEN `POST /api/v1/transactions` is scored as fraud
- THEN the response is HTTP 201 and the enqueue failure is logged (best-effort)
