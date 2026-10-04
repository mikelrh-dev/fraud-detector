# Backup and restore

What to back up, how to restore it, and — more usefully — **which of these
numbers were measured and which were assumed**. Everything below was exercised
on 2026-10-04 against a scratch Postgres; the drill log is at the bottom and
names what it did not cover.

## Scope

### Backed up

The **Postgres database**, via a logical `pg_dump` in custom format. That is
the `postgres_data` volume in `docker-compose.yml`, and it holds everything the
product treats as durable:

| Table | What it holds |
|---|---|
| `transactions` | The transaction ledger (soft-deleted rows included by design, ADR-004) |
| `users` | Accounts, roles, hashed passwords, token revocation state |
| `fraud_scores` | Rule / ML / ensemble scores per transaction |
| `fraud_alerts` | Alerts, review state, analyst label |
| `llm_reports` | Generated explanations |
| `audit_entries` | The immutable audit trail |
| `outbox_events` | Durable staging for the Redis stream publishes |
| `ml_model_runs`, `rule_metadata`, `drift_reference_data`, `shap_attributions` | Provenance and monitoring data |
| `alembic_version` | Which migration the data was written under |

### Deliberately NOT backed up

**Redis.** This is a decision, not an oversight, and the application is built to
survive it:

- The velocity counters are a derived cache. `VelocityStore.get_counts` reads a
  Redis ZSET with a 25h TTL (`VELOCITY_TTL_SECONDS = 90_000`) and **falls back to
  Postgres** (`_pg_counts`) whenever Redis is unavailable, recomputing the same
  5-minute and 1-hour windows from `transactions.created_at` with the same
  soft-delete semantics. Losing Redis costs a slower read path, not data.
- The work streams are a transport, not a record. Rows are written to
  `outbox_events` **in Postgres** inside the scoring transaction and only then
  relayed into Redis; the relay drains staged rows. The durable copy of a
  queued event is the outbox table, which *is* in the dump.

**Host filesystem artifacts.** `models/xgboost_paysim_v1.joblib` (1.46 MB) and
`data/*.csv` are bind-mounted into the containers and are **not** in the
database. A `pg_dump` restore does not bring them back. See "Known gaps".

**Container images and the `frontend` build.** Rebuildable from source.

## Taking a backup

```bash
python scripts/backup_db.py --target-dir ./backups --retention 14
```

Reads the connection from `src.core.config.Settings` (`DB_*`), so there is one
place that knows where the database is. Takes one dump plus a `MANIFEST.json`
holding its SHA-256. The password is passed in `PGPASSWORD`, never on the
command line, because `argv` is readable via `ps` for as long as the process
runs.

`pg_dump` must be **at least as new as the server**. This is not
theoretical: the drill host has a PostgreSQL 15 client against a 16 server, and
the 15 client refuses. Use `--pg-dump /path/to/pg_dump` to point at the right
binary. In the compose stack the simplest correct client is the one already in
the postgres image:

```bash
docker compose exec postgres pg_dump \
  --username="$DB_USER" --dbname="$DB_NAME" --format=custom --no-password
```

### Rotation is opt-in and gated

Nothing is deleted unless you pass **both** flags:

```bash
python scripts/backup_db.py --target-dir ./backups --retention 14 --prune --yes
```

`--prune` alone exits **3** and deletes nothing. The confirmation is a separate
flag on purpose: `--prune --prune` must not read as consent, and
`--prune --retention 1` typed at 03:00 should not delete a week of backups
because the operator was in a hurry. Overwriting an existing dump is gated the
same way, because the file already there is the last known-good copy.

Retention selects by **filename extension** (`.custom.dump`, `.sql`). Keep
anything you would not want rotated out of the backup directory.

## Restoring

Restoring onto a **fresh** database. Do not restore over a live one; the
restore is not transactional across the whole database and a failure leaves a
half-restored schema.

```bash
# 1. Provision an empty database
docker run -d --name restore-target --network <net> \
  -v restore_data:/var/lib/postgresql/data \
  -e POSTGRES_USER=fraud -e POSTGRES_PASSWORD=... -e POSTGRES_DB=fraud_detector \
  postgres:16-alpine

# 2. Restore (positional dump file; --dbname selects the target)
docker cp ./backups/fraud_detector_20261004_150158.custom.dump restore-target:/tmp/r.dump
docker exec restore-target pg_restore -U fraud -d fraud_detector \
  --no-owner --no-privileges /tmp/r.dump

# 3. Bring the schema to head — this is what the API entrypoint does at boot
DB_HOST=restore-target DB_NAME=fraud_detector python -m alembic upgrade head
python -m alembic current     # must print the same revision as `alembic heads`

# 4. Start the stack against it
```

Two flags that are not optional in practice:

- **`--no-owner`** — the dump records `ALTER ... OWNER TO fraud`. Restoring onto
  a host where that role does not exist fails partway through.
- **`alembic upgrade head` after restoring.** A dump faithfully preserves
  whatever revision the source was at, **including being behind head**. In the
  drill the restored database came back at `c4d5e6f7a8b9` while the code head was
  `d7e8f9a0b1c2`, exactly as the source was, and `upgrade head` applied that one
  migration cleanly.

## RPO and RTO

**RPO — currently unbounded, and this is the real finding.** RPO is the
interval between backups, and *nothing schedules this script*. There is no cron
entry, no timer unit, no compose job. Until one exists the honest RPO is
"however long it has been since someone last ran it by hand", which for an
unattended deployment is unbounded. Adding the schedule is the single highest-value
change to backup posture and it is not in this change.

Assuming a daily schedule: **RPO = 24h**, meaning a restore can lose up to a day
of transactions. That is a large window for a fraud ledger, where the
`audit_entries` trail is a compliance artefact. The fix is not more retention,
it is WAL archiving (`archive_mode`) for a point-in-time recovery of minutes or
seconds. Not done here.

**RTO — measured, at this data size.** On 2026-10-04, against 11 tables / 92 rows
producing a 39,623-byte custom dump:

| Step | Measured |
|---|---|
| `pg_dump` (server → file) | **161 ms** |
| `pg_restore` (file → empty database, incl. schema, indexes, FKs) | **312 ms** |
| `alembic upgrade head` (1 pending migration) | applied cleanly, not timed |
| Key tables readable through the ORM | verified, 6 tables + a 3-table join |

So restoring **the data** is under a second. Total RTO is dominated by
everything around it — provisioning a volume, waiting for Postgres to become
healthy, `alembic upgrade head`, starting containers, and above all a human
following this runbook. Call it **minutes, dominated by operator and provisioning
time, not by the data**. The provisioning and application-start steps were *not*
timed, because they are environment-dependent; treat "minutes" as an estimate and
the sub-second figures as the measurements.

**These figures do not scale linearly and were not measured at scale.** At 39 KB
the restore is almost entirely fixed cost (process start, connection, schema and
index creation). Real restore time is dominated by data volume and index build.
A database 1000x this size is not 1000x this number, and no measurement here
supports any extrapolation. Before trusting an RTO, re-run the drill against a
production-sized copy.

## Drill log — what was actually exercised

Run 2026-10-04. Scratch stack: container `fraud-scratch-postgres`, volume
`fraud-scratch-pgdata`, network `fraud-scratch-net` — all separate from
`fraud-detector`'s, all removed afterwards. The dev database was read only, and
re-verified afterwards (26 transactions, unchanged).

**Exercised for real:**

1. `scripts/backup_db.py` run end-to-end against the live dev database, with a
   matching `pg_dump` 16.15 client, producing a 39,623-byte custom dump and a
   `MANIFEST.json`.
2. The confirmation gate, end to end: `--prune --retention 1` without `--yes`
   exited **3**, named the two files it wanted to delete, and deleted nothing.
3. `pg_restore` of that dump into the isolated scratch database: all 12 tables,
   indexes and foreign keys recreated.
4. Row counts compared table by table, source against restored — **all 11 data
   tables and `alembic_version` matched exactly**.
5. `alembic upgrade head` against the restored database, reaching
   `d7e8f9a0b1c2`, matching `alembic heads`.
6. Key tables read back **through the application's own ORM models and engine**,
   not raw SQL: `transactions` 26, `users` 4, `fraud_scores` 16, `fraud_alerts` 5,
   `llm_reports` 9, `audit_entries` 32. The column added by the pending migration
   (`fraud_alerts.analyst_label`) was read successfully, and a
   `transactions -> users -> fraud_scores` join returned rows, so the restored
   foreign keys are real and not merely present in the catalogue.
7. `import src.api.main` succeeded with `DB_NAME` pointing at the restored
   database — the application builds against a restored schema.
8. Timings in the RPO/RTO table above.

**Assumed, not exercised:**

- Restoring at production data volume (see the scaling note above).
- Restoring onto the *actual* production host, with its real roles, extensions
  and settings. `--no-owner` was used to sidestep roles, which is not the same
  thing as a like-for-like production restore.
- `pg_dump` invoked from a scheduler, on a host where the binary version matches.
- Recovery of a corrupt or truncated dump file. **No integrity check runs
  automatically** — nothing verifies that last night's backup is loadable, so a
  silently broken backup is discovered at restore time.
- Restore of the bind-mounted `models/` and `data/` artifacts (they are not in
  the dump; see below).
- TLS, encrypted-at-rest storage, and offsite/remote copies. Out of scope.

## Known gaps

1. **No scheduler.** RPO is unbounded until one exists. Highest priority.
2. **Model artifacts are not backed up.** `models/xgboost_paysim_v1.joblib` is a
   host file. Restoring the database without it leaves the API running with
   "ML model not found — ML scoring will return 0", which is a *silent* scoring
   degradation, not a crash. If that file is not in version control, it needs its
   own backup; if it is, restoring the commit is enough.
3. **No point-in-time recovery.** WAL archiving is not configured, so RPO is
   bounded by the dump interval rather than by anything an operator can dial in.
4. **No backup verification or alerting.** The absence of a failed-backup signal
   is indistinguishable from having no backups at all.
5. **No restore drill on a schedule.** This drill was run once, by hand. A backup
   whose restore path has not been walked is a claim, not a control.
6. **Retention is filename-based**, so an unrelated `.sql` file in the backup
   directory will eventually be rotated away.
