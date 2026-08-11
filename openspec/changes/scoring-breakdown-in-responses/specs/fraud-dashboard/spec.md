# Delta for fraud-dashboard

## Purpose

Makes the API response-shape contract explicit for scoring data delivered by the transaction read endpoints. The dashboard spec already mandates ensemble score + classification in list rows and a full scoring breakdown in detail; this delta specifies how the backend exposes that data (nested `scoring` on detail, `risk_score = ensemble_score` on list) so the contract is testable. `fired_rules` stays out of GET responses (not persisted in `fraud_scores`).

## ADDED Requirements

### Requirement: Transaction Detail Scoring Response (FRD-DASH-SCORE-001)

`GET /api/v1/transactions/{id}` MUST return a nested `scoring` object with `rule_score`, `ml_score`, `ensemble_score`, `threshold`, and `classification` sourced from the persisted `fraud_scores` row for that transaction. `ml_score` is a non-nullable float. When no `fraud_scores` row exists, `scoring` MUST be absent (or null), `risk_score` MUST remain null, and the response MUST still be HTTP 200.

#### Scenario: Detail returns persisted breakdown

- GIVEN a transaction with a fraud_scores row (rule_score=45, ml_score=60, ensemble_score=52, threshold=70, classification="review")
- WHEN `GET /api/v1/transactions/{id}` is requested
- THEN the response has a nested `scoring` object whose five fields match the DB row

#### Scenario: Detail without score stays null

- GIVEN a transaction with no fraud_scores row
- WHEN `GET /api/v1/transactions/{id}` is requested
- THEN the response is HTTP 200 with `scoring` absent/null and `risk_score` null

#### Scenario: Missing transaction returns 404

- GIVEN a transaction id that does not exist
- WHEN `GET /api/v1/transactions/{id}` is requested
- THEN the response is HTTP 404, unchanged

### Requirement: Transaction List Scoring Fields (FRD-DASH-SCORE-002)

`GET /api/v1/transactions` MUST return for every row a `risk_score` (float, null when the transaction has no score) and a `classification` (string, null when no score). Scores SHALL be fetched with a single batched query over the page's transaction ids; the system MUST NOT issue per-row score queries, and pagination behavior MUST remain unchanged.

#### Scenario: All rows scored

- GIVEN a page of transactions each with a fraud_scores row
- WHEN `GET /api/v1/transactions` is requested
- THEN every row has `risk_score` equal to its `ensemble_score` and `classification` equal to the stored value

#### Scenario: Mixed scored and unscored rows

- GIVEN a page where some transactions have scores and others do not
- WHEN `GET /api/v1/transactions` is requested
- THEN scored rows expose populated `risk_score`/`classification` and unscored rows expose null for both

#### Scenario: Scores fetched in one batched query

- GIVEN a page of N transactions
- WHEN `GET /api/v1/transactions` is requested
- THEN scores for the whole page come from exactly one additional query over the page ids (no per-row queries)

#### Scenario: Soft-deleted transaction excluded with its score

- GIVEN a soft-deleted transaction with a persisted score
- WHEN `GET /api/v1/transactions` is requested
- THEN the transaction does not appear in the list and its score does not either

### Requirement: risk_score Ensemble Alias (FRD-DASH-SCORE-003)

On both read endpoints, the existing `risk_score` field MUST remain an alias of `ensemble_score` so existing list consumers (dashboard charts, list sort) keep working without changes.

#### Scenario: Existing consumers keep working

- GIVEN list rows expose `risk_score` equal to `ensemble_score`
- WHEN a dashboard chart or the list sort reads `risk_score`
- THEN the value matches the ensemble score and no consumer change is required

### Requirement: POST Response Unchanged (FRD-DASH-SCORE-004)

`POST /api/v1/transactions` MUST keep returning the existing full `ScoreResponse`, including `fired_rules`; this change MUST NOT alter the POST response shape.

#### Scenario: POST still returns full ScoreResponse

- GIVEN a valid transaction payload
- WHEN `POST /api/v1/transactions` is requested
- THEN the response is the unchanged `ScoreResponse` with rule_score, ml_score, ensemble_score, threshold, classification, and fired_rules

### Requirement: No Schema Migration (FRD-DASH-SCORE-005)

The scoring breakdown MUST be read from the existing `fraud_scores` table; this change MUST NOT introduce an Alembic migration or schema change.

#### Scenario: Existing table reused

- GIVEN the `fraud_scores` table already exists
- WHEN the read endpoints fetch scores
- THEN they query the existing table and no migration is required
