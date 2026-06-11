# Authentication Specification

## Purpose

JWT authentication, user management, and role-based access control (admin/analyst) for the fraud detection system.

## Requirements

### Requirement: User Registration

The system SHALL allow admin users to create new user accounts with assigned roles.

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

- GIVEN a user with email "analyst@example.com" already exists
- WHEN a POST /api/v1/auth/users request is made with the same email
- THEN the system returns HTTP 409 Conflict

### Requirement: JWT Token Issuance

The system MUST issue JWT tokens upon successful authentication with role claims embedded.

#### Scenario: Successful login

- GIVEN a valid username and password
- WHEN a POST /api/v1/auth/login request is made
- THEN the system returns an access_token and refresh_token
- AND the access_token contains sub (user_id), role, and exp claims

#### Scenario: Invalid credentials

- GIVEN an incorrect password for an existing user
- WHEN a POST /api/v1/auth/login request is made
- THEN the system returns HTTP 401 Unauthorized
- AND the response does not reveal whether the username exists

#### Scenario: Token expiration

- GIVEN an access_token issued with exp = 15 minutes
- WHEN the token is used after 15 minutes
- THEN the system returns HTTP 401 Unauthorized

### Requirement: JWT Token Refresh

The system SHALL allow clients to refresh access tokens using a valid refresh token.

#### Scenario: Refresh token exchange

- GIVEN a valid refresh_token that has not expired or been revoked
- WHEN a POST /api/v1/auth/refresh request is made
- THEN a new access_token is issued
- AND the refresh_token is rotated (old one invalidated, new one issued)

#### Scenario: Expired refresh token

- GIVEN a refresh_token past its expiration
- WHEN a POST /api/v1/auth/refresh request is made
- THEN the system returns HTTP 401 Unauthorized

### Requirement: Role-Based Access Control

The system MUST enforce role-based access on protected endpoints.

#### Scenario: Analyst accesses transaction list

- GIVEN an authenticated analyst user
- WHEN a GET /api/v1/transactions request is made
- THEN the system returns HTTP 200 with transaction data

#### Scenario: Analyst attempts admin-only endpoint

- GIVEN an authenticated analyst user
- WHEN a DELETE /api/v1/transactions/{id} request is made
- THEN the system returns HTTP 403 Forbidden

#### Scenario: Admin accesses all endpoints

- GIVEN an authenticated admin user
- WHEN any protected endpoint is accessed
- THEN the system returns HTTP 200 (authorization passes)

#### Scenario: Unauthenticated access

- GIVEN no Authorization header is provided
- WHEN any protected endpoint is accessed
- THEN the system returns HTTP 401 Unauthorized

### Requirement: Password Security

The system MUST hash passwords using bcrypt before storage and enforce minimum complexity.

#### Scenario: Password hashing

- GIVEN a plaintext password during user creation
- WHEN the User record is persisted
- THEN the stored password is a bcrypt hash
- AND the plaintext is never stored or logged

#### Scenario: Weak password rejected

- GIVEN a password with fewer than 8 characters
- WHEN a POST /api/v1/auth/users request is made
- THEN the system returns HTTP 422 with validation error

### Requirement: Token Blacklisting

The system SHALL support token revocation via a blacklist stored in Redis.

#### Scenario: Logout revokes token

- GIVEN an authenticated user with a valid access_token
- WHEN a POST /api/v1/auth/logout request is made
- THEN the access_token is added to the Redis blacklist
- AND subsequent requests with that token return HTTP 401

#### Scenario: Blacklisted token rejected

- GIVEN a token exists in the Redis blacklist
- WHEN a request is made with that token in the Authorization header
- THEN the system returns HTTP 401 Unauthorized
