# LLM Reporting Specification

## Purpose

Async LLM report generation via Redis queue for technical explanatory fraud reports consumed by analysts.

## Requirements

### Requirement: Report Queue Submission

The system SHALL enqueue fraud report requests to Redis when a transaction is classified as fraud.

#### Scenario: Enqueue report request

- GIVEN a transaction classified as "fraud" with ensemble_score >= threshold
- WHEN the scoring pipeline completes
- THEN a report request is pushed to the Redis "fraud_reports" queue
- AND the request includes transaction_id, score breakdown, and fired rules

#### Scenario: No queue for legitimate transactions

- GIVEN a transaction classified as "legitimate"
- WHEN the scoring pipeline completes
- THEN no report request is enqueued to Redis

#### Scenario: Idempotent enqueue

- GIVEN a report request for transaction_id already exists in the queue
- WHEN the scoring pipeline attempts to enqueue again
- THEN no duplicate entry is added

### Requirement: Async LLM Worker

The system MUST run an asynchronous worker that consumes report requests from Redis and generates technical reports via Ollama.

#### Scenario: Worker processes queued request

- GIVEN a report request exists in the Redis queue
- WHEN the LLM worker polls the queue
- THEN the worker dequeues the request
- AND calls Ollama with a structured prompt containing transaction details and scoring breakdown

#### Scenario: Report generation success

- GIVEN the LLM worker calls Ollama with a valid prompt
- WHEN Ollama returns a response within the timeout (10s)
- THEN the worker parses the response
- AND persists an LLMReport record linked to the transaction

#### Scenario: LLM timeout handling

- GIVEN the LLM worker calls Ollama
- WHEN Ollama does not respond within 10 seconds
- THEN the worker marks the request as "timeout"
- AND requeues the request for retry (max 3 retries)

#### Scenario: LLM service unavailable

- GIVEN Ollama is unreachable
- WHEN the LLM worker attempts to call the API
- THEN the worker logs the error
- AND requeues the request with exponential backoff

### Requirement: LLM Report Persistence

The system SHALL persist generated LLM reports with full metadata for auditability.

#### Scenario: Report stored successfully

- GIVEN the LLM worker received a valid response from Ollama
- WHEN the worker processes the response
- THEN an LLMReport record is created with transaction_id, report_text, model_name, generation_time, and status "completed"

#### Scenario: Report references scoring data

- GIVEN an LLMReport is persisted
- WHEN the report is retrieved
- THEN it includes references to the FraudScore, fired rules, and ML score that informed the generation

### Requirement: Report Retrieval API

The system SHALL provide an endpoint to retrieve LLM reports by transaction ID.

#### Scenario: Retrieve completed report

- GIVEN an LLMReport exists with status "completed" for a transaction
- WHEN a GET /api/v1/transactions/{id}/report request is made
- THEN the report text and metadata are returned with HTTP 200

#### Scenario: Report not yet generated

- GIVEN a transaction was classified as fraud but the LLM worker has not yet processed it
- WHEN a GET /api/v1/transactions/{id}/report request is made
- THEN the system returns HTTP 202 with status "pending"

#### Scenario: Report generation failed

- GIVEN an LLMReport exists with status "failed" for a transaction
- WHEN a GET /api/v1/transactions/{id}/report request is made
- THEN the system returns HTTP 200 with the error details and status "failed"

### Requirement: Structured Prompt Template

The system MUST use a deterministic prompt template that instructs the LLM to produce technical fraud analysis, not decisions.

#### Scenario: Prompt contains scoring breakdown

- GIVEN a transaction with rule_score, ml_score, and ensemble_score
- WHEN the prompt is assembled
- THEN it includes all three scores, the threshold, and the list of fired rules

#### Scenario: LLM instructed not to decide

- GIVEN any prompt template
- WHEN the prompt is assembled
- THEN it explicitly instructs the LLM to provide analysis only, not fraud determination
