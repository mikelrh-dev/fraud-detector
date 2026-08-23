# Tasks: Mobile Optimization

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~430 (8 modified + 5 new files) |
| 400-line budget risk | High |
| Chained PRs recommended | No |
| Suggested split | Single PR (size:exception pre-approved) |
| Delivery strategy | exception-ok |
| Chain strategy | size-exception |

Decision needed before apply: No (size:exception pre-approved by owner)
Chained PRs recommended: No (repo commits direct to master)
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | All mobile-optimization changes | PR 1 (single) | size:exception pre-approved; commits direct to master |

---

## Phase 1: Test Foundations (TDD — RED)

Write failing tests first to lock regression and mobile-class expectations.

- [x] 1.1 Create `frontend/src/tests/helpers/mobile.tsx` — `expectMobileClasses(el, classes[])` and `expectHasClass(el, className)` helpers (~20 LOC)
- [x] 1.2 Create `frontend/src/tests/desktop-regression.test.tsx` — assert md+ classes (`hidden md:flex`, `hidden md:block`, `sm:grid-cols-3`, `sm:flex-row`) survive across Sidebar, TransactionsPage, AlertsPage, ShapAttributionCard, ScoreResultCard (~70 LOC)
- [x] 1.3 Verify RED: `cd frontend && npm test` — regression tests fail (components lack mobile classes yet); existing tests still green
- [x] 1.4 Snapshot current test baseline: confirm all pre-existing tests pass before implementation begins

**Verification**: `cd frontend && npm test` — new regression tests fail (RED), existing tests pass

---

## Phase 2: Sidebar Drawer

Self-contained mobile drawer inside Sidebar.tsx. Pages unchanged.

- [x] 2.1 In `frontend/src/components/Sidebar.tsx`: add `useState(false)` for drawer open state; add `useEffect` for Escape key listener (cleanup on close); add `useEffect` for body scroll lock (`overflow = 'hidden'` / reset)
- [x] 2.2 Add burger button: `md:hidden fixed top-4 left-4 z-50` with hamburger icon, `aria-expanded={open}`, `aria-label="Abrir menú de navegación"`
- [x] 2.3 Add backdrop: `fixed inset-0 bg-black/60 z-[55]` with `onClick → setOpen(false)`, rendered only when open
- [x] 2.4 Add drawer panel: `fixed inset-y-0 left-0 z-[60]` containing same brand/nav/user content as desktop sidebar; `role="dialog"`, `aria-modal="true"`, `aria-label="Menú de navegación"`
- [x] 2.5 Create `frontend/src/tests/Sidebar.drawer.test.tsx` — assert burger `md:hidden` present; simulate click → assert drawer `role="dialog"` visible; simulate Escape → assert closed; simulate backdrop click → assert closed; assert `aria-expanded` toggles (~80 LOC)
- [x] 2.6 Verify GREEN: `cd frontend && npm test` — drawer tests pass, regression tests still RED for other components, existing tests green

**Verification**: `cd frontend && npm test` — Sidebar drawer tests pass

---

## Phase 3: TransactionsPage Dual-Mode

Card list below md, table preserved at md+, overflow-x wrapper.

- [x] 3.1 In `frontend/src/pages/TransactionsPage.tsx`: add `overflow-x-auto` wrapper around existing table container
- [x] 3.2 Add `overflow-x-hidden` to page root `<div>` (prevent horizontal scroll at 375px)
- [x] 3.3 Add mobile card block (`md:hidden`) before table: render `data-testid="tx-card-{tx.id}"` cards showing merchant, amount, date, ClassificationBadge, risk score
- [x] 3.4 Wrap existing table div with `className="hidden md:block"`
- [x] 3.5 Create `frontend/src/tests/TransactionsPage.mobile.test.tsx` — assert mobile card div has `md:hidden`; assert card `data-testid` present; assert table wrapper has `hidden md:block`; assert root has `overflow-x-hidden` (~60 LOC)
- [x] 3.6 Verify GREEN: `cd frontend && npm test` — TransactionsPage mobile tests pass; regression test for TransactionsPage md+ passes; existing tests green

**Verification**: `cd frontend && npm test` — TransactionsPage mobile + regression tests pass

---

## Phase 4: AlertsPage Cards + Touch Targets

Card list below md, touch-target ≥40px, table preserved.

- [x] 4.1 In `frontend/src/pages/AlertsPage.tsx`: add mobile card block (`md:hidden`) with `data-testid="alert-card-{alert.id}"` showing status badge, tx link, classification, timestamp, action buttons
- [x] 4.2 Wrap existing table div with `className="hidden md:block"`
- [x] 4.3 Add `overflow-x-hidden` to page root `<div>`
- [x] 4.4 Apply `max-md:min-h-[40px] max-md:px-3 max-md:text-xs` to ActionButton component (or inline in AlertsPage action buttons)
- [x] 4.5 Create `frontend/src/tests/AlertsPage.touch.test.tsx` — assert mobile card div `md:hidden`; assert action buttons have `max-md:min-h-[40px]`; assert table `hidden md:block` (~50 LOC)
- [x] 4.6 Verify GREEN: `cd frontend && npm test` — AlertsPage touch tests pass; regression test for AlertsPage md+ passes; existing tests green

**Verification**: `cd frontend && npm test` — AlertsPage mobile + regression tests pass

---

## Phase 5: SHAP Stacking + Skeleton + Detail Header

Responsive stacking, skeleton grid, header wrapping.

- [x] 5.1 In `frontend/src/components/ShapAttributionCard.tsx`: change `<li>` from `flex items-center gap-3` to `flex flex-col sm:flex-row items-start sm:items-center gap-1 sm:gap-3`; add `truncate` + `title` to label span; adjust widths to `w-auto sm:w-44`, `w-full sm:w-auto` for bar, `w-auto sm:w-14` for value, `w-auto sm:w-24` for direction
- [x] 5.2 In `frontend/src/pages/ScoreResultCard.tsx` (LoadingSkeleton): change `grid grid-cols-3` to `grid grid-cols-1 sm:grid-cols-3`
- [x] 5.3 In `frontend/src/pages/TransactionDetail.tsx` (header row): change inner div to `flex items-center gap-3 flex-wrap min-w-0`; change tx.id span to include `truncate min-w-0`
- [x] 5.4 Add `overflow-x-hidden` to `frontend/src/pages/DashboardPage.tsx` root div
- [x] 5.5 Update `frontend/src/tests/ShapAttributionCard.test.tsx` — add assertions for stacking classes (`flex-col`, `sm:flex-row`, `truncate`) (~15 LOC)
- [x] 5.6 Verify GREEN: `cd frontend && npm test` — all new + existing tests pass; all regression tests pass

**Verification**: `cd frontend && npm test` — full suite green including all regression tests

---

## Phase 6: DESIGN.md + Final Verification

Documentation + full green suite + build.

- [x] 6.1 Append "Mobile" section to `DESIGN.md` — breakpoints (sm/md), drawer pattern, touch-target rule (≥40px via `max-md:`), card-list pattern, overflow guard strategy (~40 LOC)
- [x] 6.2 Verify `cd frontend && npm test` — all tests green (existing + new mobile/regression)
- [x] 6.3 Verify `cd frontend && npm run build` — production build succeeds
- [x] 6.4 Manual 375px checklist (document in tasks notes): Sidebar drawer opens/closes; Transactions cards render; Alerts cards render with ≥40px buttons; SHAP stacks vertically; no horizontal scroll on any page

**Verification**: `cd frontend && npm test && cd frontend && npm run build` — full green

### 375px Manual Checklist

| Page | Check |
|------|-------|
| Dashboard | Skeletons stack single column, charts ≥260px |
| Transactions | Cards render (merchant, amount, date, badge, score); pagination tappable |
| Alerts | Cards render; action buttons ≥40px |
| Transaction Detail | Header wraps; SHAP rows stack vertically |
| Create Transaction | Inputs full-width, no h-scroll |
| Sidebar | Burger visible; drawer opens/closes via tap/Escape/backdrop |
| All Pages | No horizontal scrollbar at 375px |
