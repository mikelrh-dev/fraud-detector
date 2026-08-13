# SHAP Attribution Specification

## Purpose

Async SHAP feature attribution for suspicious transactions: a dedicated Redis worker computes feature contributions over the exact scored feature vector (snapshot), persists the top-5, and exposes them read-only in the API. Explanation only — never influences the decision.

## Requirements

### Requirement: Queue-Driven SHAP Worker (SHP-001)

The system MUST run a dedicated async worker that consumes `fraud:shap` queue messages, each containing `transaction_id` and a snapshot feature vector. The worker MUST compute SHAP values with `shap.TreeExplainer` over the loaded XGBoost model inside `asyncio.to_thread` so CPU-bound work does not block the event loop.

#### Scenario: Process queued message

- GIVEN a `fraud:shap` message with `transaction_id` and `features`
- WHEN the worker polls the queue
- THEN it dequeues the message and computes SHAP contributions for that feature vector

#### Scenario: Snapshot vector is used

- GIVEN a message whose snapshot differs from the transaction's current features
- WHEN the worker computes SHAP values
- THEN contributions derive from the snapshot vector, not from a recalculation

### Requirement: Top-5 Persistence (SHP-002)

The worker MUST select the top-5 features by absolute contribution and MUST persist one `ShapAttribution` row per feature (transaction FK CASCADE, feature, signed contribution, rank 1-5, timestamps). Re-running for the same transaction MUST replace, not duplicate, rows.

#### Scenario: Top-5 by absolute value

- GIVEN 12 features with signed contributions
- WHEN the worker selects and persists
- THEN exactly 5 rows exist with ranks 1..5 ordered by absolute contribution descending and signed values preserved

#### Scenario: Multi-class output uses fraud class

- GIVEN `shap_values` with shape (samples, features, classes)
- WHEN contributions are extracted
- THEN the fraud-class index (1) values are used

#### Scenario: Idempotent re-run

- GIVEN existing ShapAttribution rows for a transaction
- WHEN the worker processes the message again
- THEN the rows are replaced with fresh timestamps and no duplicates exist

### Requirement: Retry with Max Attempts (SHP-003)

The worker MUST requeue failed messages and increment `retry_count`; once `retry_count` reaches the configured maximum, the message MUST be dropped and the failure logged.

#### Scenario: Retry on failure

- GIVEN a SHAP computation failure
- WHEN the worker handles the message
- THEN the message is requeued with `retry_count` incremented

#### Scenario: Max retries exhausted

- GIVEN `retry_count` equals the configured maximum
- WHEN the worker fails again
- THEN the message is dropped and the failure is logged

### Requirement: SHAP Audit Trail (SHP-004)

The worker MUST write audit entries for each outcome: `shap_computed` on success (transaction_id, timing) and `shap_failed` on final failure (transaction_id, error_type, retry_count).

#### Scenario: Success audited

- GIVEN SHAP computation and persistence succeed
- WHEN the worker completes
- THEN an audit entry with type `shap_computed` exists for the transaction

#### Scenario: Failure audited

- GIVEN a message dropped after max retries
- WHEN the worker gives up
- THEN an audit entry with type `shap_failed`, error_type, and retry_count exists

### Requirement: Defensive SHAP Import (SHP-005)

The worker MUST import `shap` defensively: when shap or its transitive dependencies are unavailable, the worker MUST NOT crash, MUST log a warning, MUST skip computation, and MUST continue the loop. The API MUST still return HTTP 200 with `shap_contributions` null.

#### Scenario: shap unavailable

- GIVEN `shap` is not installed
- WHEN the worker starts
- THEN it logs a warning and continues without computing

#### Scenario: API unaffected

- GIVEN `shap` is unavailable
- WHEN `GET /api/v1/transactions/{id}` is requested
- THEN the response is HTTP 200 with `shap_contributions` null

### Requirement: Dependency Declaration (SHP-006)

The project MUST declare `shap==0.46.*` in `requirements.txt` so the worker capability is reproducible.

#### Scenario: Dependency pinned

- GIVEN a fresh environment installs project dependencies
- THEN `shap` 0.46.x is installed and importable

### Requirement: Explanation-Only Invariant (SHP-007)

SHAP computation MUST NOT alter transaction classification, scores, alerts, or any decision artifact; it is strictly read-only after scoring.

#### Scenario: Decision unchanged

- GIVEN a transaction classified "fraud" with persisted scores
- WHEN the worker computes SHAP attribution
- THEN classification, fraud_scores, and alerts remain unchanged
