# Design: Transaction Creation Flow

## 1. Context

Analysts currently cannot create transactions from the UI — `POST /api/v1/transactions` exists (see `frontend/src/api/transactions.ts` L86-91) but has no frontend. The sidebar "Transacciones" link navigates to `/transactions` which has no route (see `App.tsx`), dumping analysts back to `/dashboard`. Both `DashboardPage` and `AlertsPage` duplicate an inline sidebar with emoji icons that violate `DESIGN.md`'s "no emojis" rule.

**Locked-in decisions** (do not re-litigate):
- **Scope**: Full slice C — sidebar extraction + creation flow + list page + tests + DESIGN.md alignment
- **Post-create UX**: User stays on `/transactions/new`, `ScoreResultCard` renders below the form
- **`user_id`**: Hidden field, auto-filled from `authStore.user.id`
- **ML-not-trained state**: "ML: no entrenado" text + icon + link, never `0.0`
- **Fraud tone**: Neutral-professional — red colors but no animation, no sound, no modal
- **Delivery**: 2 chained PRs (PR1 Foundation ~220 LOC, PR2 Features ~690 LOC)

## 2. Architecture Overview

### Component Diagram

```
                            App.tsx
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         Dashboard       Transactions    CreateTransaction
         Page             Page           Page
              │               │               │
              └───────┬───────┘               │
                      │                       │
                <Sidebar>               <ScoreResultCard>
                  activeItem                   │
                      │                  <ScoreGauge>
                      │            <BreakdownCard> × 3
                      │            <ClassificationBadge>
                      │            <FiredRulesChips>
                      │
               <Toaster> (sonner, mounted in main.tsx)
```

### Data Flow: Create Transaction

```
Form (react-hook-form)
  │
  │ onSubmit → zap amount, currency, merchant_name, card_last4, user_id
  │
  ▼
useCreateTransaction (useMutation)
  │
  │ mutateAsync(data) → apiClient.post("/transactions", data)
  │
  ▼
axios interceptor (client.ts L11-26) → attaches JWT from auth-storage
  │
  ▼
POST /api/v1/transactions (backend)
  │
  │ → RuleEngine → ML → Ensemble → persist
  │
  ▼
ScoreResponse ← 201
  │
  ├── onSuccess → set result in local state → render <ScoreResultCard>
  └── onError   → toast.error(response.data.detail)
```

### Auth Flow

```
authStore.user.id (from JWT `sub` claim, decoded in authStore.login)
  │
  ▼
CreateTransactionPage reads via useAuthStore(s => s.user.id)
  │
  ▼
Hidden <input type="hidden" name="user_id" value={user.id} />
  │
  ▼
Submitted as part of CreateTransactionRequest
```

### Error Flow

| Error Location | Presentation | Mechanism |
|---|---|---|
| Field validation (client) | Inline red text below input | react-hook-form error state |
| API returns `{detail: string}` | `toast.error(detail)` | sonner, triggered in `useMutation.onError` |
| 401 (expired token) | Redirect to `/login` | axios response interceptor (client.ts L29-41) |
| Network error | `toast.error("Error de conexión")` | sonner, triggered in `useMutation.onError` |

### Test Data Flow

```
Test spec (Vitest + RTL)
  │
  ├── render(<CreateTransactionPage />)
  │
  ├── MSW server intercepts POST /api/v1/transactions
  │     └── returns fixture (legitimate | review | fraud | ml_score: null)
  │
  └── assert: ScoreResultCard visible, correct badge, no API call to real backend
```

## 3. File & Folder Structure

```
frontend/
├── index.html                                *(modified: +Inter, JetBrains Mono, Material Symbols CDN)*
├── package.json                              *(modified: +sonner, +react-hook-form, +zod, +vitest, +@testing-library/react, +@testing-library/jest-dom, +@testing-library/user-event, +jsdom, +msw, +@vitest/coverage-v8)*
├── vite.config.ts                            *(modified: +vitest config block)*
├── tsconfig.json                             *(unchanged)*
├── src/
│   ├── main.tsx                              *(modified: wrap with <Toaster>)*
│   ├── App.tsx                               *(modified: add /transactions, /transactions/new routes)*
│   ├── index.css                             *(modified: +@theme tokens for status-*, spacing-*, text-*, border-*)*
│   ├── api/
│   │   ├── client.ts                         *(unchanged)*
│   │   ├── auth.ts                           *(unchanged)*
│   │   ├── alerts.ts                         *(unchanged)*
│   │   └── transactions.ts                   *(unchanged — already exposes createTransaction, listTransactions, ScoreResponse)*
│   ├── store/
│   │   └── authStore.ts                      *(unchanged)*
│   ├── components/
│   │   ├── **Sidebar.tsx**                   *(NEW — extracted, Material Symbols, props: activeItem)*
│   │   ├── **Toaster.tsx**                   *(NEW — sonner wrapper with DESIGN.md theme)*
│   │   ├── TransactionTable.tsx              *(unchanged)*
│   │   ├── ScoreHistogram.tsx                *(unchanged)*
│   │   └── ScoreTrendChart.tsx               *(unchanged)*
│   ├── pages/
│   │   ├── LoginPage.tsx                     *(unchanged)*
│   │   ├── DashboardPage.tsx                 *(modified: replace inline sidebar with <Sidebar>)*
│   │   ├── AlertsPage.tsx                    *(modified: replace inline sidebar with <Sidebar>)*
│   │   ├── TransactionDetail.tsx             *(unchanged — out of band for retrofit)*
│   │   ├── **CreateTransactionPage.tsx**     *(NEW — form + react-hook-form + useMutation + ScoreResultCard)*
│   │   ├── **ScoreResultCard.tsx**           *(NEW — 5 states, props: result: ScoreResponse | null, isLoading: boolean)*
│   │   └── **TransactionsPage.tsx**          *(NEW — list, filters, pagination, "Nueva transacción" button)*
│   ├── hooks/
│   │   └── **useCreateTransaction.ts**       *(NEW — react-query useMutation wrapper)*
│   ├── lib/
│   │   └── **score.ts**                      *(NEW — pure helpers: classificationColor, formatScore, isMLTrained)*
│   ├── types/
│   │   └── **score.ts**                      *(NEW — re-exports + extends ScoreResponse with derived fields)*
│   └── tests/
│       ├── **setup.ts**                      *(NEW — vitest setup, MSW server start, jest-dom matchers)*
│       ├── **mocks/server.ts**               *(NEW — setupServer from MSW for node)*
│       ├── **mocks/handlers.ts**             *(NEW — MSW handlers for /transactions endpoints)*
│       ├── **CreateTransactionPage.test.tsx** *(NEW — smoke render + form interaction)*
│       ├── **ScoreResultCard.test.tsx**      *(NEW — 4 state renders via fixtures)*
│       └── **TransactionsPage.test.tsx**     *(NEW — smoke render with mocked query)*
```

## 4. Component Contracts

### Sidebar

| Property | Type | Required | Description |
|---|---|---|---|
| `activeItem` | `'dashboard' \| 'transactions' \| 'alerts'` | Yes | Which nav item is highlighted |

| Aspect | Detail |
|---|---|
| State | None (stateless presentational) |
| Side effects | None — navigation via `useNavigate` from react-router-dom |
| Children | Brand logo (shield icon + "Fraud Detector"), 3 nav items with Material Symbols, user info section (avatar initials + role + truncated ID), logout button |
| Tests | Scenario FRD-DASH-SIDE (structure, active item, Material Symbols, Transacciones link) |
| Icons | `dashboard`, `payments`, `notifications_active`, `logout`, `shield` |

### CreateTransactionPage

| Property | Type | Required | Description |
|---|---|---|---|
| (none) | — | — | Page-level, no props |

| Aspect | Detail |
|---|---|
| State | `result: ScoreResponse \| null` (useState) — set by `useMutation.onSuccess` |
| Form | `react-hook-form` + `zod` schema. Fields: `amount` (number, >0), `currency` (string, length 3), `merchant_name` (string, >=1), `merchant_category` (string, optional), `card_last4` (string, length 4, digits), `user_id` (hidden, auto-filled) |
| Side effects | `useCreateTransaction` (useMutation) — submits form data, sets result or toasts error |
| Children | Form inputs + submit button + `<ScoreResultCard>` (rendered conditionally below form) |
| Tests | FRD-DASH-CREATE (valid submit shows card, invalid blocks, user_id hidden) |

### ScoreResultCard

| Property | Type | Required | Description |
|---|---|---|---|
| `result` | `ScoreResponse \| null` | Yes | The scoring result; null when no data |
| `isLoading` | `boolean` | No (default false) | Whether the API is processing |

| State | Condition | What Renders |
|---|---|---|
| **Loading** | `isLoading === true` | Skeleton placeholders (slate-700/800 pulse, 3 column grid) |
| **Legitimate** | `result.classification === 'legitimate'` | Green badge, ensemble score gauge, 3 breakdown cards (rule/ML/ensemble), no fired rules |
| **Review** | `result.classification === 'review'` | Yellow badge, same structure, fired rules in red-tinted chips |
| **Fraud** | `result.classification === 'fraud'` | Red badge, same structure, fired rules chips. **No animation, no sound, no modal** |
| **ML Not Trained** | `result.ml_score === null` (any classification) | ML card shows "ML: no entrenado" with `psychology` icon + link to docs. Rule/Ensemble cards render normally |

| Aspect | Detail |
|---|---|
| State | None (pure presentational) |
| Side effects | None |
| Children | Score gauge (gradient bar + ensemble score), 3 breakdown cards (rule/ML/ensemble), classification badge (pill), fired rules chips (when present) |
| Tests | FRD-DASH-CARD (loading, legitimate, review, fraud, ML-not-trained) + FRD-DASH-MLNT |

### TransactionsPage

| Property | Type | Required | Description |
|---|---|---|---|
| (none) | — | — | Page-level, no props |

| Aspect | Detail |
|---|---|
| State | Filters (status, date_from, date_to), pagination (page), all via useState |
| Side effects | `useQuery({ queryKey: ['transactions', filters], queryFn: () => listTransactions(filters), refetchOnMount: 'always' })` |
| Children | Filter bar (status pills, date range inputs), paginated table, "Nueva transacción" button, empty state |
| Tests | FRD-DASH-LIST (paginated table, filter by status, row navigates to detail, Nueva transacción button) |

### Toaster

| Property | Type | Required | Description |
|---|---|---|---|
| `position` | `'top-right'` | No (default) | Toast position per sonner API |

| Aspect | Detail |
|---|---|
| State | None (thin wrapper) |
| Side effects | None (mounts `sonner`'s `Toaster` with DESIGN.md theme: `slate-950` background, red accent) |
| Children | None (renders the sonner toast container) |
| Tests | Not directly tested (integration via toast.error calls) |

### useCreateTransaction

```typescript
function useCreateTransaction(): UseMutationResult<ScoreResponse, Error, CreateTransactionRequest>
```

| Aspect | Detail |
|---|---|
| Returns | Standard react-query `UseMutationResult`: `mutate`, `mutateAsync`, `isLoading` (renamed `isPending` in v5), `error`, `data` |
| `mutationFn` | Calls `createTransaction(data)` from `api/transactions.ts` |
| `onError` | Fires `toast.error(err.response?.data?.detail || 'Error al crear transacción')` |
| Tests | Backed by MSW handler returning fixture responses |

## 5. Routing Map

Final routes in `App.tsx`:

```
/login                  → LoginPage                    (public)
/dashboard              → DashboardPage                (protected)
/transactions           → TransactionsPage             (protected) ← NEW
/transactions/new       → CreateTransactionPage        (protected) ← NEW
/transactions/:id       → TransactionDetail            (protected, unchanged)
/alerts                 → AlertsPage                   (protected, unchanged)
*                       → Navigate to /dashboard       (protected redirect)
```

`ProtectedRoute` wraps all but `/login` (existing pattern from `App.tsx` L9-17).

**Route order matters**: `/transactions/new` must be declared BEFORE `/transactions/:id` so react-router matches the literal `/new` before the param `:id`.

## 6. State Management

| Domain | Mechanism | Details |
|---|---|---|
| Form state | react-hook-form + zod | Client-side validation, minimal re-renders, hidden `user_id` |
| Submission | react-query `useMutation` | Wraps `createTransaction()`. Result stored in local `useState` to render ScoreResultCard below form. Error surfaced via `sonner` toast |
| Transaction list | react-query `useQuery` | Keyed by `{ page, page_size, status, date_from, date_to }`. `refetchOnMount: 'always'` to surface newly created transactions |
| Auth | Zustand (`useAuthStore`) | Already wired. `user.id` consumed from JWT `sub` claim |
| Notifications | `sonner` | `toast.success()` on success, `toast.error()` on failure. Global `Toaster` mounted in `App.tsx` |
| Sidebar active state | Inferred from `useLocation().pathname` | No prop drilling — `Sidebar` reads `useLocation()` internally |

## 7. API Integration

| Endpoint | Function | Already Exists? |
|---|---|---|
| `POST /api/v1/transactions` | `createTransaction(data)` → `ScoreResponse` | Yes (transactions.ts L86-91) |
| `GET /api/v1/transactions` | `listTransactions(filters)` → `TransactionListResponse` | Yes (transactions.ts L56-71) |
| `GET /api/v1/transactions/:id` | `getTransaction(id)` → `Transaction` | Yes (transactions.ts L76-81) |

**Error format**: Backend returns `{ detail: string }`. We surface `response.data.detail` via `toast.error()` for non-field errors. No structured field-error mapping from the API yet — react-hook-form client-side validation catches field issues before they reach the server.

**MSW handlers** (in `tests/mocks/handlers.ts`):

```typescript
// Mock POST /api/v1/transactions — inspect request body, return fixture by classification
http.post('*/api/v1/transactions', async ({ request }) => {
  const body = await request.json();
  // Return one of 4 fixture responses based on test needs
  return HttpResponse.json(scoreResponseFixture(body, 'legitimate'));
});

// Mock GET /api/v1/transactions — respect page/page_size query params
http.get('*/api/v1/transactions', ({ request }) => {
  const url = new URL(request.url);
  const page = Number(url.searchParams.get('page') || 1);
  return HttpResponse.json(transactionListFixture(page));
});
```

**Fixture variants** (used interchangeably in tests):
- `legitimate`: `{ classification: "legitimate", ml_score: 12.3, ensemble_score: 15.0, fired_rules: [] }`
- `review`: `{ classification: "review", ml_score: 55.0, ensemble_score: 62.0, fired_rules: ["high_amount"] }`
- `fraud`: `{ classification: "fraud", ml_score: 88.0, ensemble_score: 91.0, fired_rules: ["high_amount", "high_velocity", "new_merchant"] }`
- `ml_not_trained`: `{ classification: "legitimate", ml_score: null, ensemble_score: 15.0, fired_rules: [] }`

## 8. Testing Strategy

### Configuration

| Setting | Value | Where |
|---|---|---|
| Test runner | Vitest | `vite.config.ts` — `test: { globals: true, environment: 'jsdom', setupFiles: ['./src/tests/setup.ts'], css: false }` |
| DOM matchers | `@testing-library/jest-dom` | `tests/setup.ts` — `import '@testing-library/jest-dom'` |
| API mocking | MSW v2 (node) | `tests/mocks/server.ts` — `setupServer(...handlers)` |
| Query wrapper for tests | `QueryClientProvider` with fresh `QueryClient` | Each test wraps component per RTL conventions |

### Test Files

| File | Type | Scenarios Covered | Spec Refs |
|---|---|---|---|
| `CreateTransactionPage.test.tsx` | Integration (smoke + interaction) | Renders without crash, form submission shows ScoreResultCard, invalid data blocked, user_id hidden | FRD-DASH-CREATE |
| `ScoreResultCard.test.tsx` | Component (4 states) | Loading skeleton, legitimate (green), review (yellow + rules), fraud (red + no animation), ML-not-trained icon + text | FRD-DASH-CARD, FRD-DASH-MLNT |
| `TransactionsPage.test.tsx` | Integration (smoke) | Renders without crash, table shows data, filter buttons work, "Nueva transacción" link exists | FRD-DASH-LIST |

### Test Commands

| Command | Script |
|---|---|
| `npm test` | `vitest run` |
| `npm run test:watch` | `vitest` |
| `npm run test:coverage` | `vitest run --coverage` |

### Key Setup Details

- **`tests/setup.ts`**: calls `server.listen()` in `beforeAll`, `server.resetHandlers()` in `afterEach`, `server.close()` in `afterAll`
- **MSW handlers are granular**: each test can override the default handler via `server.use()` for edge cases
- **`tsconfig.json` includes `src/tests/`** via `"include": ["src"]` — no config changes needed
- **`noUnusedLocals` / `noUnusedParameters`**: Test files may need `// @ts-expect-error` or eslint-disable comments for test-specific patterns like unused `screen` destructuring

## 9. DESIGN.md Update Plan

The current Tailwind config section in `DESIGN.md` (L179-206) references `tailwind.config.js` which does not exist. The project uses **Tailwind v4** where custom tokens live in `@theme` directives inside `index.css`. This discrepancy must be corrected in `DESIGN.md` as a documentation fix (not a code change).

**New content for `DESIGN.md` L177-206**:

```markdown
## Theme Tokens (Tailwind v4)

The following custom tokens are defined in `frontend/src/index.css` via the `@theme` directive (Tailwind v4 syntax — no `tailwind.config.js`):

```css
@theme {
  --color-status-approved:    #22c55e;
  --color-status-flagged:     #eab308;
  --color-status-blocked:     #ef4444;
  --color-status-info:        #3b82f6;
  --color-focus-ring:         #ef4444;
  --color-page-bg:            #020617;
  --color-border-subtle:      #1e293b;
  --color-text-primary:       #f1f5f9;
  --color-text-secondary:     #cbd5e1;
  --color-text-muted:         #94a3b8;
  --color-text-disabled:      #64748b;
  --color-divider:            #334155;
  --color-primary-container:  #dc2626;
  --color-action-hover:       #b91c1c;
  --spacing-sidebar-width:    224px;
  --spacing-max-content:      1280px;
}
```

> ⚠ **Tailwind v3 → v4 delta**: Custom tokens are defined in CSS via `@theme`, not in JS config files. The `tailwindcss` PostCSS plugin is NOT used — the project uses `@tailwindcss/vite` instead. Spacing tokens become CSS variables (e.g., `spacing-sidebar-width` generates `var(--spacing-sidebar-width)`).
```

## 10. PR Implementation Order

### PR1 — Foundation (~220 LOC)

**Goal**: Extractable primitives, working route structure, base dependencies. After this PR, `npm test` runs (even with 0 specs), sidebar is consistent across all pages, and "Transacciones" navigates to a stub.

| # | File | Action | LOC | Key Detail |
|---|---|---|---|---|
| 1 | `DESIGN.md` | Modify | ~15 | Replace `tailwind.config.js` block with v4 `@theme` syntax |
| 2 | `frontend/index.html` | Modify | +6 | Add `<link>` for Inter (400,500,600,700), JetBrains Mono, Material Symbols Outlined CSS |
| 3 | `frontend/src/index.css` | Modify | +16 | Add `@theme` tokens for `status-*`, `spacing-sidebar-width`, `spacing-max-content`, `text-*`, `border-subtle`, `divider`, `focus-ring`, `primary-container`, `action-hover` |
| 4 | `frontend/package.json` | Modify | +10 | Add deps: `sonner`, `react-hook-form`, `zod`, `@hookform/resolvers`. Add devDeps: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`, `msw`, `@vitest/coverage-v8` |
| 5 | `frontend/vite.config.ts` | Modify | +8 | Add `test:` block to `defineConfig` |
| 6 | `frontend/src/tests/setup.ts` | Create | ~30 | Vitest setup, MSW lifecycle, jest-dom import |
| 7 | `frontend/src/tests/mocks/server.ts` | Create | ~10 | `setupServer(...handlers)` |
| 8 | `frontend/src/tests/mocks/handlers.ts` | Create | ~5 | Empty export `export const handlers = []` (placeholder) |
| 9 | `frontend/src/components/Sidebar.tsx` | Create | ~80 | Material Symbols, 3 nav items, brand, user section, logout, `activeItem` prop |
| 10 | `frontend/src/components/Toaster.tsx` | Create | ~20 | sonner `<Toaster>` wrapper with DESIGN.md theme |
| 11 | `frontend/src/main.tsx` | Modify | +2 | Import `Toaster`, render inside `QueryClientProvider` |
| 12 | `frontend/src/App.tsx` | Modify | +14 | Add routes for `/transactions` (stub text) and `/transactions/new` (stub text) — ensure `/transactions/new` BEFORE `/:id` |
| 13 | `frontend/src/pages/DashboardPage.tsx` | Modify | ~5 | Replace inline sidebar with `<Sidebar activeItem="dashboard" />`, remove ~70 lines of inline sidebar markup |
| 14 | `frontend/src/pages/AlertsPage.tsx` | Modify | ~5 | Replace inline sidebar with `<Sidebar activeItem="alerts" />`, remove ~60 lines of inline sidebar markup |

**Acceptance**: `npm test` runs (even if 0 specs), `npm run build` succeeds, sidebar matches DESIGN.md across all three pages, "Transacciones" nav works, "/transactions" shows stub.

### PR2 — Features (~690 LOC)

**Goal**: Full working transaction creation flow + list page + 3 test specs.

| # | File | Action | LOC | Key Detail |
|---|---|---|---|---|
| 1 | `frontend/src/lib/score.ts` | Create | ~30 | `classificationColor(cls)`, `formatScore(n)`, `isMLTrained(score)`, `classificationLabel(cls)` |
| 2 | `frontend/src/types/score.ts` | Create | ~15 | Re-export `ScoreResponse` from api/transactions, add `ScoreClassification` type union |
| 3 | `frontend/src/hooks/useCreateTransaction.ts` | Create | ~30 | `useMutation` wrapper, `onError` → toast, returns full mutation object |
| 4 | `frontend/src/pages/ScoreResultCard.tsx` | Create | ~120 | 5-state card: ensemble score gauge, 3 breakdown cards, classification badge, fired rules chips, ML-not-trained state |
| 5 | `frontend/src/pages/CreateTransactionPage.tsx` | Create | ~200 | react-hook-form + zod + useCreateTransaction + ScoreResultCard below form |
| 6 | `frontend/src/pages/TransactionsPage.tsx` | Create | ~180 | useQuery + filter bar + paginated table + "Nueva transacción" FAB/button |
| 7 | `frontend/src/tests/mocks/handlers.ts` | Modify | +80 | Full handlers: `POST /api/v1/transactions`, `GET /api/v1/transactions`, 4 fixture generators |
| 8 | `frontend/src/tests/CreateTransactionPage.test.tsx` | Create | ~60 | Smoke render + form fill + submit → ScoreResultCard visible |
| 9 | `frontend/src/tests/ScoreResultCard.test.tsx` | Create | ~80 | 4 test cases (loading → skeleton, legitimate → green badge, review → yellow + rules, fraud → red + no animation, ML-not-trained → icon + text) |
| 10 | `frontend/src/tests/TransactionsPage.test.tsx` | Create | ~50 | Smoke render + rows visible + filter interaction |

**Acceptance**: All 18 spec scenarios satisfied, 3+ test files passing, `npm test` green, `npm run lint` clean, `npx tsc --noEmit` passes, `npm run build` succeeds.

## 11. Architecture Decisions

### Decision: react-hook-form + zod over plain useState

| Option | Tradeoff | Decision |
|---|---|---|
| react-hook-form + zod | Validation logic in schema, reduced re-renders, ~3KB dep | **CHOSEN** |
| Plain useState | Zero deps, more boilerplate for validation | Rejected — form has 6 fields with non-trivial validation |

**Rationale**: The form has 6 fields with cross-cutting validation (amount > 0, currency = 3 chars, card_last4 = 4 digits). Writing validation logic by hand in useState would produce ~50 lines of error-prone code. react-hook-form with zod schema is 5 lines for the schema, 1 resolver import.

### Decision: sonner over manual toast state

| Option | Tradeoff | Decision |
|---|---|---|
| sonner | ~3KB, zero-config, production-tested, dismiss/action API | **CHOSEN** |
| Custom toast with useState + portal | Zero deps, full control, ~80 lines of code | Rejected — sonner handles edge cases (accessibility, stacking, animation) that we'd have to implement |

### Decision: MSW over mock-fetch/axios-mock-adapter

| Option | Tradeoff | Decision |
|---|---|---|
| MSW v2 (node) | Intercepts at network level, works with any HTTP client, test + dev story | **CHOSEN** |
| axios-mock-adapter | Only mocks axios, simpler setup, couples tests to axios | Rejected — MSW gives realistic network behavior and enables future use in Playwright/storybook |

### Decision: ScoreResultCard on create page (no redirect)

| Option | Tradeoff | Decision |
|---|---|---|
| Stay on `/transactions/new`, card below form | See result instantly, no context switch | **CHOSEN** (user decision) |
| Redirect to `/transactions/:id` | Full transaction detail, page-level layout | Rejected — analyst needs to create multiple transactions in sequence |

## 12. Risks & Open Questions

| Risk | Severity | Mitigation |
|---|---|---|
| `tsconfig.json` has `noUnusedLocals: true` — test patterns may trigger compile errors | Low | Test files use `screen.getByText(...)` which is consumed. Any false positives get `// @ts-expect-error` or eslint-disable |
| `jest-dom` matchers (`.toBeInTheDocument()`) may not auto-register in vitest environment | Low | Explicit `import '@testing-library/jest-dom/vitest'` in setup.ts (vitest-compatible import path) |
| Sidebar extraction from DashboardPage/AlertsPage may lose interactive behavior (active state, logout) | Med | Both pages wire `activeItem` statically. Logout button is part of Sidebar — must accept `onLogout` callback or use `useAuthStore` + `useNavigate` internally. **Decision**: Sidebar uses `useAuthStore` and `useNavigate` internally to avoid prop drilling the logout handler |
| `npm test` may need `--run` vs `--watch` in CI | Low | `npm test` → `vitest run` (single run). `npm run test:watch` → `vitest` (watch mode). Both added to package.json scripts |

## 13. Out of Scope (Reminder)

- Full DESIGN.md retrofit of existing pages (DashboardPage metric cards, AlertsPage, LoginPage, TransactionDetail)
- ML model training, dataset selection, model metrics
- Backend service changes (API contract is final)
- Oracle Cloud deploy
- Multi-user impersonation / role-based `user_id` override
- i18n (UI text stays in Spanish — matches existing app)
- Dark/light toggle (product is dark-only)
- Bulk transaction import (CSV)
- Real-time alerts via WebSocket
- Rule configuration UI (admin)
- Paginated sidebar user menu / settings
