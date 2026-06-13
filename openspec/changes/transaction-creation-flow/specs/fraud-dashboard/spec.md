# Delta for fraud-dashboard

## Purpose

Extends `fraud-dashboard` with transaction creation flow: form at `/transactions/new`, inline `ScoreResultCard`, paginated `/transactions` list, shared `Sidebar`. All additive — no existing requirements modified.

## ADDED Requirements

### Requirement: Transaction Creation Form (FRD-DASH-CREATE)

System SHALL provide a transaction creation form at `/transactions/new` with client-side validation and inline scoring.

#### Scenario: Valid submission shows ScoreResultCard

- GIVEN analyst logged in on `/transactions/new`
- WHEN they submit valid data (amount>0, 3-char currency, non-empty merchant, 4-digit card_last4)
- THEN `ScoreResultCard` appears below form with scores, classification badge, triggered rules pills
- AND analyst stays on `/transactions/new` (no redirect)

#### Scenario: Invalid form blocks submission

- GIVEN analyst on `/transactions/new`
- WHEN they submit invalid data
- THEN inline field errors per invalid field (amount, currency, merchant_name, card_last4)
- AND submit button disabled until all fields valid

#### Scenario: user_id hidden and auto-filled

- GIVEN analyst logged in (JWT `sub` UUID)
- WHEN the form renders
- THEN `user_id` is hidden and pre-filled from JWT `sub`
- AND no editable input for `user_id` is visible

### Requirement: ScoreResultCard States (FRD-DASH-CARD)

ScoreResultCard SHALL render all classification states without alarmist treatment.

#### Scenario: Loading skeleton

- GIVEN API is processing
- WHEN `isLoading=true`
- THEN skeleton placeholders with `slate-700`/`slate-800` pulse shown

#### Scenario: Legitimate

- GIVEN `classification="legitimate"`
- WHEN card renders
- THEN green `status-approved` badge, no fired rules pills

#### Scenario: Review

- GIVEN `classification="review"`
- WHEN card renders
- THEN yellow `status-flagged` badge, fired rules pills in red-tinted chips

#### Scenario: Fraud (no alarm)

- GIVEN `classification="fraud"`
- WHEN card renders
- THEN red `status-blocked` badge, fired rules pills
- AND no animation, no sound, no modal, no pulse

#### Scenario: ML not trained

- GIVEN `ml_score=null`
- WHEN card renders
- THEN ML section shows "ML: no entrenado" with icon and CTA to training docs
- AND Rule/Ensemble cards render normally

### Requirement: Transaction List Page (FRD-DASH-LIST)

System SHALL provide a dedicated `/transactions` list page with server-side filtering and pagination.

#### Scenario: Paginated table

- GIVEN analyst on `/transactions`
- THEN paginated table shows all transactions (10 per page)

#### Scenario: Filter by status and date

- GIVEN transactions with mixed classifications and dates
- WHEN analyst selects status filter and/or date range
- THEN table refreshes with filtered results, page reset to 1

#### Scenario: Row navigates to detail

- GIVEN transaction list displayed
- WHEN analyst clicks a row
- THEN they navigate to `/transactions/:id`

#### Scenario: Nueva transacción button

- GIVEN analyst on `/transactions`
- THEN "Nueva transacción" button visible, navigates to `/transactions/new`

### Requirement: Shared Sidebar (FRD-DASH-SIDE)

Sidebar SHALL be a shared component across all authenticated pages, using Material Symbols icons and route-based active state.

#### Scenario: Sidebar structure

- GIVEN analyst authenticated on any dashboard page
- THEN sidebar shows: Fraud Detector brand, 3 nav items (Dashboard / Transacciones / Alertas), user info, logout

#### Scenario: Active item by route

- GIVEN analyst navigates between pages
- THEN active nav item highlighted by current route

#### Scenario: Transacciones link works

- GIVEN analyst clicks "Transacciones"
- THEN they navigate to `/transactions`

#### Scenario: Material Symbols icons

- GIVEN sidebar renders
- THEN all icons use Material Symbols Outlined, no emojis

### Requirement: ML-Not-Trained Transparency (FRD-DASH-MLNT)

System SHALL transparently communicate when the ML model is not trained.

#### Scenario: ML card when model absent

- GIVEN `ml_score=null` in scoring response
- WHEN `ScoreResultCard` renders
- THEN ML card shows "ML: no entrenado" with icon and link to training section
- AND Rule/Ensemble cards render normally

### Requirement: Frontend Test Coverage (FRD-DASH-TEST)

New frontend code SHALL be covered by Vitest + RTL + MSW tests.

#### Scenario: Three spec files pass

- GIVEN Vitest + RTL + MSW infrastructure configured
- THEN ≥3 spec files exist: `CreateTransactionPage` smoke, `ScoreResultCard` component (4 states), `TransactionsPage` smoke
- AND `npm test` passes all specs
