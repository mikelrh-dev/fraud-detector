# Tasks: audit-wave1-blockers

## Review Workload Forecast

| Field | Value |
| ------- | ------- |
| Estimated changed lines | ~180–300 (src+tests+ci+migration) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR with 4 isolated commits (one per finding) |
| Delivery strategy | single-pr |
| Chain strategy | pending |

```text
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low
```

Ordering: Phases 1–4 are independent; Phase 3 (R3-007 CI gate) is deliberately LAST. Strict TDD active: every implementation task is paired RED→GREEN (`pytest tests/ -v --cov=src`).

---

## Phase 0 — Pre-flight discovery

### 0.1 Grep for role=admin register usage

Search `scripts/`, seed scripts, and frontend callers for `POST /register` payloads carrying `"role": "admin"`. Record hits in change notes (out-of-band fix if found). **Done when:** findings documented, no code changed.

## Phase 1 — R1-001: Block self-service admin registration

### 1.1 RED — auth registration tests

Create `tests/api/test_auth_register.py`:

- register `"role":"admin"` → HTTP 422 naming `role`; assert no User persisted.
- no-role / `role=analyst` → persisted with `role="analyst"`.
Create `tests/services/test_auth_register_service.py`:
- parametrized direct calls to `register_user` bypassing schema: any non-analyst role raises domain error, nothing persisted.

Run: all new tests FAIL. **Done when:** red confirmed and recorded.

### 1.2 GREEN — schema + service defense-in-depth

- `src/schemas/auth.py`: `RegisterRequest.role` pattern → `^analyst$`, default `analyst`.
- `src/services/auth.py`: `register_user` independently raises a domain error for any non-analyst role; never persists it.

Run: Phase 1 tests pass; existing suite gains no new failures. Commit (isolated, revertable).

## Phase 2 — R4-001: Embedding worker `_recovery_loop`

### 2.1 RED — startup & lifecycle tests

Create `tests/workers/test_embedding_worker_startup.py` (mocked Redis): `process_queue()` starts without AttributeError; recovery task scheduled.
Create `tests/workers/test_embedding_worker_lifecycle.py`: recovery-task exception logged; shutdown cancels task cleanly without unhandled-exception warnings.
Run: FAIL (missing `_recovery_loop`). **Done when:** red confirmed.

### 2.2 GREEN — implement `_recovery_loop`

Edit `src/workers/embedding_worker.py` per AD-2:

- add `_recovery_loop()` using XAUTOCLAIM pattern via `src/core/stream_dlq.recover_pending_messages` (> PENDING_TIMEOUT_MS); route claimed `(id, fields)` through `process_message`, ACK on success; log exceptions per iteration.
- fix missing `import asyncio, json`; await-suppressed cancellation handling in the existing `finally`.

Run: 2.1 + next step pass.

### 2.3 RED→GREEN — stale PEL recovery behavior

Create `tests/workers/test_embedding_worker_recovery.py`:

- seeded stale PEL entry claimed → processed → ACKed/removed from PEL (write test first, confirm fail, then adjust implementation only if needed).
- fresh entry (idle < threshold) NOT claimed.

Run: full worker test set green. Commit (isolated).

## Phase 3 — R4-006: Real initial migration

### 3.1 RED — migration round-trip test

Create `tests/migrations/test_initial_migration.py` (SQLite where types allow; skip/mark Postgres-only assertions):

- `upgrade head` on scratch DB creates exactly the table set from `Base.metadata.tables`.
- `downgrade base` removes them all.
- asserts stub body (`pass`) replaced.
Run: FAIL against current stub. **Done when:** red confirmed.

### 3.2 GREEN — fill `b02e4753e78e_initial.py` in place

Autogenerate diff vs `Base.metadata` (9 models in `src/models/base.py` hierarchy), hand-verify Postgres-vs-SQLite drift (UUID, JSONB→JSON, server defaults), FK-safe downgrade in reverse order. Single revision, no chaining.

Run: 3.1 passes on scratch DB. **Done when:** upgrade==create_all table set, downgrade empties.

### 3.3 Stamp runbook

Append to change notes (`openspec/changes/audit-wave1-blockers/notes.md`): existing envs run `alembic stamp head`; fresh envs `alembic upgrade head`; rollback `alembic stamp b02e4753e78e`. Commit (isolated).

## Phase 4 — R3-007: CI coverage gate (LANDS LAST)

### 4.1 Measure honest coverage baseline

Run `pytest tests/ -v --cov=src` on current tree (with Phases 1–3 landed). Record measured value; threshold = 80 if ≥80 else measured baseline. Document in change notes.

### 4.2 RED — CI gate parse test

Create `tests/ci/test_ci_quality_gate.py`: file-parse `.github/workflows/ci.yml` pytest step must contain `--cov=src` and `--cov-fail-under=<T>` matching documented baseline. Run: FAIL.

### 4.3 GREEN — pin the gate

Edit `.github/workflows/ci.yml` (~line 68) pytest invocation: append `--cov-fail-under=<T>`. Canonical local command documented as identical. Note interim-vs-80 status + wave-4 follow-up if <80.

Commit last. **Done when:** 4.2 passes; gate cannot silently pass a coverage collapse.

## Phase 5 — Final verification

### 5.1 Full verify

Run `pytest tests/ -v --cov=src --cov-fail-under=<T>`, plus `ruff check .` and `mypy src` if available in the environment. Confirm: blockers fixed here add zero new failures vs pre-existing suite redness (documented carve-out). Confirm each finding is an isolatable commit. **Done when:** verify report appended to change notes.
