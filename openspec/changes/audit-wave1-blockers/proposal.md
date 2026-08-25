# Proposal: audit-wave1-blockers

**Change ID:** `audit-wave1-blockers`
**Source:** `docs/audit-2026-08-24.md` — Wave 1 (blockers only)
**Scope guard:** Exactly the 4 blocker findings below. Criticals from waves 2–5 are explicitly out of scope.

## Why

The audit verdict is 🔴 Action required, driven by 4 blockers: a public privilege-escalation endpoint, a worker that crashes on every startup, a CI gate that cannot fail on coverage collapse, and an empty database migration that makes fresh deploys unusable. Each is small (S/M effort) but each independently breaks a core guarantee: secure identity, stream consumption, quality gating, and schema reproducibility.

## Finding 1 — R1-001 [BLOCKER] Public self-service admin registration

**Problem.** `src/schemas/auth.py:48` validates `role` against `^(admin|analyst)$`, and `src/services/auth.py:44+` (`register_user`) persists whatever role the request carries with no server-side restriction. Any anonymous caller can `POST /api/v1/auth/register` with `"role": "admin"` and obtain full admin privileges.

**Fix direction.**

- Remove `admin` from the register schema's allowed values (`RegisterRequest.role` pattern becomes `^analyst$`, or drop the field entirely and default server-side to `analyst`).
- Enforce in the service layer too (`register_user` ignores/rejects any role other than `analyst`) so the invariant holds regardless of schema drift.
- Admin creation remains via the existing admin bootstrap script path / future admin-managed endpoint (out of scope here).
- TDD: test that registering with `"role":"admin"` either 422s or is coerced to `analyst`; assert no path in `register_user` can persist `role=admin`.

**Risks.** Legitimate flows relying on register-with-admin (e.g., seed scripts hitting the API) would break; grep for such usage before changing. Frontend register form sending role explicitly must tolerate removal.

**Rollback.** Revert the single commit restoring the old schema/service lines. No data or schema changes involved; any admin accounts created during exposure are a pre-existing condition handled by ops (disable those users manually), not by this change.

## Finding 2 — R4-001 [BLOCKER] Embedding worker crashes on startup (missing `_recovery_loop`)

**Problem.** `src/workers/embedding_worker.py:77` calls `asyncio.create_task(self._recovery_loop())`, but `_recovery_loop` is not defined on the class → `AttributeError` in `process_queue()` on every startup. The `fraud:embeddings` stream has no consumer; embedding/spoof-detection work accumulates unconsumed.

**Fix direction.**

- Implement `_recovery_loop()` following the existing pattern in `shap_worker` (XAUTOCLAIM pending messages past idle threshold, reprocess or requeue). Keep it minimal: claim stale PEL entries for this stream/group and route them back through `process_message`.
- Alternatively (if wave 3 will own recovery semantics), the smallest blocker fix is to remove the dangling `create_task` + its `finally: recovery_task.cancel()` so startup succeeds — but only if wave 3 explicitly inherits recovery for this worker. Prefer implementing the loop now using the shap_worker pattern.
- Guard task lifecycle: cancel safely on shutdown, log exceptions from the recovery task so it cannot die silently.
- TDD: unit test that `process_queue` starts without AttributeError and that `_recovery_loop` claims a seeded stale PEL message.

**Risks.** A naive recovery loop could double-process messages (embeddings are derived data → reprocessing should be idempotent; verify). Interaction with wave-3 DLQ redesign: keep implementation simple and replaceable.

**Rollback.** Revert commit restores prior state (worker crashed on startup). Since current behavior is total outage of this consumer, rollback risk is effectively zero; revert also removes the newly added recovery tests.

## Finding 3 — R3-007 [BLOCKER-CI] No coverage floor in CI

**Problem.** `.github/workflows/ci.yml:68` runs `pytest --cov=src --cov-report=xml` with no `--cov-fail-under`; no coverage threshold exists anywhere in CI. `openspec/config.yaml` declares `coverage_threshold: 80` but nothing enforces it. Coverage can silently collapse to 0% while CI stays green.

**Fix direction.**

- Add `--cov-fail-under=80` to the CI pytest invocation.
- Align local/verify command expectations by adding `--cov-fail-under=80` to the project test command usage documented in config verify (keep the canonical command `pytest tests/ -v --cov=src --cov-fail-under=80`).
- Known tension: suite is currently RED (14 failing + 3 collection errors, wave 3–4 scope). If current coverage is already <80, set the gate at the honest current measured value and add a tracked follow-up to raise it to 80 once waves 3–4 land — do not fake green by weakening the gate permanently. Document the chosen number in the change notes.

**Risks.** CI may go red immediately if baseline coverage is below the threshold — that is the intended signal, but coordinate landing order (this can be last in the unit) and record the measured baseline first.

**Rollback.** Revert removes `--cov-fail-under` from ci.yml; one-line, zero runtime impact.

## Finding 4 — R4-006 [BLOCKER] Empty initial Alembic migration

**Problem.** `alembic/versions/b02e4753e78e_initial.py:19-26` has `upgrade()` and `downgrade()` as `pass`. None of the 9 tables exist in migrations; fresh deploys get an empty schema and there is no drift-recovery path. Current databases were evidently built by `create_all`.

**Fix direction.**

- Generate a real migration covering all 9 tables/models matching current SQLAlchemy metadata exactly:
  1. On a clean database, run `alembic upgrade head` against the new migration and diff resulting schema vs `Base.metadata.create_all()` output (e.g., via alembic autogenerate diff or a schema-comparison test).
  2. Implement `downgrade()` dropping all tables in dependency-safe (reverse FK) order.
  3. For existing environments created via `create_all`: standard practice is to stamp heads (`alembic stamp head`) — document this in the change notes/deploy runbook; do not attempt auto-data migration in this wave.
- TDD/testability: add a test that runs the migration chain on a scratch SQLite/Postgres schema (or at minimum asserts `upgrade()` produces all expected table names and `downgrade()` empties them).
- Keep it a single "initial" migration replacing the stub body; no new revisions chained.

**Risks.** Migration drift vs live models (column types, indexes, server defaults) — mitigate by autogenerating then hand-verifying against models; Postgres-vs-SQLite type differences in tests. Existing dev/staging DBs must be stamped, not re-upgraded, or upgrade will fail on existing tables.

**Rollback.** Reverting the commit returns the stub migration; deployed DBs stamped with the new revision would need `alembic stamp b02e4753e78e` to point back — include exact stamp commands in the change notes. Fresh deploys between revert and next fix would again produce empty schemas (current status quo).

## Affected areas

- `src/schemas/auth.py`, `src/services/auth.py` (+ register API test)
- `src/workers/embedding_worker.py`
- `.github/workflows/ci.yml` (+ possibly documented test command)
- `alembic/versions/b02e4753e78e_initial.py` (+ new migration test)

Estimated changed lines per finding: well under the ~400-line budget; treat as 4 independent commits within one change.

## Non-goals

- Token revocation, BOLA, refresh-token typing (wave 2), LLM/SHAP worker durability & DLQ (wave 3), test-suite rot (waves 3–4), conventions/hygiene (wave 5).
- Redesigning role management or adding admin-user CRUD endpoints.
- Raising coverage to 80 if the honest baseline is lower — that follows in later waves.

## Success criteria

1. `POST /api/v1/auth/register` cannot yield a user with `role=admin` (test proves it).
2. Embedding worker starts cleanly; messages on `fraud:embeddings` are consumed and ACKed; stale PEL entries are recovered by `_recovery_loop` (tested).
3. CI fails when coverage drops below the agreed threshold; threshold matches `config.yaml` intent or a documented interim baseline.
4. `alembic upgrade head` on an empty database creates all 9 tables identical to model metadata; `downgrade` removes them; tested.
5. Full verify passes: `pytest tests/ -v --cov=src --cov-fail-under=<threshold>` plus build checks, within the constraints of currently-failing pre-existing tests (documented carve-out if suite redness blocks full green — blockers fixed here must not add failures).
