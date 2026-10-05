# Mobile Responsive Layout Specification

## Purpose

Responsive retrofit for the fraud-detection dashboard. Below `md` (768px) = mobile; at `md+` desktop is pixel-identical.

## Requirements

### Requirement: Sidebar Drawer

The system SHALL render a slide-over drawer below `md` (768px). Hamburger button (aria-expanded) opens; Escape/backdrop close. At `md+` fixed sidebar, no hamburger.

#### Scenario: Drawer opens below md

- GIVEN viewport < 768px
- WHEN the user taps hamburger
- THEN a slide-over drawer opens with nav items and backdrop

#### Scenario: Drawer closes via Escape

- GIVEN drawer is open
- WHEN the user presses Escape
- THEN drawer closes

#### Scenario: Drawer closes via backdrop

- GIVEN drawer is open
- WHEN the user taps backdrop
- THEN drawer closes

#### Scenario: Desktop sidebar unchanged

- GIVEN viewport >= 768px
- WHEN dashboard renders
- THEN fixed sidebar visible, no hamburger

### Requirement: Transactions Mobile Cards

The system SHALL render transactions as card lists below `md`. Cards MUST show amount, merchant, date, badge, score. Pagination MUST work. At `md+` 7-col table preserved.

#### Scenario: Card list below md

- GIVEN viewport < 768px
- WHEN transactions page loads
- THEN transactions render as cards with amount, merchant, date, badge, score

#### Scenario: Pagination usable

- GIVEN multiple pages exist
- WHEN viewport < 768px
- THEN pagination controls visible and tappable (min 40px)

#### Scenario: Table preserved at md+

- GIVEN viewport >= 768px
- WHEN transactions page loads
- THEN 7-col table unchanged

### Requirement: Alerts Mobile Cards

The system SHALL render alerts as card lists below `md`. Action buttons MUST have min height 40px. At `md+` table preserved.

#### Scenario: Card list below md

- GIVEN viewport < 768px
- WHEN alerts page loads
- THEN alerts render as cards with action buttons

#### Scenario: Touch target min 40px

- GIVEN viewport < 768px
- WHEN alert buttons render
- THEN each button min height 40px

#### Scenario: Table preserved at md+

- GIVEN viewport >= 768px
- WHEN alerts page loads
- THEN table unchanged

### Requirement: SHAP Card Stacking

The system SHALL stack ShapAttributionCard children vertically below `sm` (640px). Labels MUST truncate with `title` attr. At `md+` horizontal preserved.

#### Scenario: Vertical stacking below sm

- GIVEN viewport < 640px
- WHEN SHAP card renders
- THEN label, value, bar stack vertically per row

#### Scenario: Labels truncate with title

- GIVEN viewport < 640px
- WHEN a label exceeds width
- THEN label truncates with ellipsis, title shows full text

#### Scenario: Horizontal at md+

- GIVEN viewport >= 768px
- WHEN SHAP card renders
- THEN rows horizontal

### Requirement: Page Usability at 375px

The system SHALL ensure create-transaction and auth pages are usable at 375px. Inputs full-width; no horizontal scroll.

#### Scenario: Create transaction at 375px

- GIVEN viewport is 375px
- WHEN create-transaction page renders
- THEN inputs full-width, no horizontal scrollbar

#### Scenario: Auth pages at 375px

- GIVEN viewport is 375px
- WHEN login/register renders
- THEN inputs full-width, no horizontal scrollbar

### Requirement: Dashboard Responsive Skeletons

The system SHALL render skeletons as `grid-cols-1` below `lg`, `lg:grid-cols-2` at `lg+`. Charts render at a fixed height of 200px on every viewport.

<!-- historical: superseded values quoted for traceability only; not normative -->
This requirement previously read `sm:`/`sm:grid-cols-N` and a `>= 260px` chart
height. Neither matched the shipped dashboard: the charts use
`grid-cols-1 lg:grid-cols-2`, and both `ScoreTrendChart` and `ScoreHistogram`
mount `<ResponsiveContainer width="100%" height={200}>`. No ADR, test or code
comment records 260px anywhere, so it was an aspiration written into a
requirements document rather than a decision anyone took.
<!-- end historical -->

Correcting it downward is a documented product compromise, not a silent one: if
200px proves too cramped for a phone, the fix belongs in the chart components
AND here together, not in one of them alone.

#### Scenario: Skeleton grid below lg

- GIVEN viewport < 1024px
- WHEN skeletons render
- THEN cards stack single column

#### Scenario: Chart height on mobile

- GIVEN viewport < 640px
- WHEN ResponsiveContainer renders
- THEN height is 200px, the same fixed height used at every viewport

### Requirement: Global Overflow Guard

The system SHALL NOT introduce horizontal scroll at 375px. Retained tables MUST have `overflow-x-auto` wrapper.

#### Scenario: No horizontal scroll at 375px

- GIVEN viewport is 375px
- WHEN any page renders
- THEN scrollWidth <= viewport width

#### Scenario: Table overflow wrapper

- GIVEN a page retains a table
- WHEN table renders
- THEN wrapped in `overflow-x-auto` container

### Requirement: DESIGN.md Mobile Section

DESIGN.md SHALL include a "Mobile" section documenting breakpoint (md/768px), drawer pattern, touch-target rule (>=40px), and card-list pattern.

#### Scenario: Mobile section exists

- GIVEN DESIGN.md is open
- WHEN analyst searches for mobile docs
- THEN "Mobile" section present with breakpoints, drawer, touch targets, card-list pattern
