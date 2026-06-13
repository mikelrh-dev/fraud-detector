# Tasks: Transaction Creation Flow

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~910 (additions + deletions, net) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Foundation ~220 LOC) → PR 2 (Features ~690 LOC) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Foundation: DESIGN.md fix, fonts/icons, @theme tokens, deps, vitest+MSW, Sidebar extraction, Toaster, routes, sidebar swap | PR 1 | Base = feature/transaction-creation-flow; `npm test` runs, sidebar consistent, /transactions stub works |
| 2 | Features: score helpers, types, useCreateTransaction hook, ScoreResultCard, CreateTransactionPage, TransactionsPage, MSW handlers, 3 test specs | PR 2 | Base = PR 1 branch (immediate previous PR); full flow end-to-end, verified by tests |

## PR1 — Foundation (14 tasks, ~220 LOC)

### Task Dependency Map

```
1.1 (DESIGN.md fix)
 │
 ├─── 1.2 (index.html fonts/icons) ───────┐
 │                                         │
 └─── 1.3 (index.css @theme tokens) ───────┤
                                           │
1.4 (package.json deps) ──────────────┐   │
 │                                     │   │
1.5 (vite.config.ts vitest) ───────────┤   │
 │                                     ├───┤
1.6 (tests/setup.ts) ←─── 1.7 ─── 1.8  │   │
 (setup.ts → server.ts → handlers.ts)  │   │
                                       │   │
1.9 (Sidebar.tsx) ←────────────────────┼───┘ (depends on 1.1, 1.2, 1.3 for tokens/fonts)
 │                                     │
1.10 (Toaster.tsx) ←───────────────────┘ (depends on 1.4 for sonner)
 │
1.11 (main.tsx +Toaster mount) ←──── depends on 1.10
 │
1.12 (App.tsx +routes) ←──────────── depends on 1.9 (Sidebar import)
 │
 ├─── 1.13 (DashboardPage sidebar swap) ──── depends on 1.9
 │
 └─── 1.14 (AlertsPage sidebar swap) ─────── depends on 1.9
```

### Tasks

- [x] **1.1 — Fix DESIGN.md Tailwind v4 syntax** — Modify `DESIGN.md` L177-206: replace `tailwind.config.js` block with `@theme` directive docs. 15 LOC. Deps: none. **N/A — doc-only**.

- [x] **1.2 — Load Google Fonts + Material Symbols** — Modify `frontend/index.html`: add `<link>` for Inter (400,500,600,700), JetBrains Mono, Material Symbols Outlined CSS CDN. +6 LOC. Deps: none. **N/A — config**.

- [x] **1.3 — Add @theme tokens to index.css** — Modify `frontend/src/index.css`: add `--color-status-approved`, `--color-status-flagged`, `--color-status-blocked`, `--color-status-info`, `--color-focus-ring`, `--color-page-bg`, `--color-border-subtle`, `--color-text-primary`, `--color-text-secondary`, `--color-text-muted`, `--color-text-disabled`, `--color-divider`, `--color-primary-container`, `--color-action-hover`, `--spacing-sidebar-width`, `--spacing-max-content`. +16 LOC. Deps: none. **N/A — config**.

- [x] **1.4 — Update package.json with all new deps** — Modify `frontend/package.json`: add deps `sonner`, `react-hook-form`, `zod`, `@hookform/resolvers`; add devDeps `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`, `msw`, `@vitest/coverage-v8`. Add scripts: `"test": "vitest run"`, `"test:watch": "vitest"`, `"test:coverage": "vitest run --coverage"`. +12 LOC. Deps: none. **N/A — config**.

- [x] **1.5 — Add vitest config block to vite.config.ts** — Modify `frontend/vite.config.ts`: add `test: { globals: true, environment: 'jsdom', setupFiles: ['./src/tests/setup.ts'], css: false }` to `defineConfig`. +8 LOC. Deps: 1.4 (conceptual). **N/A — config**.

- [x] **1.6 — Create vitest setup file** — Create `frontend/src/tests/setup.ts`: import `@testing-library/jest-dom/vitest`, MSW server lifecycle (`beforeAll` listen, `afterEach` resetHandlers, `afterAll` close). ~30 LOC. Deps: 1.5. **N/A — infra**.

- [x] **1.7 — Create MSW server** — Create `frontend/src/tests/mocks/server.ts`: `setupServer(...handlers)` export. ~10 LOC. Deps: 1.6. **N/A — infra**.

- [x] **1.8 — Create placeholder MSW handlers** — Create `frontend/src/tests/mocks/handlers.ts`: `export const handlers = []` (empty placeholder). ~5 LOC. Deps: 1.7. **N/A — empty placeholder**.

- [x] **1.9 — Create shared Sidebar component** — Create `frontend/src/components/Sidebar.tsx`: Material Symbols icons (shield, dashboard, payments, notifications_active, logout), 3 nav items (Dashboard / Transacciones / Alertas), brand logo, user section (avatar initials, role, truncated ID), logout action via `useAuthStore` + `useNavigate`. Props: `activeItem: 'dashboard' | 'transactions' | 'alerts'`. Reads `useLocation()` internally to infer active state. ~80 LOC. Deps: 1.1, 1.2, 1.3 (tokens/fonts/icons). **TDD**: Write test verifying sidebar renders nav items, active item highlighted, Material Symbols present. RED → GREEN → REFACTOR.

- [x] **1.10 — Create Toaster component** — Create `frontend/src/components/Toaster.tsx`: thin wrapper importing `<Toaster>` from `sonner`, with DESIGN.md theme (`slate-950` background, red accent). ~20 LOC. Deps: 1.4 (sonner dep). **N/A — config wrapper**.

- [x] **1.11 — Mount Toaster in main.tsx** — Modify `frontend/src/main.tsx`: import `Toaster`, render inside `QueryClientProvider` but outside `BrowserRouter`. +2 LOC. Deps: 1.10. **N/A — config**.

- [x] **1.12 — Add /transactions and /transactions/new routes** — Modify `frontend/src/App.tsx`: import `TransactionsPage` (stub text for PR1) and `CreateTransactionPage` (stub text for PR1). Add routes: `/transactions` → `TransactionsPage`, `/transactions/new` → `CreateTransactionPage`. **Must declare `/transactions/new` BEFORE `/transactions/:id`** to avoid param matching `/new` as `:id`. +14 LOC. Deps: 1.11. **N/A — config (stubs in PR1)**.

- [x] **1.13 — Swap DashboardPage sidebar to shared Sidebar** — Modify `frontend/src/pages/DashboardPage.tsx`: replace inline sidebar (~75 lines) with `<Sidebar activeItem="dashboard" />`. Remove emoji icons from sidebar only (keep metric card emojis). ~5 LOC net change (remove ~75, add ~5). Deps: 1.12. **TDD**: PR2 tests cover this indirectly via navigation flow. In PR1, visual check: sidebar matches DESIGN.md.

- [x] **1.14 — Swap AlertsPage sidebar to shared Sidebar** — Modify `frontend/src/pages/AlertsPage.tsx`: replace inline sidebar (~65 lines) with `<Sidebar activeItem="alerts" />`. ~5 LOC net change. Deps: 1.12. **TDD**: same as 1.13.

**PR1 Acceptance**: `npm test` runs (even with 0 specs), `npm run build` succeeds, sidebar is visually consistent across all 3 pages, "Transacciones" link navigates to `/transactions` (stub), Toaster mounts without error.

---

## PR2 — Features (10 tasks, ~690 LOC)

### Task Dependency Map

```
2.1 (lib/score.ts) ──── 2.2 (types/score.ts)
    │                       │
    │                       └─── 2.3 (useCreateTransaction hook)
    │                             │
    └─── 2.4 (ScoreResultCard) ───┤ (depends on 2.1 for helpers, 2.2 for types)
          │                       │
          └─── 2.5 (CreateTransactionPage) ←── depends on 2.3, 2.4
                │
                └─── 2.6 (TransactionsPage) ←── depends on 2.2 for types (can start parallel with 2.5)

2.7 (handlers.ts update) ←── depends on 2.1 for fixture data shapes

2.8 (CreateTransactionPage.test.tsx) ←── depends on 2.5, 2.7
2.9 (ScoreResultCard.test.tsx) ←─────── depends on 2.4, 2.7
2.10 (TransactionsPage.test.tsx) ←────── depends on 2.6, 2.7
```

### Tasks

- [x] **2.1 — Create score helper library** — Create `frontend/src/lib/score.ts`: pure functions `classificationColor(cls)`, `formatScore(n)`, `isMLTrained(score)`, `classificationLabel(cls)`. ~30 LOC. Deps: none. **TDD**: Write unit test for each helper — RED → GREEN → REFACTOR.

- [x] **2.2 — Create score types** — Create `frontend/src/types/score.ts`: re-export `ScoreResponse` from `api/transactions.ts`, add `ScoreClassification` type union (`'legitimate' | 'review' | 'fraud'`). ~15 LOC. Deps: none (re-exports existing types). **N/A — types only**.

- [x] **2.3 — Create useCreateTransaction hook** — Create `frontend/src/hooks/useCreateTransaction.ts`: react-query `useMutation` wrapper wrapping `createTransaction()`. `onError` fires `toast.error()` with `response.data.detail || 'Error al crear transacción'`. Returns full `UseMutationResult`. ~30 LOC. Deps: 2.2 (types). **TDD**: Write test verifying mutation calls API, toast on error.

- [x] **2.4 — Create ScoreResultCard component** — Create `frontend/src/pages/ScoreResultCard.tsx`: 5-state card. Props: `result: ScoreResponse | null`, `isLoading?: boolean`. States: loading (skeleton pulse), legitimate (green badge), review (yellow + fired rules), fraud (red + no animation/sound/modal), ML-not-trained (`psychology` icon + "ML: no entrenado" + link). Contains score gauge, 3 breakdown cards (rule/ML/ensemble), classification badge pill, fired rules chips. ~120 LOC. Deps: 2.1 (helpers), 2.2 (types). **TDD**: Write test for each state — RED → GREEN → REFACTOR.

- [x] **2.5 — Create CreateTransactionPage** — Create `frontend/src/pages/CreateTransactionPage.tsx`: react-hook-form + zod schema. Fields: amount (number >0), currency (string length 3), merchant_name (string >=1), merchant_category (optional), card_last4 (string length 4 digits), user_id (hidden, auto-filled from `authStore.user.id`). On valid submit → `useCreateTransaction()` → on success set `result` state → render `<ScoreResultCard>` below form. On error → toast. "Nueva Transacción" page title. ~200 LOC. Deps: 2.3 (hook), 2.4 (ScoreResultCard). **TDD**: Write test: fill form → submit → ScoreResultCard visible. Invalid data → submit button disabled + inline errors. user_id hidden. RED → GREEN → REFACTOR.

- [x] **2.6 — Create TransactionsPage** — Create `frontend/src/pages/TransactionsPage.tsx`: useQuery with `listTransactions()`. Filters: status pills (Todas/Legítimo/Revisión/Fraude), date range inputs. Paginated table (10 per page). Empty state. "Nueva transacción" button → navigate to `/transactions/new`. Row click → navigate to `/transactions/:id`. ~180 LOC. Deps: 2.2 (types). **TDD**: Write test: renders without crash, rows visible, filter buttons work, "Nueva transacción" link exists. RED → GREEN → REFACTOR.

- [x] **2.7 — Complete MSW handlers** — Modify `frontend/src/tests/mocks/handlers.ts`: add full handlers — `POST /api/v1/transactions` (reads body, returns fixture by classification), `GET /api/v1/transactions` (respects page/page_size, returns paginated list). Add 4 fixture generators: `legitimate`, `review`, `fraud`, `ml_not_trained`. +80 LOC. Deps: 2.1 (fixture data shapes). **N/A — test infra**.

- [x] **2.8 — Create CreateTransactionPage test** — Create `frontend/src/tests/CreateTransactionPage.test.tsx`: smoke render + form fill + submit → ScoreResultCard visible. Covers FRD-DASH-CREATE. Wraps component in `QueryClientProvider`. ~60 LOC. Deps: 2.5, 2.7. **TDD**: Write BEFORE implementing 2.5 (RED) → make pass (GREEN) → REFACTOR.

- [x] **2.9 — Create ScoreResultCard test** — Create `frontend/src/tests/ScoreResultCard.test.tsx`: 4 test cases — loading skeleton, legitimate (green badge), review (yellow + rules), fraud (red + no animation), ML-not-trained (`psychology` icon + "ML: no entrenado" text). Covers FRD-DASH-CARD, FRD-DASH-MLNT. ~80 LOC. Deps: 2.4, 2.7. **TDD**: Write BEFORE implementing 2.4 (RED) → make pass (GREEN) → REFACTOR.

- [x] **2.10 — Create TransactionsPage test** — Create `frontend/src/tests/TransactionsPage.test.tsx`: smoke render + rows visible + filter interaction + "Nueva transacción" button exists. Covers FRD-DASH-LIST. ~50 LOC. Deps: 2.6, 2.7. **TDD**: Write BEFORE implementing 2.6 (RED) → make pass (GREEN) → REFACTOR.

**PR2 Acceptance**: All 18 spec scenarios satisfied (FRD-DASH-CREATE ×3, FRD-DASH-CARD ×5, FRD-DASH-LIST ×4, FRD-DASH-SIDE ×4, FRD-DASH-MLNT ×1, FRD-DASH-TEST ×1). 3+ test files passing. `npm test` green. `npm run lint` clean. `npx tsc --noEmit` passes. `npm run build` succeeds.

---

## Test Strategy per Task (TDD Mapping)

| Task | TDD? | RED step | GREEN step | Refactor? | Command |
|------|------|----------|------------|-----------|---------|
| 1.1 | N/A | — | — | — | — |
| 1.2 | N/A | — | — | — | — |
| 1.3 | N/A | — | — | — | — |
| 1.4 | N/A | — | — | — | — |
| 1.5 | N/A | — | — | — | — |
| 1.6 | N/A | — | — | — | — |
| 1.7 | N/A | — | — | — | — |
| 1.8 | N/A | — | — | — | — |
| 1.9 | Yes | Write test: sidebar renders nav, active item | Implement Sidebar.tsx | Yes | `npx vitest run src/tests/` |
| 1.10 | N/A | — | — | — | — |
| 1.11 | N/A | — | — | — | — |
| 1.12 | N/A | — | — | — | — |
| 1.13 | N/A* | — | — | — | Visual check |
| 1.14 | N/A* | — | — | — | Visual check |
| 2.1 | Yes | Write unit test for helpers | Implement lib/score.ts | Yes | `npx vitest run` |
| 2.2 | N/A | — | — | — | — |
| 2.3 | Yes | Write test: mutation calls API, toast on error | Implement hook | Yes | `npx vitest run` |
| 2.4 | Yes | Write ScoreResultCard test (4 states) | Implement component | Yes | `npx vitest run` |
| 2.5 | Yes | Write CreateTransactionPage test | Implement page | Yes | `npx vitest run` |
| 2.6 | Yes | Write TransactionsPage test | Implement page | Yes | `npx vitest run` |
| 2.7 | N/A | — | — | — | — |
| 2.8 | Yes | Already written as RED for 2.5 | Confirm green | Yes | `npx vitest run` |
| 2.9 | Yes | Already written as RED for 2.4 | Confirm green | Yes | `npx vitest run` |
| 2.10 | Yes | Already written as RED for 2.6 | Confirm green | Yes | `npx vitest run` |

*\* Tasks 1.13 and 1.14 are pure refactors — behavior unchanged, sidebar extraction preserves identical nav + user + logout. Visual regression check required.*

---

## Commit Strategy by Work Unit

### PR1 Commits

| # | Message | Tasks | Changed Lines | Review Unit |
|---|---------|-------|---------------|-------------|
| 1 | `chore(design): update DESIGN.md to Tailwind v4 @theme syntax` | 1.1 | ~15 | Docs fix, standalone |
| 2 | `chore(deps): add vitest, testing-library, msw, sonner, react-hook-form` | 1.4 | ~12 | Deps + scripts, single concept |
| 3 | `feat(ui): add DESIGN.md @theme tokens and load fonts/icons` | 1.2, 1.3 | +22 | Visual foundation |
| 4 | `chore(test): configure vitest + MSW setup` | 1.5, 1.6, 1.7, 1.8 | +53 | Test infra boots |
| 5 | `feat(ui): extract shared Sidebar component with Material Symbols` | 1.9 | ~80 | Deliverable: reusable sidebar |
| 6 | `feat(ui): mount global Toaster` | 1.10, 1.11 | +22 | Notification system ready |
| 7 | `feat(routing): add /transactions and /transactions/new routes` | 1.12 | +14 | Routes wired, stubs in place |
| 8 | `refactor(pages): use shared Sidebar in Dashboard and Alerts` | 1.13, 1.14 | ~10 | Sidebar consistent everywhere |

### PR2 Commits

| # | Message | Tasks | Changed Lines | Review Unit |
|---|---------|-------|---------------|-------------|
| 1 | `feat(lib): add score classification helpers` | 2.1 | ~30 | Pure logic, testable in isolation |
| 2 | `feat(hooks): add useCreateTransaction mutation hook` | 2.2, 2.3 | ~45 | Types + mutation hook, paired |
| 3 | `feat(ui): add ScoreResultCard with 5 states` | 2.4 | ~120 | Component: commit includes RED test (2.9) + GREEN impl |
| 4 | `feat(ui): add CreateTransactionPage with form and result` | 2.5 | ~200 | Page: commit includes RED test (2.8) + GREEN impl |
| 5 | `feat(ui): add TransactionsPage with filters and pagination` | 2.6 | ~180 | Page: commit includes RED test (2.10) + GREEN impl |
| 6 | `chore(test): complete MSW handlers with 4 fixtures` | 2.7 | +80 | Test fixtures enable all specs |
| 7 | `test: verify all 3 spec files pass` | 2.8, 2.9, 2.10 | ~0 (tests already written) | Green check: `npm test` passes |

---

## Out of Scope (Reminder)

1. **ML model training, dataset selection, model metrics** — user owns this work
2. **Backend service changes** — API contract is final; only existing endpoints consumed
3. **Oracle Cloud deploy** — separate change
4. **Full DESIGN.md retrofit** of existing pages (DashboardPage metric cards, AlertsPage, LoginPage, TransactionDetail) — only new + extracted code gets DESIGN.md treatment
5. **Multi-user impersonation / role-based `user_id` override** — not in scope for v1
6. **i18n** — UI text stays in Spanish (matches existing app)
7. **Dark/light toggle** — product is dark-only
8. **Bulk transaction import (CSV)** — future feature
9. **Real-time alerts via WebSocket** — out of scope
