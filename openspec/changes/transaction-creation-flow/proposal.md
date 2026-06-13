# Proposal: Transaction Creation Flow

## Intent

Fraud analysts currently cannot create transactions from the UI — the `POST /api/v1/transactions` endpoint exists but has no frontend. The sidebar "Transacciones" link navigates to `/transactions` which has no route, dumping analysts back to the dashboard. This change wires the full transaction creation flow end-to-end: a create-transaction form at `/transactions/new`, inline scoring results via `ScoreResultCard`, a browsable `/transactions` list page, extracted shared `Sidebar` component, and the frontend test infrastructure needed to keep it reliable.

## Scope

### In Scope

| File | Action | Est. LOC |
|------|--------|----------|
| `frontend/src/components/Sidebar.tsx` | **New** — shared sidebar extracted from DashboardPage | ~120 |
| `frontend/src/pages/CreateTransactionPage.tsx` | **New** — form + submit + ScoreResultCard integration | ~200 |
| `frontend/src/pages/ScoreResultCard.tsx` | **New** — score display, classification badge, fired rules, ML-not-trained state | ~120 |
| `frontend/src/pages/TransactionsPage.tsx` | **New** — paginated, filterable, sortable transaction list | ~200 |
| `frontend/src/components/Toaster.tsx` | **New** — sonner toast provider (wrapper) | ~20 |
| `frontend/src/tests/setup.ts` | **New** — Vitest + MSW setup | ~30 |
| `frontend/src/tests/CreateTransactionPage.test.tsx` | **New** — smoke test for create page | ~60 |
| `frontend/src/tests/ScoreResultCard.test.tsx` | **New** — component test (3 states + ML-not-trained) | ~80 |
| `frontend/src/tests/TransactionsPage.test.tsx` | **New** — smoke test for transactions list | ~50 |
| `frontend/src/App.tsx` | **Modify** — add `/transactions`, `/transactions/new`, `/transactions/:id` routes | +10 |
| `frontend/src/pages/DashboardPage.tsx` | **Modify** — replace inline sidebar with shared `<Sidebar>` | -150 |
| `frontend/src/pages/AlertsPage.tsx` | **Modify** — replace inline sidebar with shared `<Sidebar>` | -150 |
| `frontend/src/index.css` | **Modify** — add `status-*` `@theme` tokens per DESIGN.md | +10 |
| `frontend/index.html` | **Modify** — load Inter, JetBrains Mono, Material Symbols | +6 |
| `frontend/package.json` | **Modify** — add sonner, vitest, @testing-library/react, jsdom, msw, @testing-library/jest-dom | +5 |

**Total new LOC**: ~880 **Modified delta**: +~30 **Net**: ~910 LOC changed

### Out of Scope
- ML model training, dataset selection, model metrics (user owns this work)
- Backend service changes (API contract is final; only `POST /api/v1/transactions` and `GET /api/v1/transactions` consumed)
- Oracle Cloud deploy (separate change)
- Full DESIGN.md retrofit of existing pages (only apply to NEW + extracted Sidebar; existing pages keep their current look)
- Multi-user impersonation / role-based `user_id` override
- i18n (UI text stays in Spanish, matches existing pages)
- Dark/light toggle (product is dark-only)
- Bulk transaction import (CSV)
- Real-time alerts via WebSocket

### Capabilities (contract with sdd-spec)

**New capabilities**: None — the change fits within the existing `fraud-dashboard` capability.

**Modified capabilities**:
- `fraud-dashboard`: Requirements expand to include transaction creation flow (form + inline results), full `/transactions` list page, and shared sidebar. The existing spec scenarios for "Transaction List View" and "Transaction Detail View" remain unchanged; new scenarios for creation and inline results are added via a delta spec.

## Approach

### Architecture

Page-level components consume shared primitives:
- **`Sidebar`** — extracted out of DashboardPage, received by all authenticated pages. Accepts `activeItem` prop. Replaces emoji icons with Material Symbols. Brand logo, user info, logout inline.
- **`CreateTransactionPage`** — uses `react-hook-form` for client-side validation (amount > 0, currency = 3 chars, card_last4 = 4 digits, merchant_name >= 1 char). Hidden `user_id` field auto-filled from `authStore.user.id`. On submit, calls `createTransaction()` from `api/transactions.ts`. On success, renders `<ScoreResultCard>` below form. On error, shows toast via `sonner` toast triggered from `useMutation.onError`.
- **`ScoreResultCard`** — pure presentational component. Props: `ScoreResponse | null`, `isLoading`. Renders: ensemble score gauge, rule/ML/ensemble breakdown cards, classification badge (pill), fired rules chips. Handles 5 states: loading (skeleton), legitimate (green), review (yellow), fraud (red, no animation/sound/modal), ML-not-trained (subtle icon + "no entrenado" text + link to docs).
- **`TransactionsPage`** — standalone `/transactions` page. Uses `useQuery` with `listTransactions()`. Filters: status (legitimate/review/fraud), date range. Sortable columns. Paginated. Navigate to `/transactions/new` button, click row to `/transactions/:id`.
- **`Toaster`** — thin wrapper importing `Toaster` from `sonner` and mounting it in `App.tsx`.

### State & Data Flow

- **Form state**: `react-hook-form` with `zod` resolver (or inline validation for v1 simplicity). Local `useState` is acceptable for MVP to minimize deps, but `react-hook-form` is recommended for validation ergonomics.
- **Mutation**: `useMutation` from `@tanstack/react-query` wrapping `createTransaction()`. `onSuccess` sets the result in local state (renders `ScoreResultCard`). `onError` fires `toast.error()`.
- **List query**: `useQuery` in `TransactionsPage` with filters as query key dependencies. `refetchOnMount: true` to see newly created transactions.
- **Auth**: `user_id` sourced from `authStore.user.id` (already populated from JWT `sub` claim). Hidden input, not editable in v1.

### Routing

```
/transactions         → TransactionsPage (list)
/transactions/new     → CreateTransactionPage (form + result)
/transactions/:id     → TransactionDetail (existing, unchanged)
```

### DESIGN.md Alignment

- **`@theme` tokens** in `index.css`: add `--color-status-approved`, `--color-status-flagged`, `--color-status-blocked`, `--color-status-info` using DESIGN.md hex values. These live alongside existing `--color-fraud-*` tokens.
- **Fonts** in `index.html`: `<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">` + Material Symbols CSS.
- **Material Symbols**: replace emoji icons in new + extracted components. Icons needed: `dashboard`, `payments`, `notifications_active`, `add`, `arrow_forward`, `logout`, `shield`, `psychology`, `gavel`, `info`.
- **Existing pages**: DashboardPage and AlertsPage keep their emoji icons in metric cards and non-sidebar areas. Only the sidebar extraction removes emojis.

### Testing Strategy

- **Framework**: Vitest + React Testing Library + MSW (Mock Service Worker) for API mocking
- **Setup file**: `tests/setup.ts` — configures MSW server, cleanup, custom matchers
- **Smoke tests**: one per new page (`CreateTransactionPage`, `TransactionsPage`) — renders without crash
- **Component test**: `ScoreResultCard.test.tsx` — renders 4 states (legitimate, review, fraud, ML-not-trained)
- **Test commands**: `npm test` (vitest), `npm run lint` (eslint), `npx tsc --noEmit`
- **Note**: No existing frontend tests exist — this change bootstraps the infrastructure

## User Stories

- As an analyst, I can create a transaction from the UI and see its risk score without leaving the page.
- As an analyst, I can browse all transactions in `/transactions` with filters (status, date range) and search.
- As an analyst, I see "ML: no entrenado" instead of a misleading 0.0 score.
- As an analyst, I get a non-alarmist visual treatment even when a transaction classifies as fraud.
- As a developer, I can run `npm test` and see component tests pass.

## Acceptance Criteria

1. **Given** I'm logged in, **when** I click "Transacciones" in the sidebar, **then** I land on `/transactions` (not bounced to dashboard).
2. **Given** I'm on `/transactions/new`, **when** I fill the form with valid data and submit, **then** the `ScoreResultCard` appears below the form with rule/ML/ensemble scores, classification badge, and triggered rules pills.
3. **Given** the form has invalid data (e.g., negative amount, 3-digit last4), **when** I try to submit, **then** I see inline field errors and the submit button stays disabled.
4. **Given** the ML model is not trained (`ml_score === null`), **when** the result is rendered, **then** the ML card shows "no entrenado" with a link to docs/training.
5. **Given** a transaction classifies as "fraud", **then** the UI shows red colors but **no** animation, **no** sound, **no** modal.
6. **Given** I'm on `/transactions`, **then** I can filter by status (legitimate/review/fraud) and date range.
7. **Given** I run `npm test`, **then** all Vitest specs pass with at least: 1 smoke test for CreateTransactionPage, 1 component test for ScoreResultCard (4 states), 1 smoke test for TransactionsPage.
8. **Given** I run `npm run lint` and `npx tsc --noEmit`, **then** both pass.

## Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Scope creep — DESIGN.md alignment tempts retrofitting existing pages | Med | Hard scope-limit: existing pages untouched unless they break. Only new + extracted code gets DESIGN.md treatment. |
| Form UX edge cases (large amounts, special chars, malformed UUIDs) | Low | Backend validation catches everything; frontend shows API error from `response.data.detail` via toast. react-hook-form blocks basic validation client-side. |
| No frontend tests currently exist | Med | Test infrastructure is part of this change, not deferred. MSW setup, vitest config, and 3 test files included. |
| Tailwind v4 `@theme` syntax differences from `tailwind.config.js` | Low | Already verified: project uses Tailwind v4 with `@theme` in `index.css`. Design tokens will use that syntax (not the `tailwind.config.js` block in DESIGN.md). |
| Sonner toast library (~3KB dependency) | Low | Accepted. Lightweight, zero-config, production-tested. Matches the product's need for non-intrusive notifications. |
| Stitch HTML inconsistencies (sidebar brands/nav items vary between screens) | Low | Already documented in DESIGN.md normalization rules. Sidebar will match the normalized nav: Dashboard, Transacciones, Alertas. |
| Sidebar extraction may change existing page behavior | Med | Extract Sidebar as a pure presentational component first, then replace in DashboardPage/AlertsPage. Both pages get identical sidebar appearance; only `activeItem` prop changes. Visual regression check required. |

## Estimated Size & Review Budget

- **New files**: ~9
- **Modified files**: ~6
- **LOC forecast**: ~910 (additions + deletions, net)
- **Default budget**: 400 lines (preflight D1)
- **Delivery strategy**: User-selected `ask-always` (C1) for chained PRs
- **Recommendation**: Split into 2 chained PRs at tasks phase:

  **PR1 — Foundation** (~220 LOC): DESIGN.md `@theme` tokens + fonts + Material Symbols loading, Sidebar extraction, route fix, Toaster setup, `package.json` dep updates. Delivers: testable sidebar, working route structure, new deps available.

  **PR2 — Features** (~690 LOC): CreateTransactionPage, ScoreResultCard, TransactionsPage, Vitest tests, MSW setup. Delivers: full working flow end-to-end, verified by tests.

  **PR2 is large** (690 LOC) and may exceed a single review session. Consider further splitting PR2 into `PR2a` (CreateTransactionPage + ScoreResultCard + tests) and `PR2b` (TransactionsPage + its tests) if reviewer bandwidth is constrained. Flag at tasks phase for resolution.

## Success Metrics

- **E2E flow**: login → `/transactions` → click "Nueva transacción" → fill form → submit → see ScoreResultCard → see in list
- **DESIGN.md compliance**: 0 emojis in new code; all semantic colors via `status-*` tokens; Inter + JetBrains Mono loaded; Material Symbols in use
- **Tests**: ≥3 spec files (1 per new page + 1 component test for ScoreResultCard), all passing
- **Lint**: `npm run lint` passes
- **Type check**: `npx tsc --noEmit` passes
- **Build**: `npm run build` succeeds

## Out of Band / Future

- Full DESIGN.md retrofit of existing pages (DashboardPage metric cards, AlertsPage, LoginPage)
- Impersonation / role-based `user_id` override for admin testing
- Bulk transaction import (CSV upload)
- Real-time alerts via WebSocket
- i18n (English locale)
- Dark/light theme toggle (product is dark-only)
- Paginated sidebar user menu / settings
- Rule configuration UI (admin)
