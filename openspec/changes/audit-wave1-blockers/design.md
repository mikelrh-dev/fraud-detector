# Design: audit-wave1-blockers

Scope: 4 blocker findings (R1-001, R4-001, R3-007, R4-006). Four independent commits, ≤400 changed lines total. Centered on `packages/coding-agent` scope guard: N/A — repo is fraud-detector; all changes under `src/`, `.github/`, `alembic/`, plus tests.

## Architecture decisions

### AD-1: Defense-in-depth role restriction (R1-001) — reject, don't coerce

- Schema: `RegisterRequest.role` pattern becomes `^analyst$` (default `analyst`). Requests with `"role":"admin"` fail FastAPI validation → HTTP 422 naming `role`.
- Service: `register_user` independently raises a domain error for any non-`analyst` role and never persists it. Rationale: schema validation alone is one drift away from re-exposure; the service-layer invariant is the actual security guarantee. Rejection over silent coercion so misuse is visible in logs/tests.
- No data migration; existing admin accounts are an ops concern (proposal rollback note).

### AD-2: Embedding worker recovery loop now, minimal and replaceable (R4-001)

Implement `_recovery_loop()` on `EmbeddingWorker` following the shap_worker XAUTOCLAIM pattern via `src/core/stream_dlq.recover_pending_messages`. Do **not** remove the dangling `create_task`.

**R4-003 boundary decision (explicit):**

- **Wave 1 implements:** `_recovery_loop` that claims stale PEL entries (> `PENDING_TIMEOUT_MS`) via `recover_pending_messages`, routes each claimed `(message_id, fields)` back through `process_message`, ACKs on success. Task lifecycle guarded: exceptions logged inside a try/except around each iteration + on task completion; cancelled safely in the existing `finally`. Also fixes two latent bugs in touched code: missing `import asyncio, json` and non-awaited recovery-task cancellation (`await` suppressed-cancellation handling).
- **Wave 1 defers (R4-003, wave 3):** retry counters / MAX_RETRIES enforcement before DLQ routing, DLQ redesign, poison-message quarantine semantics. In wave 1, a message whose processing repeatedly fails stays claimed by this consumer and is logged per iteration; it is retried next cycle after idle timeout — acceptable because embeddings/spoof results are derived data with a 1h TTL result key, i.e., reprocessing is idempotent by construction (AD rationale for why wave 1 can ship without retry accounting).
- Keep the loop a simple private method calling the shared helper so wave 3 can swap internals without touching worker startup.

### AD-3: Coverage gate at honest measured baseline (R3-007)

Measure current coverage first; pin CI to that value if <80, else 80. Record number in change notes; monotonic non-decreasing rule (spec) governs future edits. Add `--cov-fail-under=<T>` to `ci.yml:68` pytest step only; canonical local command documented as matching. Landing order within unit: last.

### AD-4: Replace stub migration body in place (R4-006)

Fill `upgrade()`/`downgrade()` of `b02e4753e78e_initial.py` from autogenerate diff against `Base.metadata` (9 models in `src/models/base.py` hierarchy), hand-verified for Postgres-vs-SQLite type drift (UUID, JSONB→JSON fallbacks, server defaults). Single revision, no chaining. Existing DBs get `alembic stamp b02e4753e78e` (runbook below); fresh deploys run `alembic upgrade head`.

## Sequence diagram — embedding worker recovery lifecycle

```text
Worker                 Redis Streams            stream_dlq
  |--process_queue()------>|                          |
  |   ensure_group         |                          |
  |   create_task(_recovery_loop)                     |
  |<--loop: xreadgroup '>'--|  (new msgs -> process_message -> xack)
  |                                                   |
  |   _recovery_loop iteration:                       |
  |   |--xautoclaim(min_idle=300s, count=10)--------->|
  |   |                    |--recover_pending_messages>|
  |   |<---claimed [(id, fields), ...]----------------|
  |   |--for each claim: process_message(fields)      |
  |   |--xack(stream, group, id)                      |
  |   |--except e: log error, sleep(RECOVERY_INTERVAL)|
  | shutdown: finally { cancel(); await suppress }    |
```

## File changes

| Finding | File | Change |
| --- | --- | --- |
| R1-001 | `src/schemas/auth.py` | pattern → `^analyst$`, default `analyst` |
| R1-001 | `src/services/auth.py` | `register_user` rejects non-analyst role (domain error) |
| R4-001 | `src/workers/embedding_worker.py` | add `_recovery_loop`; fix asyncio/json imports; safe task cancel; exception logging |
| R3-007 | `.github/workflows/ci.yml` | append `--cov-fail-under=<baseline>` to pytest step |
| R4-006 | `alembic/versions/b02e4753e78e_initial.py` | real upgrade()/downgrade() for 9 tables |

## Migration strategy (R4-006)

1. Autogenerate against empty scratch DB, hand-diff vs `Base.metadata.create_all()`.
2. Verify FK dependency order; downgrade drops in reverse.
3. Stamp runbook:
   - Existing envs: `alembic stamp head` (after deploying code).
   - Fresh envs: `alembic upgrade head`.
   - Rollback: `alembic stamp b02e4753e78e`.
4. Test uses SQLite where types allow; skip/dialect-mark Postgres-only assertions.

## Test plan (strict TDD: `pytest tests/ -v --cov=src --cov-fail-under=<T>`)

| Scenario | Test file |
| --- | --- |
| register `"role":"admin"` → 422, no user persisted | `tests/api/test_auth_register.py` |
| service-layer rejection of admin role (parametrized call shapes) | `tests/services/test_auth_register_service.py` |
| default/no-role registration → analyst | `tests/api/test_auth_register.py` |
| `process_queue` starts w/o AttributeError; recovery task scheduled | `tests/workers/test_embedding_worker_startup.py` |
| stale PEL claimed via XAUTOCLAIM → processed → ACKed | `tests/workers/test_embedding_worker_recovery.py` |
| fresh PEL entry not stolen (idle < threshold) | same file, separate test |
| recovery-loop exception logged; shutdown cancels cleanly | `tests/workers/test_embedding_worker_lifecycle.py` |
| ci.yml contains `--cov=src --cov-fail-under=<T>`; matches config verify | `tests/ci/test_ci_quality_gate.py` (file-parse test) |
| upgrade creates all 9 tables == Base.metadata; downgrade empties | `tests/migrations/test_initial_migration.py` |

## Risks & rollout

- Coverage gate may turn CI red immediately if baseline <80 — intended signal; land last, document measured value.
- Register change may break seed scripts hitting API with role=admin (grep first; out-of-band fix).
- Recovery loop double-processing is safe (idempotent derived writes, SETEX result keys).
- Each finding is an isolated commit; revert any single one independently.
