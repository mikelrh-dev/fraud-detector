# Tasks: Event-Driven Architecture with Redis Streams

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ≈ +330/−120 |
| 400-line budget risk | Medium |
| Chained PRs recommended | No (single transport refactor, atomic) |
| Delivery strategy | single-pr (orchestrator-directed: 1 commit for all changes) |
| Chain strategy | pending |

Decision needed before apply: No — orchestrator explicitly requested a single
commit for all changes.

## Phase 1: Stream infrastructure (RED)

- [ ] 1.1 Write `tests/unit/test_stream_publisher.py`: publish maps event_type→stream, XADD fields (event_type/timestamp/payload), unknown event type → ValueError, Redis failure propagates [FD-STREAM-001]
- [ ] 1.2 Write `tests/unit/test_stream_manager.py`: ensure_consumer_group XGROUP CREATE MKSTREAM + BUSYGROUP tolerated; migrate_legacy_list drains list→stream, empty list no-op [FD-STREAM-002, FD-STREAM-004]

## Phase 2: Stream infrastructure (GREEN)

- [ ] 2.1 Create `src/core/stream_publisher.py`: EVENT_STREAM_MAP, `publish_transaction_event(event_type, payload)`, `decode_message(fields)` [FD-STREAM-001]
- [ ] 2.2 Create `src/core/stream_manager.py`: `ensure_consumer_group`, `migrate_legacy_list` [FD-STREAM-002, FD-STREAM-004]

## Phase 3: API publisher wiring (RED → GREEN)

- [ ] 3.1 Update `tests/integration/test_transaction_api.py` TestCreateTransactionShapEnqueue: patch `publish_transaction_event`; assert event_type `shap_attribution` + payload snapshot; legitimate → no shap event; publish failure → 201 [FD-STREAM-001]
- [ ] 3.2 Modify `src/api/v1/transactions.py`: replace 3 `enqueue()` calls with `publish_transaction_event()` (llm_report, shap_attribution, merchant_embedding); keep best-effort try/except [FD-STREAM-001]

## Phase 4: Worker refactors (RED → GREEN)

- [ ] 4.1 Update `tests/test_shap_worker.py` run_worker tests: XREADGROUP loop (message → XACK; retry → re-publish + XACK; malformed → skip + XACK; empty → no-op) [FD-STREAM-002, FD-STREAM-003]
- [ ] 4.2 Modify `src/workers/shap_worker.py`: ensure group, migrate legacy list, XREADGROUP loop, XACK on success/retry, re-publish on retry [FD-STREAM-002, FD-STREAM-003]
- [ ] 4.3 Update `tests/test_llm_worker.py` run_worker tests: same XREADGROUP pattern [FD-STREAM-002, FD-STREAM-003]
- [ ] 4.4 Modify `src/workers/llm_worker.py`: same pattern; legacy list `fraud:reports` → stream `fraud:llm` [FD-STREAM-002, FD-STREAM-003]
- [ ] 4.5 Modify `src/workers/embedding_worker.py`: same XREADGROUP pattern with `embedding-workers` group; remove local `redis_client` import bug path (uses stream fields only) [FD-STREAM-002]

## Phase 5: Verification

- [ ] 5.1 Run `pytest tests/ -v --cov=src` (all pass), `ruff check src/`, `mypy src/` — green [Success criteria]
- [ ] 5.2 Commit all changes: `feat(arch): refactor to event-driven with Redis Streams consumer groups` [Commit]
