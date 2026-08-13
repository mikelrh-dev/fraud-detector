# Velocity Store Specification

## Purpose

Redis-backed sliding-window velocity counts (5-minute and 1-hour transaction counts per user) with Postgres fallback, powering fraud scoring features without per-request Postgres scans.

## Requirements

### Requirement: Velocity Write Path (VEL-STORE-001)

The system MUST record each created transaction into a Redis Sorted Set keyed `velocity:{user_id}:tx`, using the transaction's creation timestamp as the score and the transaction ID as the member. Recording MUST be idempotent per transaction. Recording MUST NOT fail the host request when Redis is unavailable.

#### Scenario: Record transaction with timestamp score

- GIVEN a transaction for user U created at time T
- WHEN the velocity store records it
- THEN a member with the transaction ID and score T exists in `velocity:U:tx`

#### Scenario: Duplicate record is idempotent

- GIVEN the same transaction is recorded twice
- WHEN the store records it again
- THEN the set contains exactly one member for that transaction ID

### Requirement: Velocity Read Path — 5min/1h Counts (VEL-STORE-002)

The system MUST return, for a user, the count of transactions whose timestamps fall within the last 5 minutes and within the last hour (inclusive windows), computed from the user's velocity set in a single round trip (pipeline).

#### Scenario: Both windows populated

- GIVEN a user with 2 transactions in the last 5 minutes and 8 in the last hour
- WHEN velocity counts are requested
- THEN the 5-minute count is 2 AND the 1-hour count is 8

#### Scenario: Boundary transaction at exactly 5 minutes

- GIVEN a transaction whose timestamp is exactly 5 minutes before the request
- WHEN velocity counts are requested
- THEN the transaction is included in both the 5-minute and 1-hour counts

### Requirement: Per-User Isolation (VEL-STORE-003)

Velocity set keys MUST follow the convention `velocity:{user_id}:tx`, and counts MUST be isolated per user.

#### Scenario: Counts unaffected by other users

- GIVEN user A has 3 transactions and user B has 50 in the last hour
- WHEN counts are requested for user A
- THEN the 1-hour count for A is 3

### Requirement: 24-Hour Trim and TTL Renewal (VEL-STORE-004)

The system MUST remove members older than 24 hours before counting, and MUST renew the set's time-to-live when recording, so velocity sets do not grow unbounded.

#### Scenario: Stale members excluded and trimmed

- GIVEN a velocity set with one member 25 hours old and one 1 hour old
- WHEN counts are read
- THEN the 25-hour-old member is removed AND excluded from the 1-hour count

#### Scenario: TTL renewed on write

- GIVEN an existing velocity set with a time-to-live
- WHEN a new transaction is recorded
- THEN the set's time-to-live is renewed

### Requirement: Postgres Fallback (VEL-STORE-005)

When Redis is unavailable or raises an error, the system MUST compute velocity counts from Postgres instead, MUST NOT raise or propagate the error to the host request, and MUST log the failure.

#### Scenario: Redis down at write time

- GIVEN Redis is unreachable
- WHEN a transaction is recorded and counted
- THEN the request completes using Postgres-derived counts without error

#### Scenario: Redis down at read time

- GIVEN Redis is unreachable
- WHEN velocity counts are requested
- THEN counts are derived from Postgres AND a warning is logged

### Requirement: Soft-Delete Accounting (VEL-STORE-006)

Soft-deleted transactions MAY remain in the velocity set and MAY be counted until trimmed by the 24-hour window (accepted, documented behavior).

#### Scenario: Deleted transaction counted within 24 hours

- GIVEN a transaction is soft-deleted but its member remains in the set
- WHEN counts are requested within 24 hours of the deletion
- THEN the transaction MAY be included in the counts

### Requirement: Configuration Toggle (VEL-STORE-007)

When the `velocity_store_enabled` flag is disabled, the system MUST NOT use the Redis velocity path and MUST compute velocity from Postgres only.

#### Scenario: Flag disabled falls back to Postgres

- GIVEN `velocity_store_enabled=false`
- WHEN a transaction is scored
- THEN no Redis velocity set is read or written AND Postgres-only counts are used