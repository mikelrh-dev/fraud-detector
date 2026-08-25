# Delta for Auth

Scope: finding R1-001 (public self-service admin registration).

## MODIFIED Requirements

### Requirement: User Registration

The system SHALL allow admin users to create new user accounts with assigned roles via the admin-managed endpoint.

Self-service registration (`POST /api/v1/auth/register`) MUST NOT permit the creation of accounts with `role=admin`. The register request schema MUST reject `role=admin` with HTTP 422, and the `register_user` service function MUST independently reject or ignore any requested role other than `analyst` as defense in depth, so that no code path reachable through self-service registration can persist a user with `role=admin`. Admin account creation SHALL remain exclusively on the admin bootstrap / admin-managed path.

(Previously: the register schema validated `role` against `^(admin|analyst)$` and the service persisted whatever role the request carried, allowing anonymous privilege escalation.)

#### Scenario: Admin creates a user

- GIVEN an authenticated admin user
- WHEN a POST /api/v1/auth/users request is made with username, email, password, and role
- THEN a User record is created with hashed password
- AND the response excludes the password field

#### Scenario: Non-admin cannot create users

- GIVEN an authenticated analyst user
- WHEN a POST /api/v1/auth/users request is made
- THEN the system returns HTTP 403 Forbidden

#### Scenario: Duplicate email rejected

- GIVEN a user with email "<analyst@example.com>" already exists
- WHEN a POST /api/v1/auth/users request is made with the same email
- THEN the system returns HTTP 409 Conflict

#### Scenario: Self-service register with role=admin returns 422

- GIVEN no authentication header (anonymous caller)
- WHEN a POST /api/v1/auth/register request is made with valid credentials and `"role": "admin"`
- THEN the API responds HTTP 422 with a validation error naming the `role` field
- AND no User record is created

#### Scenario: Service layer rejects non-analyst role regardless of schema

- GIVEN the `register_user` service function is invoked directly (bypassing schema validation) with `role="admin"`
- WHEN the service processes the request
- THEN it raises a validation/domain error and does not persist any User record
- AND no invocation of `register_user` can result in a persisted user with `role="admin"` (asserted by pytest parametrizing all call shapes)

#### Scenario: Self-service register defaults to analyst

- GIVEN an anonymous caller
- WHEN a POST /api/v1/auth/register request is made with valid credentials and no role field (or `role=analyst`)
- THEN a User record is persisted with `role="analyst"` and the registration succeeds
