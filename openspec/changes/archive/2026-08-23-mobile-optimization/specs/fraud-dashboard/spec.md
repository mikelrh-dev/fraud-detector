# Delta for Fraud Dashboard

## MODIFIED Requirements

### Requirement: Responsive Layout

The dashboard SHALL be usable on desktop, tablet, and mobile screen sizes (375px+). At `md+` (>=768px) the layout MUST remain pixel-identical to today: fixed sidebar visible, flex layouts intact, 7-column transaction table, alerts table. Below `md` the sidebar becomes a slide-over drawer, tables become card lists, touch targets >=40px, and all pages are usable at 375px with no horizontal scroll.

(Previously: covered desktop+tablet only; no mobile scenarios)

#### Scenario: Desktop layout unchanged

- GIVEN viewport width >= 1024px
- WHEN the dashboard renders
- THEN the full layout with sidebar navigation and main content area is displayed

#### Scenario: Tablet layout

- GIVEN viewport width between 768px and 1023px
- WHEN the dashboard renders
- THEN the sidebar collapses to a hamburger menu
- AND content adapts to the narrower viewport

#### Scenario: Mobile sidebar drawer

- GIVEN viewport width < 768px
- WHEN the dashboard renders
- THEN the sidebar is replaced by a hamburger button that opens a slide-over drawer

#### Scenario: Mobile transaction cards

- GIVEN viewport width < 768px
- WHEN the transaction list loads
- THEN transactions render as card lists (amount, merchant, date, badge, score visible)

#### Scenario: Mobile alert cards with touch targets

- GIVEN viewport width < 768px
- WHEN the alerts page loads
- THEN alert cards display with action buttons of minimum height 40px

#### Scenario: Mobile no horizontal scroll

- GIVEN viewport width is 375px
- WHEN any page renders
- THEN no horizontal scrollbar appears
