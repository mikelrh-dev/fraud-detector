# Fraud Dashboard Specification

## Purpose

React frontend providing transaction list, alert management, scoring visualizations, and analyst actions (revert, false-positive marking).

## Requirements

### Requirement: Transaction List View

The dashboard SHALL display a paginated, filterable, and sortable list of all transactions.

#### Scenario: Display transactions with scores

- GIVEN transactions exist in the system with fraud scores
- WHEN the dashboard loads the transaction list
- THEN each row shows transaction ID, amount, merchant, timestamp, ensemble score, and classification
- AND rows are color-coded by classification (red=fraud, green=legitimate, yellow=review)

#### Scenario: Filter by classification

- GIVEN transactions with mixed classifications exist
- WHEN the user selects "fraud" filter
- THEN only transactions classified as "fraud" are displayed

#### Scenario: Sort by score descending

- GIVEN a list of transactions with varying scores
- WHEN the user clicks the score column header
- THEN transactions are sorted by ensemble_score in descending order

#### Scenario: Pagination

- GIVEN more than 50 transactions exist
- WHEN the dashboard loads
- THEN only the first 50 transactions are displayed
- AND pagination controls allow navigation to subsequent pages

### Requirement: Transaction Detail View

The dashboard SHALL provide a detailed view of a single transaction with full scoring breakdown.

#### Scenario: View transaction details

- GIVEN a transaction exists with a FraudScore and LLMReport
- WHEN the user clicks on a transaction row
- THEN a detail panel opens showing transaction fields, rule scores, ML score, ensemble score, and LLM report text

#### Scenario: LLM report not yet available

- GIVEN a transaction classified as fraud but LLM report is still pending
- WHEN the user opens the detail view
- THEN the LLM report section shows "Report generating..." with a loading indicator

### Requirement: Alert Management

The dashboard SHALL display active fraud alerts and allow analysts to manage them.

#### Scenario: View active alerts

- GIVEN FraudAlert records exist with status "open"
- WHEN the user navigates to the Alerts view
- THEN all open alerts are displayed with transaction reference, score, and creation time

#### Scenario: Mark alert as reviewed

- GIVEN an open FraudAlert
- WHEN the analyst clicks "Mark as reviewed"
- THEN the alert status changes to "reviewed"
- AND the action is recorded in the audit trail

### Requirement: Analyst Actions

The dashboard SHALL allow analysts to take actions on flagged transactions: revert block and mark as false positive.

#### Scenario: Mark transaction as false positive

- GIVEN a transaction classified as "fraud"
- WHEN an analyst marks it as false positive with a reason
- THEN the transaction classification is updated to "false_positive"
- AND the action is logged with analyst ID, timestamp, and reason

#### Scenario: Revert a blocked transaction

- GIVEN a transaction that was blocked due to fraud classification
- WHEN an analyst with appropriate permissions reverts the block
- THEN the transaction status changes to "reverted"
- AND the revert action is logged in the audit trail

#### Scenario: Analyst cannot action without reason

- GIVEN an analyst attempts to mark a transaction as false positive
- WHEN no reason is provided
- THEN the system rejects the action with a validation error

### Requirement: Scoring Visualizations

The dashboard SHALL provide visual representations of fraud scoring data using charts.

#### Scenario: Score distribution chart

- GIVEN transactions scored in the last 30 days
- WHEN the dashboard renders the scoring overview
- THEN a histogram shows the distribution of ensemble scores

#### Scenario: Score trend over time

- GIVEN daily aggregated fraud scores exist
- WHEN the user views the trend chart
- THEN a line chart shows average fraud score per day over the selected period

### Requirement: Authentication Integration

The dashboard SHALL integrate with the JWT auth system for user authentication.

#### Scenario: Login redirects to dashboard

- GIVEN a user enters valid credentials on the login page
- WHEN the user submits the login form
- THEN the JWT token is stored securely
- AND the user is redirected to the dashboard home

#### Scenario: Expired token prompts re-login

- GIVEN the user's JWT token has expired
- WHEN the user makes an API request from the dashboard
- THEN the system redirects to the login page
- AND preserves the current URL for post-login redirect

### Requirement: Responsive Layout

The dashboard SHALL be usable on desktop and tablet screen sizes.

#### Scenario: Desktop layout

- GIVEN a viewport width >= 1024px
- WHEN the dashboard renders
- THEN the full layout with sidebar navigation and main content area is displayed

#### Scenario: Tablet layout

- GIVEN a viewport width between 768px and 1023px
- WHEN the dashboard renders
- THEN the sidebar collapses to a hamburger menu
- AND content adapts to the narrower viewport

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

---

## Delta: shap-feature-attribution

### Requirement: Detail SHAP Contributions Field (FRD-SHP-001)

`GET /api/v1/transactions/{id}` MUST return `scoring.shap_contributions` as a list of `{feature, contribution}` objects ordered by rank (1..5) when ShapAttribution rows exist for the transaction, and null when none exist. `GET /api/v1/transactions` (list) and `GET /api/v1/transactions/{id}/report` MUST NOT expose this field.

#### Scenario: Detail returns ordered contributions

- GIVEN a transaction with 5 ShapAttribution rows
- WHEN `GET /api/v1/transactions/{id}` is requested
- THEN `scoring.shap_contributions` lists 5 `{feature, contribution}` entries ordered by rank

#### Scenario: No contributions yields null

- GIVEN a transaction with no ShapAttribution rows
- WHEN `GET /api/v1/transactions/{id}` is requested
- THEN the response is HTTP 200 with `scoring.shap_contributions` null

#### Scenario: List endpoint untouched

- GIVEN a transaction with persisted contributions
- WHEN `GET /api/v1/transactions` is requested
- THEN list rows do not include `shap_contributions` and the list shape is unchanged

### Requirement: SHAP Attribution Section (FRD-SHP-002)

The detail view MUST render an "Atribución SHAP" section when `scoring.shap_contributions` is non-null and non-empty: up to 5 bars with direction (positive → fraud red; negative → legit green) and Spanish feature labels. Hidden when null or empty.

#### Scenario: Section renders with direction

- GIVEN detail returns 5 contributions
- WHEN the analyst opens the detail view
- THEN the section renders up to 5 bars with Spanish labels and fraud/legit direction styling

#### Scenario: Section hidden when null

- GIVEN `scoring.shap_contributions` is null
- WHEN the analyst opens the detail view
- THEN the "Atribución SHAP" section is not rendered
