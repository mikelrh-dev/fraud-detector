# Frontend Design System — Design Spec

**Date:** 2026-09-27
**Status:** approved (architecture + ordering)
**Origin:** audit of `frontend/src` against the Vercel Web Interface Guidelines

## Why this exists

The audit found 15 repetitions of `outline-none` + `focus:` instead of
`focus-visible:`. That is not 15 bugs, it is one missing abstraction. The same
shape repeats elsewhere: the `btn-motion` class appears 20 times, the input
class string 8 times, and there are three separate badge components
(`Badge`, `ClassificationBadge`, `AlertStatusBadge`) for one concept.

`lib/ui.ts` already proves the fix works. Its own comment says numeric
alignment "used to be re-typed per page and drifted". The convention exists and
stops at class strings. This spec extends it to components.

## Goal

Stop defect classes from recurring, and cut the bundle. **This does not change
how the app looks.** Visual design is a separate pass that runs afterwards and is
made cheaper by this work, not replaced by it.

The primitives must carry spacing and density decisions, not only accessibility
ones, so the later visual pass composes good pieces instead of rewriting
Tailwind by hand.

## Out of scope

- Visual redesign. No change to layout, hierarchy, density or colour. That is
  the next pass.
- Any backend change.
- A27 (httpOnly cookies + CSRF), A10/A11 (ensemble recalibration), C6/C7.
- Replacing Tailwind, `recharts`, `sonner` or the motion system. The motion
  system is the strongest part of this repo and stays.

## Architecture

One source, two layers.

```
lib/ui.ts          class constants (existing, grows)
components/        primitives that consume them (new)
pages/             consume primitives, not raw Tailwind
```

`lib/ui.ts` stays the single source for class fragments. Primitives read from
it. Pages stop restating class strings.

### Primitives

| Primitive | Absorbs | Notes |
|---|---|---|
| `Button` | 20 uses of `btn-motion` | new |
| `Input` + `Field` | 8 duplicated input class strings | new |
| `Badge` | `Badge`, `ClassificationBadge`, `AlertStatusBadge` | merge 3 into 1 |
| `Modal` | `ConfirmDialog` | promote, unchanged behaviour |
| `State` | `EmptyState`, `ErrorState` | merge 2 into 1, variant prop |

#### Button

```tsx
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

<Button variant="primary" size="sm" loading={false} onClick={fn}>Label</Button>
```

Encodes, so no call site can forget:

- `type="button"` by default. Submitting must be explicit `type="submit"`.
- `focus-visible:ring-2 focus-visible:ring-focus-ring` — never `focus:`, never
  `outline-none` alone.
- `touch-action: manipulation`.
- `active:scale-[0.98]` under the existing `btn-motion` class.
- `aria-busy` and a non-changing label while `loading`, so the button width does
  not shift.

#### Input and Field

```tsx
<Field
  label="Monto"
  htmlFor="amount"
  error={errors.amount?.message}
  hint="En dólares"
>
  <Input id="amount" name="amount" type="number" inputMode="decimal" autoComplete="off" />
</Field>
```

`Input` is thin: it spreads props and applies the class constant. `Field`
encodes the label/control association, `aria-invalid`, `aria-describedby`
pointing at whichever of hint or error is present, the error rendered adjacent to
the control with `role="alert"`, and the `sr-only` label variant.

#### Badge

```tsx
<Badge tone="clean">Legítimo</Badge>
```

Tones come from the semantic vocabulary already in `lib/classification.ts`. The
domain-value-to-tone mapping stays there, so classification colour cannot drift
again — which is what V-01 was.

#### Modal

`ConfirmDialog` promoted to `Modal`, keeping its focus trap, Escape handling and
focus restoration. Adds `overscroll-behavior: contain` so scrolling inside does
not chain to the page behind.

#### State

`EmptyState` and `ErrorState` merged into one `State` with
`variant="empty" | "error"`. Same visual language, one component.

## Route splitting

All seven routes in `App.tsx` become `lazy()`. `recharts` is imported by exactly
three components — `ChartTooltip`, `ScoreHistogram` and `ScoreTrendChart` — so
the charting library loads with the routes that use it and not with the login
page.

The `Suspense` fallback is a skeleton, and that is honest here: a route really
is loading. This is the distinction the `ScoreResultCard` fix turned on — there,
a skeleton rendered because `!result`, which was true before any submit and so
claimed work in progress that did not exist. A route-level fallback has no such
ambiguity.

## Order

Each step ships and verifies independently.

| # | Step | Verifies with |
|---|---|---|
| 1 | `lib/ui.ts` grows the class constants | `tsc`, `eslint`, existing suite |
| 2 | `Button`, `Input`, `Field` primitives | new unit tests per primitive |
| 3 | **`CreateTransactionPage` migrated** — the proving case | its 6 existing tests + new a11y assertions |
| 4 | Three badges merged | `src/lib/score.test.ts`, `src/lib/gauge.test.ts` keep passing |
| 5 | `Modal` from `ConfirmDialog` | `confirm-dialog.a11y.test.tsx` unchanged |
| 6 | Routes lazy | build output shows split chunks, `recharts` absent from the entry chunk |
| 7 | Mechanical guideline fixes | audit re-run reports clean for the touched rules |

Step 3 comes early and deliberately. It concentrates the two worst findings — the
submit button disabled before the request starts, and five duplicated inputs. If
the primitives do not simplify the most complex form, they will not simplify the
others, and it is better to find that out on one page than six.

## Step 7, itemised

- `…` instead of `...` in the five user-visible strings.
- `lib/datetime.ts` with a single `Intl.DateTimeFormat` formatter, replacing five
  scattered `toLocaleDateString` calls. This is the same defect V-04 was for
  money, applied to dates.
- `touch-action: manipulation` and an intentional `-webkit-tap-highlight-color`
  set globally in `index.css`.
- `color-scheme: dark` so Windows dark mode does not render light scrollbars and
  native controls.
- `text-wrap: balance` on page and section headings.
- `autoComplete` on the filter inputs, so password managers do not trigger on
  them.
- `transition-all` replaced with explicit properties in `RiskMeter`.
- `<main>` landmark added to `TransactionsPage`, which is the only page missing
  one.
- Skip link to main content.
- **Filters and pagination into the URL.** The riskiest item in this step and
  the only one that changes behaviour rather than markup: it makes a filtered
  view deep-linkable and shareable and makes the back button work. Split it into
  its own commit so it can be reverted independently if it misbehaves.

## Testing

Each primitive gets tests for the contract it encodes, not for its styling:
`Button` defaults to `type="button"` and exposes `aria-busy`; `Field` wires
`aria-describedby` to the error when there is one and to the hint when there is
not; `Badge` maps tones to the semantic classes; `Modal` keeps the focus trap.

The existing suite is the regression net for the migrations: 256 tests, of which
`desktop-regression.test.tsx` pins the mobile-retrofit classes (`hidden md:flex`,
`hidden md:block`, `sm:flex-row`, `sm:grid-cols-3`) and must keep passing
unchanged. A migration step that needs a regression test edited is a step that
changed behaviour it should not have.

## Risks

- **A wrong primitive gets amplified.** Six pages consuming a badly designed
  `Button` is worse than six local implementations. Mitigated by doing step 3
  before steps 4 and 5.
- **This work is hard to show.** It changes no pixels. If a visual result is
  needed for a demo, that is the next pass, and this pass makes it cheaper
  rather than replacing it.
- **Refactor breadth.** Eight pages are touched. Each step is committed
  separately so a bad step is one revert.
