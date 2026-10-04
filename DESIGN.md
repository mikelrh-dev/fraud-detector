# Fraud Detector — Design System

> Source of truth for visual design. Validated with Stitch (project `11464160867924444499`).
> All frontend code MUST follow this system. When in doubt, this file wins.

---

## Brand

Professional fintech dashboard for fraud detection analysts. Dark-first, data-dense, no decorative flourishes. The aesthetic is "analyst at 2am reviewing alerts" — calm, high contrast, no noise.

---

## Color Palette

### Surfaces
| Token | Hex | Tailwind |
|---|---|---|
| Page background | `#020617` | `slate-950` |
| Card background | `#0f172a` | `slate-900` |
| Subtle elevation | `#1e293b` | `slate-800` |
| Borders | `#1e293b` | `slate-800` |
| Subtle dividers | `#334155` | `slate-700` |

### Text
| Token | Hex | Tailwind |
|---|---|---|
| Primary | `#f1f5f9` | `slate-100` |
| Secondary | `#cbd5e1` | `slate-300` |
| Muted | `#94a3b8` | `slate-400` |
| Disabled | `#64748b` | `slate-500` |

### Semantic (Fraud States — critical, this IS the product)
| State | Hex | Tailwind |
|---|---|---|
| Legitimate / Approved | `#22c55e` | `green-500` |
| Review / Flagged | `#f59e0b` | `amber-500` |
| Fraud / Blocked | `#ef4444` | `red-500` |
| Info / Neutral | `#3b82f6` | `blue-500` |

### Accent (primary action — risk is the product)
| Token | Hex | Tailwind |
|---|---|---|
| Action base (`--color-accent`) | `#dc2626` | `red-600` / `bg-accent` |
| Action hover | `#b91c1c` | `red-700` / `hover:bg-action-hover` |
| Focus ring | `#ef4444` | `red-500`, 2px offset (offset not yet applied — see Buttons) |

**Accent contract (Phase 4):** `--color-accent` is the **brand action color**
for primary CTAs (Login/Register/CreateTransaction submits, "Nueva
Transacción", alert resolve). It is deliberately **independent from risk
semantics** — `risk-critical` stays reserved for fraud states even though both
live in the red family. Never use accent to color data or badges.

---

## Typography

- **Body / UI:** Geist Variable — self-hosted via `@fontsource-variable/geist` (imported in `src/main.tsx`, before `index.css`)
- **Monospace** (IDs, card numbers, UUIDs): JetBrains Mono — self-hosted via `@fontsource/jetbrains-mono`
- Declared as `--font-sans` / `--font-mono` inside the `@theme` block of `frontend/src/index.css`
- Google Fonts CDN links for Inter/JetBrains Mono were REMOVED in Phase 0; the Material Symbols Outlined CDN was REMOVED in Phase 4 — **`index.html` makes zero external requests** (fonts + icons are fully self-hosted/local)

### Scale
| Level | Size / Weight |
|---|---|
| Display | 32px / 700 (page-level score numbers) |
| H1 | 24px / 600 |
| H2 | 18px / 600 (section headers) |
| H3 | 16px / 600 (card titles) |
| Body | 14px / 400 |
| Small | 12px / 400 (labels, metadata) |
| Tiny | 10px / 500 (uppercase tags, truncated IDs) |

---

## Spacing

Base unit: **4px**. Common values: 4, 8, 12, 16, 24, 32, 48.

- Card padding: 24px
- Section vertical gap: 24px
- Field vertical gap: 16px
- Inline element gap: 8px

---

## Shape

| Element | Radius |
|---|---|
| Default | 8px |
| Large cards | 12px |
| Pills / badges | 9999px (full) |

---

## Layout

### App shell
- Fixed left sidebar: **224px wide**, `slate-900`, `slate-800` right border
- Main: flexible width, scrollable, 24px padding
- Max content width: 1280px (centered in main)

### Cards
- Background: `slate-900`
- Border: 1px solid `slate-800`
- Radius: 12px
- Padding: 24px
- Title: H3, `slate-100`
- Subtitle: Small, `slate-400`

### Auth split-screen (Login / Register — `<AuthSplitLayout>`)

Desktop (md+): root `min-h-dvh md:grid md:grid-cols-[1.15fr_1fr]`.

- **LEFT brand panel** (`hidden md:flex`, bg-slate-950): two radial glows via
  inline style (`rgba(239,68,68,0.07)` at ~20% 15%, `rgba(34,197,94,0.05)` at
  ~85% 90%) — **the single sanctioned inline-gradient location in JSX**
  (page-level gradients remain forbidden; see Don'ts). 64px `BrandShield` in
  a `rounded-2xl border-slate-800 bg-slate-900` box, display headline with
  "fraude" in `text-risk-critical`, and three feature rows (Scales /
  ShieldCheck / Sparkle) in `h-9 w-9` icon boxes.
- **RIGHT form panel**: centered `max-w-sm`; labels above inputs (`text-xs`
  slate-400); inputs per Forms spec (h-11, focus ring risk-critical/25);
  password fields carry an Eye/EyeSlash visibility toggle
  ("Mostrar/Ocultar contraseña"); primary submit
  `bg-accent hover:bg-action-hover`; ghost demo button under a divider row.
- **Register strength meter**: 3 segments (`h-1 rounded-full`), filled count
  1/2/3 for weak/medium/strong with tones risk-critical / warn / clean.
- **Mobile (<md)**: single column — compact brand header (`h-14`, 28px shield)
  above the form.
- Entrance: panels ride `.motion-stagger` with `--i` 0/1 (reduced-motion safe).

### Forms
- Label: Small, `slate-400`, 8px above input
- Input bg: `slate-950`
- Input border: 1px solid `slate-700`
- Input focus: `red-500` border
- Input padding: 10px vertical, 12px horizontal
- Input radius: 8px
- Error state: `red-500` border, helper text in `red-200`

---

## Components

### Buttons

All buttons compose from the shared constants in `src/lib/ui.ts` (`BTN_BASE` + one `BTN_VARIANTS` entry + one `BTN_SIZES` entry) via `cn()` — import them, don't copy class strings. Semantics of each slot:

| Slot | Token / value |
|---|---|
| Behaviour (all) | `BTN_BASE` — `btn-motion active:scale-[0.98]`, touch-action, `disabled:opacity-50`, `FOCUS_RING` |
| `primary` | `bg-accent text-white`, hover `bg-action-hover` |
| `secondary` | `bg-transparent text-slate-300 border border-slate-700`, hover `bg-slate-800` |
| `ghost` | `text-slate-400` (text only, no background), hover `text-slate-100` |
| `danger` | identical to `primary` — see the note below |
| Size `sm` | `px-3 py-1.5 text-xs rounded-lg` |
| Size `md` | `px-4 py-2 text-sm rounded-lg` (8px radius, 12×24px padding) |

- **Design intent — Danger: same as primary** (this product's primary action IS
  risky). `danger` is therefore *the same tokens as `primary`*: the distinction
  is semantic, carried by the button's label, not by colour.
  - It previously used `bg-risk-critical` with its own `risk-critical-hover`
    token. That token resolved to `#dc2626` — byte-identical to `--color-accent` —
    so **hovering a destructive button landed on the rest colour of a primary
    one**, a worse version of the problem it was meant to fix. A second red ramp
    to say "risky" was the wrong instrument; this design system had already
    answered the question. Both the variant's colour and the token are gone.
  - `bg-risk-critical` is also *lighter* than `bg-accent` (`#ef4444` vs `#dc2626`),
    so a destructive control read as weaker than the action beside it.
  - If the visual pass wants destructive controls to read as visually distinct
    from the primary action, that is a deliberate design change to make there —
    with a third tone, not by reusing an existing one.
- **Hovers are gated on `enabled:`** (`enabled:hover:bg-…`). `BTN_BASE` already
  dims disabled controls with `disabled:opacity-50`; a bare `hover:` still fired
  under the cursor and made an inert button look pressable.
- ⚠ **Known deviation, deferred to the visual pass:** the focus-ring constants
  carry **no ring offset**, where the Accent table above specifies 2px. The
  tokenization pass was scoped to no visual change, so the value was left alone;
  the offset belongs to the visual pass.

### Badges / Pills

All badges render through the **`Badge` primitive** (`src/components/Badge.tsx`) — never hand-roll pill styling:

- **Tone prop** (semantic, zero hardcoded hex): `clean` → `risk-clean`, `warn` → `risk-warn`, `critical` → `risk-critical`, `info` → `status-info`, `neutral` → slate utilities (`bg-slate-800 border-slate-700 text-slate-400`, unknown-state fallback — skips the tinted pattern on purpose)
- **Background:** semantic color at 10% opacity (`bg-risk-XXX/10`)
- **Border:** 1px solid semantic color at 30% opacity (`border-risk-XXX/30`)
- **Text:** full semantic color (`text-risk-XXX`)
- **Padding/radius:** `rounded-full`; sizes `md` (px-3 py-1 text-sm) and `sm` (px-2 py-0.5 text-[11px])
- **Icon slot:** optional Material Symbols glyph via the `icon` prop
- Consumers: `ClassificationBadge` (approved/flagged/blocked), `AlertStatusBadge` (open→warn, reviewed→info, resolved→clean, unknown→neutral)

### Charts

Chart colors come from **`src/lib/chart-theme.ts`** (`THEME`). Rule: **no literal hex inside chart components** — enforced by `chart-theme.test.ts` (guards `ScoreHistogram`, `ScoreTrendChart` and `ChartTooltip`). The hex values in `THEME` must mirror the `@theme` CSS tokens in `index.css` until Tailwind exposes theme vars to JS; both sides are guarded by tests.

Phase 4 additions:
- **`<ChartTooltip>`** (`src/components/ChartTooltip.tsx`) — shared tooltip surface for every recharts instance via the `content={<ChartTooltip />}` pattern. Rounded-xl slate-900/95 glass panel, mono uppercase label, right-aligned mono values, per-series legend dots. Optional `valueFormatter` (e.g. `(v) => v.toFixed(1)`).
- **Trend chart**: `AreaChart` with a vertical `linearGradient` (`id="trend-fill"`, risk-warn 0.18→0), strokeWidth 2.5, activeDot stroked with `THEME.pageBg`; horizontal-only dashed grid from `THEME.gridSoft` (slate-800); axis lines off.
  - **Dots are a data decision, not a style**: `MIN_CONSECUTIVE_DAYS_FOR_LINE` (`src/lib/trend.ts`) — when the window has no run of 2+ adjacent measured days the line cannot speak for itself, so points render (`{r: 4}`). With 2+ consecutive measured days they are omitted and the line carries the trend. Do not set `dot={false}` unconditionally; that is what produced a blank panel on sparse windows.
  - **`connectNulls={false}` is load-bearing**: a day without transactions is a gap, not a measurement. Interpolating across one draws scores that were never computed, and a failed query would render as a flat "risk 0" line. `honest-data.test.ts` guards this.
  - **Gaps are shaded, not hidden**: `GapBandLayer` paints `THEME.gridSoft` @ 0.55 over each unmeasured day run plus a caption "N de 7 días sin transacciones", so a sparse window reads as *measured* rather than *broken*. Built through recharts `Customized` against the chart's own scale — **`ReferenceArea` silently renders nothing here**, because a categorical XAxis resolves to a point scale with `bandwidth() === 0` (measured on recharts 2.15.4: a one-day `x1=x2` area emits an empty `<g>`, a two-day area spans one category step, numeric half-step bounds render nothing at all).
- **Histogram**: `radius={[6,6,0,0]}`, `maxBarSize={48}`, per-bucket Cell fills, Bar `background` track + slate-800/40 hover cursor.
- **Axis ticks**: compact formatter **`formatCompactTick(v)`** from `chart-theme.ts` — values ≥ 1000 render as `N.Nk`. Pure function, unit-tested.

### Tables

Unified chrome (shared constants in `src/lib/ui.ts` — import them, don't copy class strings):

- Header cells: `TABLE_HEADER_CELL` = `text-left px-4 py-3 text-[11px] font-medium uppercase tracking-wider text-slate-400`; numeric columns use `TABLE_HEADER_NUMERIC` (same, but `text-right`)
- Rows: alternating `slate-900` / `slate-950`
- Row hover: `bg-slate-800/40` (unified across dashboard, transactions and alerts tables)
- Cell padding: `px-4 py-3`
- Borders: 1px solid `slate-800` between rows

**Numeric-cell rule:** every AMOUNT cell and SCORE value renders right-aligned monospace with fixed-width digits — always via `NUMERIC_CELL` (`text-right font-mono tabular-nums`). Applies to desktop tables and mobile card values alike. Transaction IDs stay mono as before.

### Timestamps

Every timestamp renders through **`formatTimestamp`** (`src/lib/datetime.ts`) — one format, every call site, never an inline `toLocale*` call. Consumers: `TransactionsPage` (mobile card + table), `TransactionTable`, `AlertsPage` (card + table), `TransactionDetail` (created + updated).

- **Format: `DD/MM/AAAA, HH:MM`** — `Intl.DateTimeFormat("es-AR")` with `hourCycle: "h23"`, 2-digit day/month/hour/minute, 4-digit year, no seconds.
- **Locale is `es-AR`, unchanged and never inferred** — every call site already passed it, `formatMoney` already uses it, and the copy is Argentine Spanish. Switching it would rewrite every amount on screen.
- **`hourCycle: "h23"` is load-bearing.** Measured: es-AR resolves `{hour: "2-digit"}` to `h12`, so the alerts page was rendering `20/09/2026, 02:30 p. m.` — a 12-hour clock, a dotted meridiem and a U+00A0 before the `m.`, inside a data table. `hour12: false` is not a substitute; its h23-vs-h24 mapping has moved between ICU versions. `datetime.test.ts` pins the digits.
- **ONE format, date-only deliberately not offered.** `formatMoney`'s note already ruled on the identical question — hiding the cents from an amount under review is a data-fidelity defect, not a cosmetic one. Dropping the hour from a fraud timestamp is the same defect: on a list of charges, two transactions on a day become indistinguishable and an alert triage pass cannot separate a 03:00 burst from a 15:00 one. The three date-only call sites gained the time they were dropping.
- **Local zone, as before.** The backend sends ISO-8601 with an offset, so the instant is preserved; a viewer elsewhere sees their own wall clock.
- **Unparseable input → `—`**, not `"Invalid Date"` — same as `formatMoney`.
- **Tests pin literals, never the formatter's own output.** Rebuilding the expected string from the same `Intl` options would move both sides of the assertion. The `Date`s are built from local components so the literals hold in any timezone.

### RiskMeter

All score bars render through **`<RiskMeter value={n} />`** (`src/components/RiskMeter.tsx`) — never hand-roll an inline-styled bar:

- Track: `h-1.5 rounded-full bg-slate-800`; optional `widthClass` (default `w-16`)
- Fill: width clamped to 0–100%, tone from the shared banding in `src/lib/risk.ts`: `risk-clean <45`, `risk-warn 45–59`, `risk-critical ≥60`
- Two threshold ticks at 45% / 60% (`border-slate-600/50`, absolute-positioned)
- Zero inline hex; meter semantics via `role="meter"` + aria valuenow
- Source-of-truth note: backend classification is dynamic (amount-based thresholds), so these bands are the agreed UI display convention

### Score Gauge (ensemble risk score, 0-100)

Signature 270° dial rendered by `<ScoreGauge>` inside `ScoreResultCard`:

- **Arc math is a pure module**: `src/lib/gauge.ts` exports `GAUGE_SWEEP_DEG`
  (270), `GAUGE_START_ANGLE_DEG` (135, bottom-left), `totalArcLength(r)`,
  `scoreToDashOffset(score, arcLength)` (clamps 0–100, monotonic decreasing)
  and `thresholdToPosition(t)` / `polarToPoint(...)` for tick placement. The
  gap always sits at the bottom: the arc covers [135°, 360°] ∪ [0°, 45°].
- Track: full 270° arc in `slate-800`; progress arc takes the score's tone
  via `riskTone()` (`stroke-risk-clean/warn/critical`) — same banding as
  RiskMeter. Zero inline hex.
- Threshold ticks at 45 / 60 (`RISK_THRESHOLDS`, the shared display
  convention) rendered as small radial segments crossing the arc band.
- Center readout: score in `font-mono tabular-nums text-3xl` + muted "/100"
  + `<ClassificationBadge>` below.
- Animation: `stroke-dashoffset` transition, 600ms
  `cubic-bezier(0.16,1,0.3,1)`; disabled under `prefers-reduced-motion`.
  Exposes `role="meter"` semantics like RiskMeter.

---

## Iconography

- **Phosphor Icons** (`@phosphor-icons/react`) — **the single icon system as of Phase 4.** Material Symbols Outlined was fully removed (source + CDN link). **Standard weight: `weight="regular"`** — Phosphor draws on a 256-grid with stroke 16, which is exactly **1.5px at 24px** render size; that is the house strokeWidth. Sizes: 16px nav/inline glyphs, 18px metric-card and feature-row icons.
- Migration map applied in Phase 4 (Material Symbols → Phosphor): `dashboard→SquaresFour`, `payments→Receipt`, `notifications_active→BellRinging`, `add→Plus`, `logout→SignOut`, `menu→List`, `check_circle→CheckCircle (weight="fill")`, `info→Info`, `gavel→Scales`, `psychology→Brain`, `neurology→Circuitry`.
- Badge icon slots take a **Phosphor component node** (`icon?: ReactNode`) rendered inside an aria-hidden wrapper — never glyph-name strings.
- Brand mark = `<BrandShield>` (`src/components/BrandShield.tsx`): shield+check outline inheriting `currentColor`. Used in the sidebar brand, auth split-screen panel (64px) and mobile auth header (28px).
- No emojis in production UI.

## Tab identity

- **Favicon:** `frontend/public/favicon.svg` (**independent simplified mark**; `<BrandShield>` is its own component-level drawing, not a geometry mirror of this file) — outer shield stroke `#e2e8f0` (slate-200) on transparent, inner check filled `#ef4444` at 0.9 opacity, < 1KB. Wired via `<link rel="icon" type="image/svg+xml">`.
- `<meta name="theme-color">` = `#020617` (page background). Title: "Fraud Detector — Consola de análisis".
- **Sanctioned hex locations (complete list):** `frontend/src/index.css` `@theme`, `src/lib/chart-theme.ts`, `frontend/index.html` meta/favicon, `frontend/public/favicon.svg`. Anywhere else is a violation; repeated colors become tokens.

---

## Motion

CSS-first motion system (Phase 3). One easing, three durations, transform +
opacity ONLY. No animation libraries (framer-motion/gsap) and no scroll
listeners — ever.

### Tokens (`@theme` in `frontend/src/index.css`)

| Token | Value | Used for |
|---|---|---|
| `--ease-out-expo-like` | `cubic-bezier(0.16,1,0.3,1)` | everything (single house easing; generates the `ease-out-expo-like` Tailwind utility) |
| `--motion-duration-fast` | 150ms | hover / press micro-feedback |
| `--motion-duration-base` | 300ms | entrances, route transitions, stagger steps |
| `--motion-duration-slow` | 600ms | data-driven reveals (gauge arc, SHAP bars) |

### Keyframes & utilities

- **`.animate-fade-slide-up`** — shared one-shot entrance: opacity 0→1 +
  translateY(8px)→0 over 300ms. Drives route transitions; also backs the
  legacy `.animate-report-in` class (same keyframes, kept name).
- **`.motion-stagger > *`** — staggered reveal: direct children replay the
  same entrance with `animation-delay: calc(var(--i) * 60ms)`.
- **`.btn-motion`** (`@utility`) — press feedback for interactive controls:
  transitions color/background/border + transform over fast duration. Pair
  with `active:scale-[0.98]` at each call site.

### Stagger contract — `<MotionList>` (`src/components/MotionList.tsx`)

Component-driven pattern (chosen over a bare utility so the cap is enforced):
renders children inside a `.motion-stagger` container and stamps each element
child with an inline `--i` clamped by `clampStaggerIndex` to
`MOTION_STAGGER_MAX_INDEX = 8` → max accumulated delay ≈ **480ms**, regardless
of list length. Non-element children pass through untouched. Apply to mobile
card lists, KPI grids, chart rows and chip groups — never to desktop tables.

### Route transition — `<PageTransition>` (`src/components/PageTransition.tsx`)

Wraps authenticated page content in a div keyed by `location.pathname`.
Navigation swaps the key → remount → the fade-slide-up entrance replays once.
In-page updates (filters, pagination, data refetches) never re-trigger it.
Integrated in every Sidebar page's content area plus the standalone
TransactionDetail. Login/Register are excluded (unauthenticated); since
Phase 4 they run their own entrance through `<AuthSplitLayout>`'s staggered
panels.

### Micro-interactions

- **Buttons/pills/CTAs:** `btn-motion active:scale-[0.98]` — pressed controls
  scale down 2% instantly-tweened; colors keep their legacy hover transitions.
- **MetricCards:** hover lifts `-translate-y-[1px]` + border-color deepens to
  `slate-700`. Deliberately NO box-shadow animation (see non-goals).
- **Sidebar active item:** a 2px accent bar (`.nav-indicator`) scales in from
  origin-left via `[aria-current="page"]` on the parent button — pure CSS,
  zero JS measuring, transform + opacity only.
- **Table rows:** color hover ONLY (`bg-slate-800/40`). Restraint is the rule;
  no transforms on rows.

### Reduced-motion guarantee

One global guard in `index.css` kills every CSS-driven animation under
`prefers-reduced-motion`: shimmer sweep (also `display:none`), report
entrance, route transition and staggered reveals get `animation: none`; the
nav indicator gets `transition-duration: 0.01ms`. JS-driven paths carry their
own opt-outs at the call site: gauge arc (`motion-reduce:transition-none`),
count-up hook (jumps straight to target), SHAP bars (final width immediately).
Button press-scale snaps without tweening — a discrete state change, not
animation.

### Explicit non-goals

- **No desktop-table stagger** — data-dense views re-render on every
  pagination/sort/filter tick; re-animating rows there is churn, not polish.
- **No shadow animation** — animating box-shadow repaints every frame; cards
  shift borders instead (colors are cheap).
- **No layout-property animations** — only `transform` and `opacity` (plus
  legacy color hovers). No top/left/height, no scroll listeners. Two sanctioned
  exceptions, both reduced-motion-guarded and documented in Legacy motion
  below: the gauge arc animates `stroke-dashoffset` (SVG-native, zero layout
  cost) and SHAP bars animate `width` inside fixed-height rows.
- **No bounce/playful easing** — calm analyst tool, one expo-out curve.

### Legacy motion (unchanged)

- Hover transitions: 150ms ease-out
- Loading: subtle pulse (`slate-700` ↔ `slate-800`) on skeleton placeholders;
  shimmer sweep (`.animate-shimmer`) for composed chart-area skeletons
- Score gauge arc: 600ms `cubic-bezier(0.16,1,0.3,1)` on `stroke-dashoffset`
  (mount + value changes); SHAP bars grow from 0 with the same timing —
  both disabled under `prefers-reduced-motion`
- Metric count-up: `useCountUp(target, { duration: 800 })` hook (`src/hooks/useCountUp.ts`) — requestAnimationFrame-driven, easeOutCubic, animates the real fetched value only (no invented deltas). **Gating contract**: callers must pass a real number — mount the animated child only when `value !== null` (see `AnimatedMetricValue` in DashboardPage), so no rAF churn runs toward a fabricated 0 while loading. **Respects `prefers-reduced-motion`**: jumps straight to the target.

---

## Don'ts

- No bright white backgrounds (eye strain during long analyst shifts)
- No drop shadows for elevation (use borders + subtle bg shifts)
- No gradient backgrounds on the page level — exceptions: the gauge arc fill and the auth brand-panel radial glows (see Auth split-screen)
- No more than 2 accent colors on any one screen
- No rounded / display fonts (geometric sans only)
- No emojis in production UI (dev-friendly, not product-friendly)

---

## Theme Tokens (Tailwind v4)

The following custom tokens are defined in `frontend/src/index.css` via the `@theme` directive (Tailwind v4 syntax — no `tailwind.config.js`):

```css
@theme {
  /* Semantic risk tones — single source for risk/status coloring */
  --color-risk-clean:         #22c55e;  /* = green-500 */
  --color-risk-warn:          #f59e0b;  /* = amber-500 (unifies legacy status-flagged/fraud-review drift) */
  --color-risk-critical:      #ef4444;  /* = red-500 */

  /* Legacy aliases, derived from risk-* (kept working for existing consumers) */
  --color-status-approved:    var(--color-risk-clean);
  --color-status-flagged:     var(--color-risk-warn);
  --color-status-blocked:     var(--color-risk-critical);
  --color-status-info:        #3b82f6;

  --color-focus-ring:         #ef4444;
  --color-page-bg:            #020617;
  --color-border-subtle:      #1e293b;
  --color-text-primary:       #f1f5f9;
  --color-text-secondary:     #cbd5e1;
  --color-text-muted:         #94a3b8;
  --color-text-disabled:      #64748b;
  --color-divider:            #334155;
  /* Brand action color — primary CTAs; independent from risk semantics */
  --color-accent:             #dc2626;
  --color-primary-container:  #dc2626;
  --color-action-hover:       #b91c1c;
  --spacing-sidebar-width:    224px;
  --spacing-max-content:      1280px;

  /* Self-hosted fonts (fontsource imports in main.tsx) */
  --font-sans: "Geist Variable", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;
}
```

> ⚠ **Tailwind v3 → v4 delta**: Custom tokens are defined in CSS via `@theme`, not in JS config files. The `tailwindcss` PostCSS plugin is NOT used — the project uses `@tailwindcss/vite` instead. Spacing tokens become CSS variables (e.g., `spacing-sidebar-width` generates `var(--spacing-sidebar-width)`). The default Tailwind palette (`slate-*`, etc.) is NOT re-declared — use the native utilities/vars.
>
> ⚠ **Badge bg pattern**: tone backgrounds use `/10` opacity and borders `/30` — e.g. `bg-risk-clean/10 border-risk-clean/30 text-risk-clean`.

---

## Landmarks & the skip link

- **One `<main>` per route, owned by the page.** The app shell does not provide
  one: `App.tsx` renders `<Routes>` directly and each page mounts its own
  `<Sidebar>`, so a landmark has to live in the page whose content it labels.
  Every `<main>` carries `id={MAIN_LANDMARK_ID}` and `tabIndex={-1}` —
  programmatically focusable (a skip target) without becoming a tab stop (it
  must not add a second stop between the shell and the first control). The id is
  a single exported constant in `src/lib/focusable.ts`, not a literal in five
  files: that module already exists to hold "one definition, two bugs gone", and
  a skip link pointing at an id nobody renders goes nowhere invisibly.
- **`<SkipLink>` (`src/components/SkipLink.tsx`) is the first focusable
  element in the document on every route** — rendered as the first child of the
  route `ErrorBoundary` in `App.tsx`, ABOVE `<Suspense>` so it survives a lazy
  chunk in flight. It lives there rather than in a layout route with an
  `<Outlet/>` because introducing a layout route changes the element tree,
  which is a different change than this one.
- **It reveals on bare `focus:`, not `focus-visible:`** — the single documented
  exception to `ui/no-raw-class-tokens`. A skip link is reached by Tab, by an
  assistive technology's "activate first link", and by `element.focus()` from
  anywhere in the app, and it must become visible in all of them. `sr-only`
  clips rather than removes, so a link that misses the focus-visible heuristic
  is left 1px wide and invisible while a keyboard user tabs onto it: the worst
  outcome for a link whose whole purpose is to be seen. The ring is
  `focus:`-prefixed for the same reason.
- **The geometry is hand-written CSS in `index.css` (`.skip-link` /
  `.skip-link:focus`), not utilities.** The obvious spelling —
  `sr-only` + `focus:not-sr-only` + `focus:absolute` — has three utilities all
  setting `position`, so which one applies is decided by Tailwind's internal
  stylesheet order and nothing else. It comes out right today (measured) and
  would break silently on an upgrade. One authored rule per state, sharing
  identical values for every property both declare. `fixed`, not `absolute`, in
  both states: a skip link is reached by Shift+Tab from anywhere in a long list.
- **The focus INDICATOR stays a Tailwind `focus:ring-2 focus:ring-focus-ring`**
  on the element, so the skip link wears the same ring, from the same token, as
  every other control. Spelling a ring out in hand-written CSS would put a
  second divergent copy of the focus treatment inside the rule whose job is to
  stop the design system growing one.
- **`href="#main"` AND an explicit `focus()` call, deliberately both.** The href
  is what makes it a link — fragment to copy, status-bar URL, middle-click, and
  a working link with JS disabled. The handler is what makes the focus move
  testable: jsdom implements fragment navigation (it updates the hash) but does
  not move focus, so without it the one assertion that matters could not be
  written. No `preventDefault()`, so a real engine runs both onto the same
  element.
- Pinned by `src/tests/SkipLink.test.tsx` with `user.tab()`, so the real tab
  order is walked rather than proxied for.

---

`src/lib/ui.ts` is the single source for the focus treatment, the button base and
the input chrome. Every class string that used to be re-typed button by button
was fixed by hand, across seven commits, and **nothing in the toolchain stopped
the eighth one**: copying was cheaper than importing, and — because a class
naming a nonexistent Tailwind v4 token emits no CSS and raises no error — a
mistyped `ring-focus-rng` would have shipped silently. The rule is that error.

Local plugin, `frontend/eslint-rules/ui-class-tokens.js`. It is a custom rule
rather than `no-restricted-syntax` (which matches nodes, not string contents)
or `no-restricted-imports` (which matches specifiers, and the forbidden thing
here is a *copy*, not a missing import).

| Check | Fires on | Use instead |
|---|---|---|
| `bareFocus` | a bare `focus:`-prefixed class whose utility **paints** | `FOCUS_RING` (which is `focus-visible:`-prefixed on purpose) |
| `rawFocusRing` | `focus-visible:outline-none` / `:ring-2` / `:ring-focus-ring` typed by hand | `FOCUS_RING` |
| `rawInputChrome` | `placeholder-slate-500` + `bg-slate-800` + `rounded-lg` in one class list | `<Input>` or `cn(INPUT_BASE, …)` |
| `rawBtnBase` | `btn-motion` + `active:scale-[0.98]` + `touch-manipulation` in one class list | `<Button>` or `cn(BTN_BASE, …)` |
| `rawHex` | a raw hex literal in a class list | an `@theme` token in `index.css` |

**One scope: class POSITIONS.** All five checks apply in exactly two places —
a `className` / `class` attribute value, and an argument of `cn(...)` (resolved
through its import from `src/lib/ui`, at any scope, because module scope is
where a shared helper gets written). Everywhere else the rule reads nothing.

An earlier version applied the two focus checks to *every* string literal in a
file, on the theory that a focus ring is a correctness contract wherever it is
written. Measured, that read prose (`"Invalid focus: the ring did not apply"`),
an `aria-label` that mentions focus, and a `data-x` attribute — `startsWith("focus:")`
cannot tell a class from a message. The tree was clean by luck, not by design.

**The declared limit.** A class string written into a constant and only ever
*referenced* is out of reach: the rule does not follow references, because a
lint rule that follows references is a type checker and the heuristics that
approximate one produce false positives. `AUTH_INPUT_RING` in
`AuthSplitLayout.tsx` is the case in point; it is pinned by tests in both
directions (`LoginPage.test.tsx`, `RegisterPage.test.tsx`) instead, which is
this codebase's mechanism for a divergence that is deliberately kept.

**`bareFocus` covers PAINTING utilities only.** The rationale is a focus
*indicator* firing on mouse click, so a bare `focus:` is banned on a property
namespace that changes how the element looks — `ring`, `outline`, `border`,
`shadow`, `bg`, `text`, `opacity`, the transform utilities, and so on. It is
allowed on everything else: `focus:z-10`, `focus:scroll-mt-24`,
`focus:absolute`, `focus:not-sr-only` are layout and scroll adjustments that
paint nothing and are correct on any state. The two rejected utilities the
hand-written skip link exists to avoid are in that second group on purpose —
that bug is an ordering trap between three rules that all set `position`, and
has nothing to do with the pseudo-class. The house ring itself does not depend
on the namespace list: `rawFocusRing` matches three exact tokens, no vocabulary
required.

**Why the last two are combinations and not single tokens.** `bg-slate-800`,
`rounded-lg` and `px-3` are used by cards, panels and buttons; `btn-motion` and
`active:scale-[0.98]` are a PAIR. Banning any one token alone would ban the
design system.

**The button-base discriminator, and its measured weakness.** Ten call sites
carry the motion pair, and they are **not ten of the same thing**:

- **Four are chips and pills** — `AlertsPage.tsx:226`, the `ActionButton` in
  `AlertsPage.tsx`, `TransactionTable.tsx:89`, `TransactionsPage.tsx:224`. They
  are not buttons and must not be made into them. The harm of forcing the base
  on a chip is smaller than it was first claimed to be: for a single short
  label `inline-flex items-center justify-center gap-1.5` changes nothing a
  reader can see, and only `font-medium` is a real visual delta — which
  `TransactionsPage.tsx:224` already carries.
- **Six are real buttons** re-typing most of `BTN_BASE` — `ConfirmDialog.tsx`
  `:201` and `:212`, `ErrorBoundary.tsx:119`, `TransactionDetail.tsx:178`,
  `TransactionsPage.tsx:490` and `:501`. They are the drift this check exists to
  catch, and they escape it, because each omits `touch-manipulation` — one token
  out of fourteen.

`touch-manipulation` is the only token that belongs to the base alone, and a
partial copy does not include the whole base, so the discriminator is weak by
measurement. **The check is kept anyway**, because the alternatives are worse:
dropping `touch-manipulation` fires on the pair, which flags all ten sites the
moment the rule lands — ten suppressions and a rule nobody reads, plus one per
new chip. Tightening it to catch the six means six more suppressions, or six
rewrites onto a `<Button>` for which no `BTN_SIZES` entry fits (an icon-only
`h-8 w-8`, a filled-neutral pagination button) and no `BTN_VARIANTS` entry
exists for two of them. Those are DESIGN additions already recorded as debt at
their call sites; the fix for the six is the missing primitives, not a wider net.

**Exemptions, all deliberate.**
- `src/lib/ui.ts` — the module that owns the patterns.
- `**/*.test.*` and `src/test-utils/**` — a test that pins a class name has to
  write it as a **literal**; asserting against the imported constant would be a
  tautology, since mutating the constant moves both sides of the assertion. The
  tests are the layer that holds the tokens honest, so they are the one place
  the rule must not reach.
- **Two** inline, rule-specific `eslint-disable` comments, and the reasons are
  not the same shape. `SkipLink.tsx:61` covers one recorded divergence: a skip
  link must reveal on any focus, not `focus-visible:`. The `<textarea>` in
  `AlertsPage.tsx:687` covers **two** on one line — a focus ring *and* an
  `INPUT_BASE` re-type (it carries `bg-slate-800 rounded-lg
  placeholder-slate-500`, with `text-slate-200` where the constant has
  `text-slate-100`), and the reason says so. `eslint-disable-next-line` takes
  rule names, not message ids, so two directives on one line is not
  expressible; the consequence is named at the site instead, because the
  unused-directive guard only fires when **both** are resolved.

  **Both were measured, not read off the reasons.** Deleting each directive and
  running ESLint is the only way to know what a suppression actually silences:
  `SkipLink.tsx` silences exactly one check (`bareFocus`), and the `<textarea>`
  exactly two (`bareFocus` and `rawInputChrome`) — which is what its reason
  claims, and the reason names both by id. A suppression that covered more than
  its reason is invisible to review, which is the failure this pair was audited
  for.

**On the line numbers above.** This section carries the most line-numbered
citations in the file, and a stale one is a specific failure mode: it survives
review because nobody checks it, and it rots silently into pointing at the wrong
line. Every one of them was recomputed against the tree rather than spot-fixed,
which turned up **eight** wrong out of fourteen — not the one or two a review
would have suspected. Two habits keep them honest: prefer a symbol (the named
`ActionButton` in AlertsPage) wherever a line number adds nothing, and when a
cited file is edited in the same pass, re-check its citations afterwards rather
than assuming they moved.

`reportUnusedDisableDirectives` is `"error"`, not ESLint's `"warn"` default.
That default is a lie wherever the promise is made: `npm run lint` is plain
`eslint .` with no `--max-warnings 0`, so a warning exits 0. Verified: an
orphaned suppression, and both live suppressions with their divergence resolved
but the excuse kept, now exit 1. **New `npm run lint` baseline: 0, with the 3
pre-existing `react-refresh` warnings; non-zero if any suppression has expired.**

**The rule is tested.** `frontend/eslint-rules/ui-class-tokens.test.js` is a
`RuleTester` suite (95 cases) covering every check, its valid half, the scoping
decisions and the reported node kind, plus a namespace-by-namespace check of
the painting list. 26 deliberate mutations of the rule were run against it and
all 26 go red — which is the only reason to believe it. The suite is the one
file whose purpose is to contain class strings the build must **not** emit, so
`src/index.css` carries `@source not "../eslint-rules"`: without it the tests
alone shipped 30 unmatchable rules (3.6 kB), every one of them a class the rule
exists to forbid.

**Prose does not trip the rule.** The rule reads the AST, not raw text, so the
many comments in this codebase that quote `focus:` or `focus-visible:` to explain
a decision are invisible to it. Tailwind's scanner, by contrast, reads comments
— see the note in `src/lib/ui.ts` about a comment that emitted the rule it
denied, and the `@source not` line above for what that costs when a test file
cannot avoid naming a class.

### The other half: `filter-rows.a11y.test.tsx`

**The rule above catches a class string that is PRESENT and wrong. It cannot
catch one that is ABSENT**, and absence is how three of the four filter rows in
this product ended up with no focus treatment: nine call sites carried
`FOCUS_RING` and three did not, and nothing recorded the difference. A keyboard
user tabbing those rows got no indicator of any kind.

So the missing-class half is a **test**, not a lint check, and the choice is
deliberate. A rule for absence has to read JSX, decide which elements are
interactive, and then either exempt every recorded divergence with a
suppression — the "ten suppressions and a rule nobody reads" outcome the
sections above warn against twice — or carry a new exemption vocabulary that is
its own rot. A test enumerates the controls that actually rendered and asks the
one question that matters, which also means a **fifth pill added to a filter
row goes red on its own** rather than waiting to be noticed.

Four properties make it falsifiable rather than decorative, and each was checked
by breaking the code it observes:

- It reads the **rendered DOM** and asserts the two house tokens as **literals**.
  Asserting "carries `FOCUS_RING`" would be a tautology, since mutating the
  constant moves both sides.
- It asserts an explicit **control count** per surface, so a row that stops
  rendering — or a selector that stops matching — cannot turn the loop vacuous.
- It rejects any bare `focus:`-prefixed token on the same control, so a ring that
  fires on mouse click cannot satisfy a check that only looked for "a ring".
- Measured both ways: removing `FOCUS_RING` from one row produces one named
  failure (`AlertsPage status filter row: "Todas" is missing
  focus-visible:ring-2`); removing it from all three produces three.

**Two assertions had to be flipped, not deleted.** `AlertsPage.primitives` and
`TransactionsPage` each pinned the ring's *absence* as "the accessibility cost of
the gap" — the conflation being undone is that the missing `BTN_VARIANTS` entry
*caused* the missing ring. It did not: a ring is one orthogonal token and
composing it changes no fill, radius or size. The variant is still owed and still
not made; the ring half is closed.

---

## Stitch design references

- Stitch project ID: `11464160867924444499`
- Screen "Create Transaction Dashboard" (id: `952aea9968614581898bf90eef117508`)
- Screen "Fraud Score Result" (id: `221af73c17984fbd8e24968b15205b23`)

**Normalization rules** (Stitch generated inconsistencies between the two screens):
- Brand name → "Fraud Detector" (the second screen says "Shield Sentinel", drop it)
- Sidebar nav → 3 items: Dashboard, Transacciones, Alertas (drop "Ajustes" and the "Nuevas Reglas" CTA from the second screen)

---

## Mobile

Responsive retrofit. Desktop (md+ ≥ 768px) remains pixel-identical to the original design.

### Breakpoints
| Prefix | Min-width | Purpose |
|--------|-----------|---------|
| `sm` | 640px | SHAP stacking break, skeleton grid |
| `md` | 768px | Sidebar visible, table mode, card list hidden |

### Sidebar Drawer
- Burger: `md:hidden fixed top-4 left-4 z-50` — only visible below md
- Panel: `fixed inset-y-0 left-0 z-[60]` with `role="dialog"`, `aria-modal="true"`
- Backdrop: `fixed inset-0 bg-black/60 z-[55]`
- Escape key and backdrop click close the drawer; body scroll locked when open
- Desktop aside: `hidden md:flex` — structurally identical to pre-mobile code

### Card-List Pattern (TransactionsPage, AlertsPage)
- Mobile cards: `md:hidden space-y-3` container, each card `data-testid="tx-card-{id}"` or `alert-card-{id}"`
- Desktop table: `hidden md:block` wrapper around the existing `overflow-x-auto` table
- This keeps the md+ table DOM completely unchanged

### Touch Targets (≥ 40px)
- Applied via `max-md:min-h-[40px] max-md:px-3 max-md:text-xs` on interactive elements
- Ensures WCAG 2.5.8 compliance on viewports below 768px
- **BOTH axes, for a square icon-only control.** `min-h` alone turns a 20px box
  into a 40×20 target, which is still under the floor on the axis the floor is
  about. An icon-only control also takes `min-w`. The back arrow in
  `TransactionDetail` and the burger in `Sidebar` were the two that did not; the
  glyph on each stays at its current size, because the target grew and the icon
  did not.
- **The prefix is `max-md:` only when the control also exists at `md+`.** The
  burger is `md:hidden`, so it exists only below the breakpoint where the floor
  applies and takes an unconditional `min-h`/`min-w`; a `max-md:` prefix there
  would be true for every pixel it is ever visible.
- Six pagination controls (three paginations, prev/next each) carry the floor
  plus `FOCUS_RING`. They had `hover:` and no focus treatment at all, and at
  24–28px they were the smallest targets in the product.
- Pinned by `src/tests/filter-rows.a11y.test.tsx` in both directions.

### Overflow Guard
- Every page root div includes `overflow-x-hidden` to prevent horizontal scroll at 375px
- Tables wrapped in `overflow-x-auto` for safe horizontal scroll on narrow screens

### SHAP Attribution (diverging bars)

`<ShapAttributionCard>` renders one diverging bar per feature around a
central zero axis. **Reading guide** (semantics pinned by tests, do not change):

- **Right of the axis = positive contribution → pushes the ML score toward
  fraud → red (`risk-critical` token).**
- **Left of the axis = negative contribution → pushes toward legitimate →
  green (`risk-clean` token).**
- Bar length is normalized against the largest |contribution| in the set
  (each side spans half the track, so full scale reaches its edge).
- The sign→direction mapping lives in `lib/shap.ts::contributionDirection`
  (`>= 0` → fraud). Direction text ("Hacia fraude" / "Hacia legítimo") and
  the signed mono value stay right-aligned.
- Bars animate width from 0 on mount (600ms, same easing as the gauge);
  reduced-motion renders final width immediately.
- Mobile stacking (pinned): rows keep
  `flex flex-col sm:flex-row items-start sm:items-center gap-1 sm:gap-3`;
  labels `sm:w-44 truncate` with `title` attribute; direction badge
  `w-auto sm:w-24`.

### States (empty / error / success)

Composed empty, failure and success states render through **`<State>`**
(`src/components/State.tsx`) — never hand-roll a centered "no data" or "we
could not load" block. One shared component serves BOTH mobile card views and
desktop table cells (use `compact` inside `<td>`). It replaces the former
`<EmptyState>` and `<ErrorState>`, which were two variants of one layout:

- **Props:** `tone` (`empty` | `error` | `success`), `icon` (slot — caller
  supplies inline SVG line-art ~64px), `title` (`text-slate-300`), optional
  one-line `hint` (`text-slate-500`), optional `action` CTA slot, `onRetry` +
  `retryLabel` for the canonical retry control, `compact`.
- **The tones differ SEMANTICALLY, by live-region politeness — not by colour
  alone.** `--color-accent` and `--color-risk-critical` are deliberately
  independent reds (see the Accent contract above), so sharing a colour is not
  sharing a meaning. `error` is assertive (`role="alert"`, it interrupts);
  `success` is polite (`role="status"`); `empty` has no role (an empty list
  is absence, not news, and a live region would announce "nothing to see here"
  on every page load). Icon colour reinforces this: `risk-critical` / `clean` /
  `slate-600`.
- **The one exception: an `empty` state that offers `onRetry` IS a
  `role="status"`.** `onRetry` is legal on every tone, so an empty state can be
  the RESULT OF SOMETHING THE USER JUST DID - filters applied, a retry pressed -
  and announcing nothing leaves them pressing a button with no feedback at all.
  Same shape as `data?.total || 0` rendering "0 alertas" on a failed query,
  which is what made the error tone necessary in the first place. So the role is
  not a property of the tone ALONE: empty-with-retry speaks, empty-without stays
  silent. All four current `empty` call sites pass no `onRetry`, so the rule is
  latent and no page load has become chattier.
- **`title` is required for `empty` and `success`, optional for `error`.** The
  failure state has default copy and the global error boundary depends on it;
  there is no default empty or success copy in this product, and minting some
  would be inventing voice. A union encodes it, so `<State />` does not compile
  and `<State tone="error" />` does. **The default copy is
  "No se pudieron cargar los datos" / "Revisá tu conexión o intentá de nuevo en
  unos segundos."** — named here because the `ErrorBoundary` class fallback is
  the only call site that reaches them, so they are invisible everywhere else
  and were emptied rather than replaced when the two components merged.
- **`onRetry` is not error-only.** The retry control renders iff `onRetry` is
  given, on any tone — a filter that lands on an empty result is still a
  failure the user has to be able to clear. It is the shared `Button`
  (`secondary` / `sm`), so it matches a page's hand-written retry beside it.
- **`action` and `onRetry` are separate slots, in SEPARATE rows.** The error
  sites want a canonical control; the empty sites pass their own
  `<a>`/`<button>`. Each slot renders its own `div.mt-4`, and the API does not
  arbitrate between them: no call site uses both, and a future one that does
  gets two rows — visible in review rather than silently resolved.
- **No `className` prop.** Tailwind resolves two utilities of one property by
  stylesheet order, not attribute order, so a caller could not change a colour
  or a size through it anyway. **Four** call sites need a border and a
  background — both AlertsPage failure blocks and both DashboardPage failure
  blocks — and three of them wrap `<State>` in a sibling `div`. The fourth,
  DashboardPage's transactions banner, is hand-rolled inside its own bordered
  `div` and never renders `<State>` at all, so the count of "wrapper `div`s" is
  four and the count of "`<State>` call sites needing a wrapper" is **three**.
  The two numbers were the same until the fourth was checked.
- **Built-in line-art glyphs:** `ReceiptLineArt` (transactions),
  `BellLineArt` (alerts) and `AlertLineArt` (failures) — stroke-only SVGs
  inheriting `currentColor`.
- **Consumers:** AlertsPage (mobile + desktop, both tones), DashboardPage
  (metrics + charts failures), TransactionsPage, TransactionTable,
  ErrorBoundary.

**Known divergence, reported not migrated.** Four hand-rolled state blocks
remain, because adopting `<State>` would change their pixels and this pass is
scoped to no visual change. All four now carry `role="alert"` - a review found
two of them silent while their siblings in the same files announced, and fixing
that was a defect fix rather than a migration:

1. `TransactionsPage`'s mobile list error (`text-center py-12`, one
   `text-red-400` line).
2. `TransactionDetail`'s page-level failure at `if (error || !tx)`
   (`text-center` + `text-red-400`). Note the copy: a 404 makes `error`
   truthy, so it renders "Error al cargar la transaccion" and NOT
   "Transaccion no encontrada" - the API answers a missing row with 404, so
   the second string belongs to a branch this component cannot reach.
3. `TransactionDetail`'s report error (`flex flex-col items-center px-6 py-8
   text-center`, no icon, no retry). This one always had a live region.
4. `TransactionDetail`'s `report.status === "failed"` block. It sat 40 lines
   from #3 and did not announce, so one page had two failure UIs and one of
   them was silent.

All four should become `<State tone="error">` when the vertical rhythm is
decided deliberately rather than inherited from a one-off.

**`success` currently has ZERO call sites.** It exists because the merge that
produced `<State>` was justified by exactly this gap: with only empty and error
available, there was no way to say "it worked" in the same idiom. So the tone is
untested in production and the gap it was added for is still open. Treat a
`something succeeded` panel as the first thing to reach for it.

### Loading States

Two tiers:

1. **Skeleton pulse** (`.animate-pulse`) — existing per-card skeletons
   (e.g. ScoreResultCard's `grid grid-cols-1 sm:grid-cols-3` block).
2. **Shimmer sweep** (`.animate-shimmer`, Phase 2) — composed chart-area
   placeholders: rounded `h-[200px]` blocks with a gradient highlight
   sweeping via `translateX`. The gradient derives from
   `var(--color-text-muted)` through `color-mix` — no hex in the utility.
   Apply `pointer-events-none`; disabled under `prefers-reduced-motion`.

Report entrance: `.animate-report-in` fades/slides the completed LLM report
in once on mount; reduced-motion disables it.

### Skeleton Grid
- ScoreResultCard skeleton: `grid grid-cols-1 sm:grid-cols-3` (stacks below 640px)

### Testing Note
- jsdom does not process Tailwind `max-md:` or `md:` media queries — tests assert className presence, not computed styles
