# Proposal: mobile-optimization

## Intent

The fraud-detection analyst dashboard is desktop-only. 11 of 13 components have zero responsive prefixes; the fixed 224px sidebar consumes 60% of a 375px viewport, transaction tables overflow horizontally, and touch targets are below 40px. Analysts cannot triage alerts or review flagged transactions from a phone. This change retrofit responsive behavior into every flow while preserving pixel-identical desktop at md+.

## Scope

### In Scope

- Sidebar → hamburger slide-over drawer below md (768px); desktop unchanged
- TransactionsPage table → card-style list layout below md
- AlertsPage → card-style list layout; action buttons ≥40px on mobile
- ShapAttributionCard → stack row children vertically below sm; labels truncate
- ScoreResultCard loading skeleton → responsive grid (grid-cols-1 sm:grid-cols-3)
- TransactionDetail header row → wrap on narrow viewports
- TransactionsPage table overflow-x wrapper (immediate unlock)
- Toast position → top-center on mobile (optional, low priority)
- DESIGN.md "Mobile" section documenting breakpoints, drawer, touch-target rule
- Vitest tests: class-presence assertions for mobile + regression assertions for md+ classes
- All existing tests stay green; `npm run build` passes

### Out of Scope

- PWA / service worker / offline support
- Native mobile apps
- Full WCAG accessibility sweep
- Backend changes
- Desktop redesign or visual refresh
- Login/register forms (already responsive: max-w-sm centered)
- Recharts ResponsiveContainer (already responsive)

## Capabilities

### New Capabilities

- `mobile-responsive-layout`: Responsive retrofit across all dashboard components — sidebar drawer, card layouts, touch targets, skeleton grids, header wrapping

### Modified Capabilities

- `fraud-dashboard`: Existing "Responsive Layout" requirement (lines 130–145) expands from desktop+tablet to include mobile (375px+); scenarios for hamburger drawer, card-style lists, and touch targets added

## Approach

**Phased retrofit, additive-only:**

1. **P1 — Sidebar drawer + table overflow unlock.** Make Sidebar self-contained: mobile-only hamburger button, backdrop, and slide-over drawer rendered inside Sidebar.tsx. Pages keep rendering `<Sidebar/>` unchanged. Add overflow-x-auto wrapper to TransactionsPage table.
2. **P2 — Card layouts + SHAP stacking + touch targets.** Replace table rows with card-style lists below md for Transactions and Alerts. Stack ShapAttributionCard children vertically below sm with truncated labels. Enforce min-h-[40px] on AlertsPage action buttons below md.
3. **P3 — Polish + DESIGN.md + tests.** Responsive skeleton grids, header wrapping, toast position. Add "Mobile" section to DESIGN.md. Write vitest assertions for mobile class presence and md+ regression. Verify `npm test` and `npm run build` green.

**Hard constraint:** all changes are responsive-scoped (`md:` / `sm:` guards); desktop at md+ remains pixel-identical.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `frontend/src/components/Sidebar.tsx` | Modified | Self-contained mobile drawer (burger + backdrop + slide-over) |
| `frontend/src/pages/TransactionsPage.tsx` | Modified | Card-style list below md; overflow-x wrapper |
| `frontend/src/pages/AlertsPage.tsx` | Modified | Card-style list below md; touch-target fix |
| `frontend/src/components/ShapAttributionCard.tsx` | Modified | Vertical stacking below sm |
| `frontend/src/components/ScoreResultCard.tsx` | Modified | Responsive skeleton grid |
| `frontend/src/pages/TransactionDetail.tsx` | Modified | Header row wrapping |
| `DESIGN.md` | Modified | New "Mobile" section |
| `openspec/specs/fraud-dashboard/spec.md` | Modified | Delta: expanded Responsive Layout requirement |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Desktop regression from responsive changes | Med | Regression tests assert md+ classes still present; visual review at 1024px+ |
| Drawer z-index conflicts with existing modals | Low | Audit z-index stack before implementation; use highest existing +1 |
| Card layout misses data visible in table | Low | Card must show all 7 original columns; design phase validates |
| Size exceeds 400-line PR budget | High | Approved as single unit with size:exception; commits directly to master |

## Rollback Plan

Single commit to master. Revert via `git revert <commit-sha>`. No schema migrations, no backend changes, no feature flags — clean revert restores desktop-only state.

## Dependencies

- Tailwind 4 `@tailwindcss/vite` already installed (confirmed)
- No new dependencies required

## Success Criteria

- [ ] Every flow (login, dashboard, transactions list, create transaction, alerts, transaction detail w/ SHAP) usable at 375px viewport
- [ ] Zero desktop regression: all existing tests pass; `npm run build` succeeds
- [ ] Vitest suite includes mobile class-presence assertions and md+ regression assertions
- [ ] Sidebar drawer opens/closes below md; fixed sidebar renders at md+
- [ ] Transaction and alerts render as card lists below md; as tables at md+
- [ ] AlertsPage action buttons ≥40px height on mobile
- [ ] ShapAttributionCard stacks vertically below sm with truncated labels
- [ ] DESIGN.md documents mobile breakpoints, drawer pattern, and touch-target rule
