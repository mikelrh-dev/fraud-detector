# Design: Mobile Optimization

## Technical Approach

Additive-only responsive retrofit using Tailwind `md:` (768px) as the mobile/desktop switch and `sm:` (640px) for intra-mobile steps. Every page currently renders `<Sidebar />` inside a flex container — the sidebar becomes self-contained with its own drawer state. Tables get dual-mode rendering (card list below md, table at md+). Desktop at md+ remains pixel-identical.

## Architecture Decisions

### Decision: Sidebar Drawer Location

**Choice**: Self-contained inside `Sidebar.tsx` — burger button, drawer panel, and backdrop all rendered by the Sidebar component. Pages render `<Sidebar />` unchanged.

**Alternatives considered**: Layout wrapper in `App.tsx` managing drawer state; page-level wrappers.

**Rationale**: Every page already renders `<Sidebar activeItem="..." />` independently (DashboardPage, TransactionsPage, AlertsPage). A self-contained Sidebar means zero page-level changes for the drawer mechanism. `App.tsx` has no layout wrapper — each page owns its flex container.

### Decision: Burger Button Placement

**Choice**: Fixed position `md:hidden fixed top-4 left-4 z-50` inside Sidebar.tsx. Not integrated into a top bar.

**Alternatives considered**: Adding a global top bar component; integrating into each page header.

**Rationale**: Fixed burger avoids coupling to any page header. Single button, single location, consistent across all pages. The existing pages have no shared header — each has its own heading pattern.

### Decision: Touch Target Scoping

**Choice**: Use `max-md:` variant to scope enlarged touch targets below md only. `max-md:min-h-[40px] max-md:px-3 max-md:text-xs`.

**Alternatives considered**: Apply `min-h-[40px]` at all sizes (slightly enlarges desktop buttons).

**Rationale**: Honors the pixel-identical desktop constraint. Tailwind v4 supports `max-md:` natively. Desktop buttons remain at their original `text-[11px] px-2 py-1` size.

### Decision: Toast Position

**Choice**: CUT from scope. Sonner `<Toaster position>` is a JS prop — changing it requires either matchMedia at module load or conditional rendering. Not worth the complexity for this change.

**Alternatives considered**: matchMedia once at module load to set position dynamically.

**Rationale**: Low priority, adds JS complexity, not required for mobile usability (toasts appear at top-right which is fine on mobile). Keeps the R-list clean.

## Data Flow

```
Sidebar.tsx (mobile state)
├── useState(open) — controls drawer
├── useEffect — Escape listener when open
├── useEffect — body scroll lock when open
├── Burger button: md:hidden, onClick → setOpen(true)
├── Backdrop: fixed inset-0, onClick → setOpen(false)
└── Drawer panel: fixed inset-y-0 left-0, slide-in transform

Page components (unchanged render signature)
├── <Sidebar activeItem="..." />
├── Mobile card block: md:hidden
├── Desktop table: hidden md:block
└── overflow-x-auto wrappers where needed
```

## Sidebar Drawer Architecture

### Render Structure

```
<aside>                          ← Desktop: hidden md:flex; w-sidebar-width
  [brand, nav, user section]     ← unchanged content
</aside>

{mobile-only below md:}
  <button md:hidden>             ← Burger: fixed top-4 left-4 z-50
    ☰ menu icon
  </button>

  {open && <>
    <div fixed inset-0 bg-black/60 z-[55] />   ← Backdrop
    <aside fixed inset-y-0 left-0 z-[60]>       ← Drawer panel
      [brand, nav, user section — same content]
    </aside>
  </>}
```

### Z-Index Stack

| Layer | z-index | Element |
|-------|---------|---------|
| Burger button | z-50 | `md:hidden fixed top-4 left-4 z-50` |
| Existing modal (AlertsPage) | z-50 | `fixed inset-0 ... z-50` |
| Backdrop | z-[55] | `fixed inset-0 bg-black/60 z-[55]` |
| Drawer panel | z-[60] | `fixed inset-y-0 left-0 z-[60]` |

**Note**: AlertsPage action confirmation modal uses `z-50`. The drawer at `z-[60]` sits above it. If a drawer is open and user triggers an alert action, the modal renders behind the drawer — acceptable since the drawer covers the full viewport on mobile. No conflict.

### Accessibility

- Burger button: `aria-expanded={open}`, `aria-label="Abrir menú de navegación"`
- Drawer panel: `role="dialog"`, `aria-modal="true"`, `aria-label="Menú de navegación"`
- Escape key closes drawer (useEffect listener)
- Backdrop click closes drawer
- Focus trap is noted as a follow-up item (not in scope — simple close-on-escape is sufficient for this change)

### Body Scroll Lock

When drawer opens: `document.body.style.overflow = 'hidden'`
When drawer closes: `document.body.style.overflow = ''`
Cleanup in useEffect return function.

## Card-List Patterns

### TransactionsPage

Mobile card block (`md:hidden`, rendered before the table div):

```
<div className="md:hidden space-y-3">
  {data.items.map(tx => (
    <div data-testid={`tx-card-${tx.id}`}
         className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      {/* Header row: merchant + amount */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-slate-200 truncate">{tx.merchant_name}</span>
        <span className="text-sm font-bold text-slate-100">${tx.amount.toFixed(2)}</span>
      </div>
      {/* Footer row: date + badge + score */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">{formatted_date}</span>
        <div className="flex items-center gap-2">
          <ClassificationBadge ... />
          <span className="text-xs text-slate-300">{tx.risk_score?.toFixed(1) ?? '—'}</span>
        </div>
      </div>
    </div>
  ))}
</div>
```

Desktop table: wrap existing `<div className="bg-slate-900 ...">` with `className="hidden md:block"`.

Table overflow: wrap the table container in `<div className="overflow-x-auto">` (already exists in AlertsPage, needs adding to TransactionsPage).

Pagination: stays below both blocks, unchanged.

### AlertsPage

Mobile card block (`md:hidden`, rendered before the table div):

```
<div className="md:hidden space-y-3">
  {data.items.map(alert => (
    <div data-testid={`alert-card-${alert.id}`}
         className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      {/* Status badge */}
      <div className="mb-2">
        <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium border ${STATUS_COLORS[alert.status]}`}>
          {STATUS_LABELS[alert.status]}
        </span>
      </div>
      {/* Description: tx link + classification */}
      <div className="flex items-center gap-2 mb-1">
        <button onClick={...} className="font-mono text-xs text-slate-400 underline">
          {alert.transaction_id.slice(0, 8)}...
        </button>
        <span className={`text-xs font-medium ${CLASSIFICATION_COLORS[alert.classification]}`}>
          {CLASSIFICATION_LABELS[alert.classification]}
        </span>
      </div>
      {/* Timestamp */}
      <p className="text-xs text-slate-500 mb-3">{formatted_timestamp}</p>
      {/* Action buttons row — min-h-[40px] via max-md */}
      <div className="flex gap-2">
        <ActionButton ... />   ← max-md:min-h-[40px] max-md:px-3
      </div>
    </div>
  ))}
</div>
```

Desktop table: wrap with `className="hidden md:block"`.

### ActionButton Touch Target

Current: `text-[11px] px-2 py-1 rounded border` (~24px height).

Change to: `max-md:min-h-[40px] max-md:px-3 max-md:text-xs text-[11px] px-2 py-1 rounded border`

The `max-md:` variants apply only below 768px. Desktop retains original sizing.

## SHAP Stacking

Current `<li>`: `flex items-center gap-3` with fixed-width children (`w-44`, `w-14`, `w-24`).

Change to:
```
<li className="flex flex-col sm:flex-row items-start sm:items-center gap-1 sm:gap-3">
  <span className="w-auto max-w-full truncate sm:w-44 shrink-0 text-sm text-slate-300"
        title={featureLabel(c.feature)}>
    {featureLabel(c.feature)}
  </span>
  <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden w-full sm:w-auto">
    <div ... style={{ width: `${width}%` }} />
  </div>
  <span className="w-auto sm:w-14 shrink-0 sm:text-right text-sm font-mono text-slate-300">
    {formatContribution(c.contribution)}
  </span>
  <span className="w-auto sm:w-24 shrink-0 sm:text-right text-xs ...">
    {direction label}
  </span>
</li>
```

Labels get `truncate` + `title` attr for full text on hover. Bar and value widths auto on mobile.

## Skeletons

ScoreResultCard `LoadingSkeleton` (line 95): change `grid grid-cols-3 gap-4` to `grid grid-cols-1 sm:grid-cols-3 gap-4`.

BreakdownCards grid (line 127) already uses `grid-cols-1 sm:grid-cols-3` — no change needed.

## TransactionDetail Header

Current header (line 195): `flex items-center gap-3` — tx.id span has no min-w-0 or truncation.

Change inner div to: `flex items-center gap-3 flex-wrap min-w-0`
Change tx.id span to: `text-xs font-mono text-slate-500 truncate min-w-0`

This allows the header to wrap on narrow viewports while truncating the tx ID.

## Overflow Guard Strategy

**Page roots**: Each page's outer `<div className="min-h-screen ... flex">` gets `overflow-x-hidden` added. This prevents any child from causing horizontal scroll at 375px.

**Retained tables**: TransactionsPage's table container wraps in `<div className="overflow-x-auto">` (AlertsPage already has this at line 153).

**jsdom limitation**: jsdom does not compute layout — `scrollWidth <= clientWidth` cannot be tested via class presence. The test approach asserts that `overflow-x-hidden` is present on page roots and `overflow-x-auto` is present on table wrappers. This is a class-presence test, not a layout test.

## Toast Position

**Decision**: CUT from scope. Sonner's `position` is a JS prop passed at `<Toaster>` mount time. Changing it requires either:
- `matchMedia` at module load to detect mobile → conditional prop
- Two `<Toaster>` instances with visibility toggling

Neither is trivial enough to justify for low-priority behavior. Toast at top-right is acceptable on mobile. Noted as potential follow-up.

## File Change Map

| File | Action | Est. LOC Delta | Description |
|------|--------|----------------|-------------|
| `frontend/src/components/Sidebar.tsx` | Modify | +85 | Add useState, burger button, drawer panel, backdrop, Escape listener, body scroll lock, aria attrs |
| `frontend/src/pages/TransactionsPage.tsx` | Modify | +40 | Add mobile card block (`md:hidden`), wrap table with `hidden md:block`, add `overflow-x-auto` wrapper, add `overflow-x-hidden` to root |
| `frontend/src/pages/AlertsPage.tsx` | Modify | +45 | Add mobile card block (`md:hidden`), wrap table with `hidden md:block`, add `overflow-x-hidden` to root |
| `frontend/src/components/ShapAttributionCard.tsx` | Modify | +12 | Change `<li>` to flex-col/flex-row, add truncate+title to label, adjust widths |
| `frontend/src/pages/ScoreResultCard.tsx` | Modify | +1 | LoadingSkeleton grid: `grid-cols-3` → `grid-cols-1 sm:grid-cols-3` |
| `frontend/src/pages/TransactionDetail.tsx` | Modify | +3 | Header flex-wrap, min-w-0 truncation on tx.id |
| `frontend/src/pages/DashboardPage.tsx` | Modify | +2 | Add `overflow-x-hidden` to root div |
| `frontend/src/pages/CreateTransactionPage.tsx` | Modify | +1 | Add `overflow-x-hidden` to root div (verify; may already be safe) |
| `DESIGN.md` | Modify | +40 | New "Mobile" section |
| `openspec/specs/fraud-dashboard/spec.md` | Modify | 0 | Delta already in change specs |
| `frontend/src/tests/helpers/mobile.tsx` | Create | +20 | Helper: `expectMobileClasses(el, ['md:hidden'])` |
| `frontend/src/tests/Sidebar.drawer.test.tsx` | Create | +80 | Open/close, Escape, backdrop, aria assertions |
| `frontend/src/tests/TransactionsPage.mobile.test.tsx` | Create | +60 | Card rendering below md, table hidden below md |
| `frontend/src/tests/AlertsPage.touch.test.tsx` | Create | +50 | Card rendering, touch target min-h assertions |
| `frontend/src/tests/ShapAttributionCard.test.tsx` | Modify | +15 | Add stacking class assertions |
| `frontend/src/tests/desktop-regression.test.tsx` | Create | +70 | Assert md+ classes survive across 5 components |

**Total**: 8 modified, 4 new test files + 1 helper. ~430 LOC delta.

## Test Architecture

### Helper: `frontend/src/tests/helpers/mobile.tsx`

```ts
export function expectMobileClasses(el: HTMLElement, classes: string[]) {
  for (const cls of classes) {
    expect(el.className).toContain(cls);
  }
}

export function expectHasClass(el: HTMLElement, className: string) {
  expect(el.className.split(/\s+/)).toContain(className);
}
```

### New Test Files

**Sidebar.drawer.test.tsx**: Render Sidebar, assert burger button present with `md:hidden`. Simulate click → assert drawer panel visible with `role="dialog"`, `aria-modal="true"`. Simulate Escape → assert drawer closed. Simulate backdrop click → assert drawer closed. Assert `aria-expanded` toggles.

**TransactionsPage.mobile.test.tsx**: Render TransactionsPage with mock data. Assert mobile card div has `md:hidden`. Assert card wrapper contains `data-testid="tx-card-{id}"`. Assert table wrapper has `hidden md:block`. Assert root div has `overflow-x-hidden`.

**AlertsPage.touch.test.tsx**: Render AlertsPage with mock data. Assert mobile card div has `md:hidden`. Assert action buttons have `max-md:min-h-[40px]` class. Assert table wrapper has `hidden md:block`.

**desktop-regression.test.tsx**: For each of Sidebar, TransactionsPage, AlertsPage, ShapAttributionCard, ScoreResultCard — assert that md+ classes (`hidden md:flex`, `hidden md:block`, `sm:grid-cols-3`, `sm:flex-row`) are present in the rendered output. This is the regression safety net.

### Existing Tests

All existing tests in `frontend/src/tests/` remain untouched and must pass.

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| z-index stacking vs Toaster (sonner z-9999) | Drawer z-[60] is well below sonner's z-9999. No conflict. AlertsPage modal at z-50 is below drawer — acceptable since drawer covers viewport on mobile. |
| Body scroll lock cleanup | useEffect cleanup function resets `document.body.style.overflow = ''`. StrictMode double-render is handled by cleanup. |
| Backdrop focus handling | No focus trap in this change. Escape closes drawer. Full a11y (focus trap, inert main content) noted as follow-up. Simple approach is acceptable for initial mobile support. |
| Tailwind v4 arbitrary values syntax | `z-[60]`, `min-h-[40px]`, `max-md:` are all valid in Tailwind v4. `max-md:` is a native variant (not arbitrary). Confirmed by Tailwind v4 docs. |
| Card layout missing table data | Transaction card shows merchant, amount, date, badge, score — 5 of 7 columns. Currency and classification are secondary on mobile; classification is shown via badge. Currency omitted (low information density on mobile). |
| ScoreResultCard file location | Component is at `frontend/src/pages/ScoreResultCard.tsx` (not `components/`). Import in TransactionDetail uses `./ScoreResultCard`. Tests import from `../pages/ScoreResultCard`. |

## DESIGN.md Mobile Section (Draft)

```markdown
## Mobile (375px+)

### Breakpoints
- `sm:` (640px) — intra-mobile steps (SHAP stacking, skeleton grids)
- `md:` (768px) — mobile/desktop switch point

### Sidebar Drawer (below md)
- Burger button: fixed top-left, z-50
- Drawer panel: fixed left, full height, z-60, w-[224px]
- Backdrop: fixed inset-0, bg-black/60, z-55
- Close: Escape key, backdrop tap
- Body scroll locked when open

### Touch Targets
- All tappable elements: min-height 40px below md
- Applied via `max-md:min-h-[40px]` to preserve desktop sizing

### Card-List Pattern
- Below md: data renders as stacked cards (rounded-xl, slate-900 bg)
- At md+: original table layout preserved
- Tables wrapped in overflow-x-auto where retained

### Overflow Guard
- Page roots: overflow-x-hidden
- Retained tables: overflow-x-auto
- No horizontal scroll at 375px
```
