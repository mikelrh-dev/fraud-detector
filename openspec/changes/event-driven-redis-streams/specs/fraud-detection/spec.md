# Delta for fraud-detection

## Purpose

Introduces an event-driven transport for the async worker pipeline: the API
publishes events to Redis Streams (`fraud:llm`, `fraud:shap`,
`fraud:embeddings`) and workers consume them via consumer groups with explicit
XACK. Replaces the list-based LPUSH/BRPOP queues while preserving payload
structure and worker behavior. All behavioral changes are ADDED — no existing
requirement text is modified.

## ADDED Requirements

### Requirement: Event Publishing via Redis Streams (FD-STREAM-001)

The API MUST publish async work as stream events through
`publish_transaction_event(event_type, payload)`. Each event MUST carry
`event_type`, the JSON payload, and an ISO-8601 timestamp. Event types
SHALL map to dedicated streams: `llm_report` → `fraud:llm`,
`shap_attribution` → `fraud:shap`, `merchant_embedding` → `fraud:embeddings`.
Unknown event types MUST raise `ValueError`. A Redis failure during publish
MUST NOT fail the transaction request (best-effort, HTTP 201 preserved).

#### Scenario: Publish LLM report event

- GIVEN a scored transaction
- WHEN the scoring pipeline completes
- THEN an `llm_report` event is appended to stream `fraud:llm` with the
  `score_breakdown` payload and a timestamp

#### Scenario: Publish SHAP attribution event

- GIVEN a transaction classified fraud or review
- WHEN the scoring pipeline completes
- THEN a `shap_attribution` event is appended to stream `fraud:shap` with the
  scored feature-vector snapshot

#### Scenario: Legitimate transaction skips SHAP

- GIVEN a transaction classified legitimate
- WHEN the scoring pipeline completes
- THEN no `shap_attribution` event is published

#### Scenario: Publish merchant embedding event

- GIVEN any scored transaction
- WHEN the scoring pipeline completes
- THEN a `merchant_embedding` event is appended to stream `fraud:embeddings`
  with the merchant name

#### Scenario: Unknown event type rejected

- GIVEN `event_type="nonsense"`
- WHEN `publish_transaction_event` is called
- THEN a `ValueError` is raised and nothing is written to Redis

#### Scenario: Redis down during publish

- GIVEN Redis is unreachable
- WHEN a POST /api/v1/transactions request is scored
- THEN the response is still HTTP 201 and a warning is logged

### Requirement: Consumer Groups for Workers (FD-STREAM-002)

Each worker type MUST consume from its own stream via a dedicated consumer
group: `llm-workers` on `fraud:llm`, `shap-workers` on `fraud:shap`,
`embedding-workers` on `fraud:embeddings`. The group MUST be created
idempotently before consumption (XGROUP CREATE with MKSTREAM, tolerating
BUSYGROUP). Workers MUST XACK each message after successful processing so it
leaves the pending-entries list.

#### Scenario: Worker group created on startup

- GIVEN a worker starts
- WHEN it initializes
- THEN its consumer group exists on its stream (created with MKSTREAM if missing)

#### Scenario: Message acknowledged after processing

- GIVEN a stream message with a valid payload
- WHEN the worker processes it successfully
- THEN the message is XACKed (no longer pending)

#### Scenario: Malformed payload does not crash the loop

- GIVEN a stream message whose payload is not valid JSON
- WHEN the worker reads it
- THEN the worker logs a warning, XACKs it, and continues the loop

### Requirement: Retry Semantics Preserved (FD-STREAM-003)

Workers MUST preserve the existing retry contract: on a recoverable processing
failure the message is re-published to its stream with `retry_count`
incremented (max 3); on success or permanent failure the message is XACKed.
Payload structure and worker outputs MUST remain identical to the list-based
implementation.

#### Scenario: Retry re-publishes with incremented count

- GIVEN a message that fails processing with retry_count 0
- WHEN the worker handles it
- THEN a new event with retry_count 1 is published to the same stream AND the
  original message is XACKed

#### Scenario: Max retries terminates the message

- GIVEN a message that fails processing with retry_count >= 3
- WHEN the worker handles it
- THEN the message is XACKed (permanent failure recorded by the worker) and no
  further event is published

### Requirement: Backward Compatibility During Transition (FD-STREAM-004)

The legacy list-based helpers (`enqueue`, `dequeue`, `enqueue_for_retry`) MUST
remain importable and functional. Workers SHALL attempt to migrate any
leftover messages from the legacy list into their stream on startup so nothing
enqueued before the deploy is lost. Payload structure MUST NOT change.

#### Scenario: Legacy list drained into stream on startup

- GIVEN a legacy list `fraud:shap` holding 2 messages and a worker starting
- WHEN the worker initializes
- THEN both messages are appended to stream `fraud:shap` (XADD) and removed
  from the list

#### Scenario: No legacy list present

- GIVEN no legacy list exists
- WHEN the worker initializes
- THEN startup proceeds without error and zero messages are migrated
