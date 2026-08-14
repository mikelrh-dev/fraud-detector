# Design: Event-Driven Architecture with Redis Streams

## Overview

Replace list-based queues with Redis Streams + consumer groups. Transport
changes only: payload structure, worker outputs, scoring flow, and docker
compose stay identical.

```
┌─────┐   publish_transaction_event()    ┌────────────────────┐
│ API │ ───────────────────────────────▶ │   Redis Streams    │
└─────┘        (XADD, best-effort)       │  fraud:llm          │
                                        │  fraud:shap         │
                                        │  fraud:embeddings   │
                                        └─────────┬──────────┘
                                                  │ XREADGROUP
                                        ┌─────────▼──────────┐
                                        │  Consumer Groups    │
                                        │ llm-workers         │
                                        │ shap-workers        │
                                        │ embedding-workers   │
                                        └─────────┬──────────┘
                                                  │ process
                                        ┌─────────▼──────────┐
                                        │  Workers (async)    │
                                        │  process → XACK     │
                                        └────────────────────┘
```

## Decisions

### D1: Keep 3 separate streams (one per worker type)

`fraud:llm`, `fraud:shap`, `fraud:embeddings`.

- PRO: per-type scaling, per-type backpressure, isolated failure domains,
  enqueue() maps 1:1 to an existing queue name.
- CON: more stream keys to manage (mitigated by `stream_manager.py`).
- REJECTED: single `fraud:events` stream — one slow worker would backlog all
  types and routing logic moves into workers.

### D2: Consumer group per worker type

- `llm-workers` → `fraud:llm`
- `shap-workers` → `fraud:shap`
- `embedding-workers` → `fraud:embeddings`

Multiple instances of the same worker share a group: Redis round-robins
messages between consumers (horizontal scale). `ensure_consumer_group()` is
idempotent (XGROUP CREATE MKSTREAM, BUSYGROUP tolerated).

### D3: Event schema — per-stream payload with shared envelope

Each stream entry is a flat field map:

| Field       | Value                                  |
|-------------|----------------------------------------|
| `event_type`| `llm_report` / `shap_attribution` / `merchant_embedding` |
| `timestamp` | ISO-8601 UTC                           |
| `payload`   | JSON string (exact same dict as today) |

Worker-side `decode_message()` extracts `payload` → `json.loads` — the message
dict the worker already handles. Payload structure is UNCHANGED (FD-STREAM-004).

### D4: Retry strategy — re-publish + XACK (preserves existing contract)

Existing behavior: on recoverable failure the worker re-enqueues with
`retry_count+1` (max 3). With streams:

- `process_*()` returns `True` (done) → **XACK** the entry.
- returns `False` (recoverable) → publish a NEW entry with `retry_count+1`
  to the same stream, then **XACK** the original (it has been accounted for by
  the new entry; keeps PEL clean and mirrors the list LPUSH-back).
- Malformed payload → log warning + XACK (skip, mirroring today's skip).

No dead-letter stream in this change: permanent failures already land in the
audit trail (`shap_failed`, `report_failed`) — that IS the DLQ record.

### D5: Backward compatibility

- `src/core/redis.py` keeps `enqueue`, `dequeue`, `enqueue_for_retry`
  unchanged (other callers/tests still import them).
- Workers call `migrate_legacy_list()` on startup: any leftover messages in
  the old list (`fraud:shap`, `fraud:embeddings`, `fraud:reports`) are
  XADDed into the stream before the consume loop begins, so nothing enqueued
  pre-deploy is lost.
- Worker `QUEUE_NAME` legacy lists: llm worker drains `fraud:reports` into
  `fraud:llm`; shap/embedding drain same-name lists into same-name streams.

### D6: API publish is best-effort

`publish_transaction_event()` wraps Redis I/O; the caller (`transactions.py`)
keeps its try/except so a Redis outage never fails the HTTP request
(FD-STREAM-001).

## File map

| File | Action |
|------|--------|
| `src/core/stream_publisher.py` | NEW — event→stream map, publish, decode helpers |
| `src/core/stream_manager.py`   | NEW — ensure_consumer_group, migrate_legacy_list |
| `src/api/v1/transactions.py`   | MODIFY — enqueue → publish_transaction_event |
| `src/workers/shap_worker.py`   | MODIFY — XREADGROUP loop + XACK + migration |
| `src/workers/embedding_worker.py` | MODIFY — XREADGROUP loop + XACK + migration |
| `src/workers/llm_worker.py`    | MODIFY — XREADGROUP loop + XACK + migration |
| `tests/unit/test_stream_publisher.py` | NEW |
| `tests/unit/test_stream_manager.py`   | NEW |
| `tests/test_shap_worker.py`, `tests/test_llm_worker.py`, `tests/integration/test_transaction_api.py` | MODIFY |

## Sequence (worker consume loop)

```
while True:
    entries = XREADGROUP(GROUP g, CONSUMER c, STREAMS {stream: ">"}, BLOCK 1000)
    if no entries: continue
    for msg_id, fields in entries[stream]:
        message = json.loads(fields["payload"])
        processed = await process_message(message, ...)
        if processed:
            XACK(stream, g, msg_id)          # done or permanent failure
        else:
            message["retry_count"] += 1
            publish_transaction_event(event_type, message)   # new entry
            XACK(stream, g, msg_id)          # original accounted for
```

## Risks

- Two transports live side by side briefly (lists + streams) → migration on
  worker startup closes the gap (D5).
- XREADGROUP with `count=1, block=1000` preserves the current 1-msg-per-iteration
  cadence and keeps tests deterministic via `max_iterations`.
