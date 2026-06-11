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
