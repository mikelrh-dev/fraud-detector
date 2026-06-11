# Audit Trail Specification

## Purpose

Immutable decision logging providing a traceable chain from rules → ML → ensemble → LLM → analyst actions.

## Requirements

### Requirement: Scoring Decision Chain

The system MUST record every step of the fraud scoring decision for each transaction.

#### Scenario: Complete scoring chain recorded

- GIVEN a transaction has been scored by the full pipeline
- WHEN the pipeline completes
- THEN an audit record exists containing: rules fired (with individual scores), ML score, ensemble score, threshold used, and final classification

#### Scenario: Chain is queryable by transaction

- GIVEN audit records exist for multiple transactions
- WHEN a query is made for the audit chain of a specific transaction
- THEN the system returns the complete ordered chain of scoring events for that transaction

### Requirement: LLM Report Audit

The system MUST record LLM report generation attempts and outcomes in the audit trail.

#### Scenario: Successful report generation logged

- GIVEN the LLM worker successfully generates a report
- WHEN the report is persisted
- THEN an audit entry records the transaction_id, model used, generation_time_ms, prompt_hash, and status "completed"

#### Scenario: Failed report generation logged

- GIVEN the LLM worker fails to generate a report (timeout or error)
- WHEN the failure occurs
- THEN an audit entry records the transaction_id, error_type, retry_count, and status "failed"

### Requirement: Analyst Action Audit

The system MUST record every analyst action with user identity, timestamp, and reason.

#### Scenario: False positive marking logged

- GIVEN an analyst marks a transaction as false positive
- WHEN the action is submitted
- THEN an audit entry records the analyst_id, transaction_id, action_type "false_positive", reason, and timestamp

#### Scenario: Block revert logged

- GIVEN an analyst reverts a blocked transaction
- WHEN the action is submitted
- THEN an audit entry records the analyst_id, transaction_id, action_type "revert", reason, and timestamp

#### Scenario: Analyst cannot modify audit entries

- GIVEN an audit entry exists for an analyst action
- WHEN the analyst attempts to modify or delete the entry
- THEN the system rejects the operation
- AND audit entries are immutable (append-only)

### Requirement: Audit Query API

The system SHALL provide endpoints to query the audit trail for compliance and investigation purposes.

#### Scenario: Query audit trail by transaction

- GIVEN audit entries exist for a transaction
- WHEN a GET /api/v1/audit/transactions/{id} request is made
- THEN the system returns all audit entries for that transaction in chronological order

#### Scenario: Query audit trail by analyst

- GIVEN an analyst has performed multiple actions
- WHEN a GET /api/v1/audit/analysts/{id} request is made by an admin
- THEN the system returns all audit entries for that analyst's actions

#### Scenario: Non-admin cannot query other analysts' actions

- GIVEN an analyst user
- WHEN a GET /api/v1/audit/analysts/{other_id} request is made
- THEN the system returns HTTP 403 Forbidden

### Requirement: Audit Data Integrity

The system MUST ensure audit trail data cannot be tampered with after creation.

#### Scenario: Audit entries are append-only

- GIVEN an audit entry exists in the database
- WHEN an UPDATE or DELETE operation is attempted on the entry
- THEN the database rejects the operation (enforced at model level)

#### Scenario: Audit entry includes checksum

- GIVEN an audit entry is created
- WHEN the entry is persisted
- THEN a SHA-256 checksum of the entry content is computed and stored
- AND the checksum can be used to verify the entry has not been altered

### Requirement: Audit Retention

The system SHALL retain audit entries indefinitely and support export for compliance purposes.

#### Scenario: Export audit trail

- GIVEN an admin requests an audit export
- WHEN a POST /api/v1/audit/export request is made with date range
- THEN the system generates a CSV or JSON export of all audit entries in the range
- AND the export is available for download

#### Scenario: Soft-deleted transactions retain audit trail

- GIVEN a transaction has been soft-deleted
- WHEN an audit query includes that transaction
- THEN the audit entries for that transaction are still returned
- AND soft delete does not affect audit trail completeness
