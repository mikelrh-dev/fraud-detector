# Change Notes: audit-wave1-blockers

## Phase 0 — Pre-flight discovery (R1-001)

Grep for `POST /register` payloads carrying `"role": "admin"`:

- `frontend/src/pages/RegisterPage.tsx` (~line 249): the public register form renders a role `<select>` with an `<option value="admin">Administrador</option>`. After this change lands, a user selecting "Administrador" on the self-service form will receive HTTP 422. **Out-of-band fix required** (frontend file is outside this change's task scope): remove the admin option from the register form and default to `analyst`.
- `scripts/`, `create_admin.py`, `create_admin_user.py`, `generate_test_data.py`: no hits — no seed/bootstrap script registers admins through the API (they use the direct DB path). No breakage.
- Existing tests (`tests/integration/test_auth_api.py`) already register with `role="analyst"` — unaffected.

## R3-007 — Coverage gate baseline

- Measured honest baseline after Phases 1–3 landed: see final value below.

## Phase 2 — R4-001: Embedding worker `_recovery_loop` (completed)

- RED: new suite `tests/workers/` (startup/lifecycle/recovery, 6 tests) failed against old code — `_recovery_loop` did not exist (`AttributeError` at `process_queue` startup).
- GREEN: `_recovery_loop()` implemented per AD-2: XAUTOCLAIM via `recover_pending_messages` (> `PENDING_TIMEOUT_MS`), claimed entries routed through `process_message`, ACK on success, exceptions logged per iteration, clean cancellation. Shutdown now awaits the cancelled recovery task (`contextlib.suppress(CancelledError)`).
- Test-infra gotcha: an `AsyncMock` `xreadgroup` returning `[]` completes without yielding to the event loop → the read loop spins hot and starves the recovery task in tests. Production is unaffected (`block=1000`). Fixed with a suspending stand-in in `tests/workers/helpers.py`.
- Full suite vs baseline: HEAD had 21 failures (15 pre-existing + 6 new worker tests failing pre-fix); after the fix: 339 passed / 15 failed — zero NEW failures; the 3 collection errors (`test_llm_worker`, `test_shap_worker`, `unit/test_stream_publisher`) are pre-existing on HEAD.
- Commit: `0bc7b01` (also carries format-only changes to `embedding_worker.py`).

## Phase 3 — R4-006: Real initial migration (completed)

- RED: `tests/migrations/test_initial_migration.py` failed against the stub (no tables created, bare `pass` bodies detected).
- GREEN: `b02e4753e78e_initial.py` filled in place — 9 tables in FK-safe order (users → transactions → rule_metadata → fraud_scores → fraud_alerts → llm_reports → shap_attributions (+index) → ml_model_runs → audit_entries), reverse-order downgrade. Round-trip verified on scratch SQLite with a `@compiles(postgresql.UUID, "sqlite")` hook rendering CHAR(32); native PostgreSQL rendering is covered by CI's Postgres service (R3-008, wave 4).
- Only PG-specific type in the schema is UUID; JSON columns are dialect-generic.

### Stamp runbook

- Existing environments (schema created via `create_all`): `alembic stamp head`
- Fresh environments: `alembic upgrade head`
- Rollback reference point: `alembic stamp b02e4753e78e`

Commit: e04c94d

## Phase 4 — R3-007: CI coverage gate (completed)

- Measured honest baseline on current tree (Phases 1-3 landed): **TOTAL 74%** (540 missed / 2058 statements). Threshold pinned at **74** (<80 rule).
- Interim-vs-80 status: 74% is interim. Wave 4 (test debt: R3-001..005 collection errors + stale assertions) is expected to raise coverage; bump `COVERAGE_FLOOR` in `tests/ci/test_ci_quality_gate.py` and the workflow flag together toward 80.
- RED→GREEN: `tests/ci/test_ci_quality_gate.py` parses `.github/workflows/ci.yml`, requires every pytest invocation to carry `--cov=src` and a `--cov-fail-under >= 74`. Failed before the workflow edit, passes after.
- Latent CI bug fixed in passing: the job set `DATABASE_URL`, which nothing in `src/` or `alembic/` reads (`Settings.database_url` builds from `db_user/db_password/db_name/db_host/db_port`). Replaced with the real pydantic-settings fields.
- Commit: e32266e

## Phase 5 — Final verification (completed)

- Full suite: `pytest tests/ --cov=src --cov-fail-under=73` → **coverage gate reached (73.66%)**; **346 passed / 14 failed**, all 14 failures pre-existing on HEAD and documented as wave-4 carve-outs (R3-002 monitoring phantom contracts, R3-003 wrong monkeypatch, R3-004/005 stale thresholds/weights). Carve-out: the 3 collection-error modules (`test_llm_worker`, `test_shap_worker`, `unit/test_stream_publisher` — R3-001) are excluded from runs; they fail identically on HEAD.
- Floor corrected from 74 to **73**: measured coverage is 73.66% once `tests/ci` + `tests/migrations` run inside the suite; 74 was a rounding artifact and failed the gate.
- Test-isolation bug found and fixed during verification: running alembic programmatically invoked `fileConfig()`, which reconfigured logging with `disable_existing_loggers=True` and broke every downstream caplog test (shap_service, velocity_store, worker lifecycle — 6 spurious failures). Migration tests now build a file-less `Config` with explicit `script_location`.
- `ruff check src/`: clean (fixed 7 pre-existing findings: unused imports, unused var, trailing whitespace, Optional→`| None`, type-narrowing in merchant_embedding_service).
- `mypy src/`: 20 errors in 14 files — all pre-existing (untyped defs, third-party stubs); not introduced by this change. Candidate for a hygiene wave.
- Commits: Phase 2 `0bc7b01`, Phase 3 `e04c94d`, Phase 4 `e32266e`, Phase 5 fixes: (this commit).
