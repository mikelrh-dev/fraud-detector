# Delta for fraud-detection

## Purpose

Extends the scoring pipeline so `POST /api/v1/transactions` snapshots the scored feature vector into the new `fraud:shap` queue for transactions classified fraud or review, feeding the `shap-attribution` capability. Existing scoring behavior is unchanged — this delta only adds enqueue behavior.

## ADDED Requirements

### Requirement: SHAP Attribution Enqueue (FD-SHP-001)

After scoring, when classification is "fraud" or "review", the system MUST enqueue a `fraud:shap` message containing `transaction_id` and a snapshot of the exact feature vector used for scoring (the worker MUST NOT recalculate features). Enqueue MUST be best-effort: a Redis failure MUST NOT fail the request. When classification is "legitimate", the system MUST NOT enqueue.

#### Scenario: Fraud transaction enqueued with snapshot

- GIVEN a transaction classified "fraud"
- WHEN `POST /api/v1/transactions` completes
- THEN a `fraud:shap` message exists with transaction_id and the scored feature vector

#### Scenario: Review transaction enqueued

- GIVEN a transaction classified "review"
- WHEN `POST /api/v1/transactions` completes
- THEN a `fraud:shap` message exists for the transaction

#### Scenario: Legitimate transaction not enqueued

- GIVEN a transaction classified "legitimate"
- WHEN `POST /api/v1/transactions` completes
- THEN no `fraud:shap` message exists for the transaction

#### Scenario: Snapshot equals scored vector

- GIVEN a scoring run whose feature vector is V
- WHEN the enqueued message is inspected
- THEN `features` equals V (the exact vector used at scoring time)

#### Scenario: Redis down during enqueue

- GIVEN Redis is unreachable
- WHEN `POST /api/v1/transactions` is scored as fraud
- THEN the response is HTTP 201 and the enqueue failure is logged (best-effort)
