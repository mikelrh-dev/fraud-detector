# Embedding Worker Specification

## Purpose

Redis Streams consumer for the `fraud:embeddings` stream: processes embedding and spoof-detection messages, ACKs them, and recovers stale pending (PEL) entries so no message is stranded by worker restarts or crashes.

## Requirements

### Requirement: Worker Startup Without Recovery Loop Error (EMB-WORKER-001)

The embedding worker MUST start successfully: `process_queue()` MUST NOT raise due to a missing `_recovery_loop` coroutine, and the recovery task lifecycle MUST be guarded — cancelled safely on shutdown, with exceptions from the recovery task logged rather than dying silently.

#### Scenario: process_queue starts cleanly

- GIVEN an instance of the embedding worker with a (mocked) Redis connection
- WHEN `process_queue()` is invoked
- THEN it starts without raising `AttributeError`
- AND `_recovery_loop` is defined on the class and scheduled as an asyncio task

#### Scenario: Recovery task exceptions are logged

- GIVEN `_recovery_loop` raises an exception while running
- WHEN the recovery task completes with the error
- THEN the exception is logged
- AND the exception does not silently terminate logging/monitoring of the loop

#### Scenario: Shutdown cancels recovery task safely

- GIVEN the worker is running with an active recovery task
- WHEN shutdown is triggered
- THEN the recovery task is cancelled without unhandled-task-exception warnings

### Requirement: Stale PEL Recovery via XAUTOCLAIM (EMB-WORKER-002)

The worker's `_recovery_loop` MUST periodically claim pending entries of the `fraud:embeddings` stream consumer group whose idle time exceeds the configured threshold, using the same XAUTOCLAIM pattern as the SHAP worker, and route claimed messages back through `process_message`. Reprocessing SHOULD be idempotent because embeddings are derived data.

#### Scenario: Stale pending message is recovered and processed

- GIVEN the `fraud:embeddings` stream has a consumer group with a message in the PEL idle longer than the claim threshold
- WHEN one iteration of `_recovery_loop` runs
- THEN the message is claimed via XAUTOCLAIM
- AND it is routed through `process_message`
- AND upon successful processing it is ACKed and removed from the PEL

#### Scenario: Fresh pending message is not stolen

- GIVEN a PEL entry whose idle time is below the claim threshold
- WHEN `_recovery_loop` iterates
- THEN the entry is NOT claimed (remains owned by its original consumer)
