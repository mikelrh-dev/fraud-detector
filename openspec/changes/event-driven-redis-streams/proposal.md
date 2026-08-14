# Proposal: Event-Driven Architecture with Redis Streams

## Intent

Refactor the worker pipeline from Redis list-based queues (LPUSH/BRPOP) to
Redis Streams with consumer groups (XADD/XREADGROUP/XACK). This is FASE 4 of
the fraud-detector project: the three async workers (LLM, SHAP, embeddings)
currently poll plain lists; moving to streams gives per-type consumer groups,
horizontal scaling, message acknowledgement, and a pending-entry-list (PEL)
safety net.

## Problem

- Current queues are `fraud:reports` (LLM), `fraud:shap`, `fraud:embeddings` —
  plain Redis lists. BRPOP removes a message atomically even if the worker
  crashes mid-processing → at-most-once delivery, silent message loss.
- No consumer groups: two instances of the same worker compete with BRPOP and
  can reorder/stomp each other.
- No native retry/PEL visibility; retries are manual re-enqueues with
  `retry_count`.

## Scope

- `src/core/stream_publisher.py` (new): `publish_transaction_event`
- `src/core/stream_manager.py` (new): `ensure_consumer_group`
- `src/api/v1/transactions.py` (modified): enqueue → publish
- `src/workers/shap_worker.py`, `src/workers/embedding_worker.py`,
  `src/workers/llm_worker.py` (modified): BRPOP → XREADGROUP + XACK
- Tests: unit + integration updated/added

## Non-Goals

- No docker-compose service definition changes
- No new dependencies (redis-py ships Streams support)
- No changes to scoring flow or worker outputs — transport only
- Legacy `enqueue`/`dequeue`/`enqueue_for_retry` in `src/core/redis.py` kept
  for backward compatibility during the transition

## Rollback Plan

Revert the single commit; the old list-based workers and `enqueue()` calls are
restored verbatim. Streams and lists can coexist in Redis (different keys), so
rollback is safe with no data migration.
