# Database Migrations Specification

## Purpose

Alembic migrations that reproduce the full application schema from an empty database, matching SQLAlchemy model metadata exactly, with a downgrade path and a stamping runbook for pre-existing databases built by `create_all`.

## Requirements

### Requirement: Real Initial Migration Covering All Tables (DB-MIG-001)

The initial Alembic migration (`b02e4753e78e`) MUST contain a real `upgrade()` that creates all 9 application tables exactly matching `Base.metadata`, replacing the current empty stub body. `downgrade()` MUST drop all tables in dependency-safe reverse-FK order. The migration chain MUST remain a single "initial" revision with no chained revisions.

#### Scenario: Upgrade produces schema identical to Base.metadata

- GIVEN a clean scratch database with no tables
- WHEN `alembic upgrade head` runs against the new migration
- THEN all 9 expected table names exist (asserted against the set derived from `Base.metadata.tables`)
- AND the resulting schema matches the output of `Base.metadata.create_all()` on an equivalent database — verified by a pytest schema-comparison check (autogenerate diff empty / column-and-index comparison), tolerating only documented engine-specific type mappings between Postgres and SQLite

#### Scenario: Downgrade removes all tables

- GIVEN a scratch database upgraded to head
- WHEN `alembic downgrade base` runs
- THEN none of the 9 application tables remain

#### Scenario: Stub migration body replaced

- GIVEN the file `alembic/versions/b02e4753e78e_initial.py`
- WHEN its contents are inspected
- THEN neither `upgrade()` nor `downgrade()` consists solely of `pass`

### Requirement: Stamp Runbook for Existing Databases (DB-MIG-002)

The change notes MUST include a deploy runbook stating that existing environments created via `create_all` MUST run `alembic stamp head` instead of `alembic upgrade head`. Rollback instructions MUST include the exact command `alembic stamp b02e4753e78e` to point stamped databases back to the stub revision.

#### Scenario: Existing database stamped not upgraded

- GIVEN an existing environment whose schema was created by `Base.metadata.create_all()`
- WHEN the operator follows the runbook
- THEN they execute `alembic stamp head` (not `upgrade`)
- AND subsequent `alembic current` shows the new revision without executing DDL

#### Scenario: Rollback stamp command documented verbatim

- GIVEN the change notes' rollback section
- WHEN it is reviewed
- THEN it contains the exact command `alembic stamp b02e4753e78e`
