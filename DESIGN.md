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
| Review / Flagged | `#eab308` | `yellow-500` |
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
- **Trend chart**: `AreaChart` with a vertical `linearGradient` (`id="trend-fill"`, risk-warn 0.18→0), strokeWidth 2.5, no dots, activeDot stroked with `THEME.pageBg`; horizontal-only dashed grid from `THEME.gridSoft` (slate-800); axis lines off.
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
| `bareFocus` | any `focus:`-prefixed class | `FOCUS_RING` (which is `focus-visible:`-prefixed on purpose) |
| `rawFocusRing` | `focus-visible:outline-none` / `:ring-2` / `:ring-focus-ring` typed by hand | `FOCUS_RING` |
| `rawInputChrome` | `placeholder-slate-500` + `bg-slate-800` + `rounded-lg` in one class list | `<Input>` or `cn(INPUT_BASE, …)` |
| `rawBtnBase` | `btn-motion` + `active:scale-[0.98]` + `touch-manipulation` in one class list | `<Button>` or `cn(BTN_BASE, …)` |
| `rawHex` | a raw hex literal in a `className` | an `@theme` token in `index.css` |

**Why the last two are combinations and not single tokens.** `bg-slate-800`,
`rounded-lg` and `px-3` are used by cards, panels and buttons; `btn-motion` and
`active:scale-[0.98]` are a PAIR that ten filter-chip, pill and icon-toggle call
sites legitimately want *without* the rest of `BTN_BASE`, because a filter chip
is not a button. Banning either token alone would ban the design system;
banning the pair would force `inline-flex` + `font-medium` onto a chip, which is
a visual change dressed up as lint compliance. What identifies a hand-rolled
base is the token that belongs to the base alone — `touch-manipulation`.

**Two scopes.** The two focus checks apply to *every* string literal in a file,
including module-level constants, because a focus ring is a correctness
contract and it has to hold wherever the class string is written. The three
composition checks apply to `className` values only, since a class list away
from a call site is not a composition.

**Exemptions, all deliberate.**
- `src/lib/ui.ts` — the module that owns the patterns.
- `**/*.test.*` and `src/test-utils/**` — a test that pins a class name has to
  write it as a **literal**; asserting against the imported constant would be a
  tautology, since mutating the constant moves both sides of the assertion. The
  tests are the layer that holds the tokens honest, so they are the one place
  the rule must not reach.
- Two inline, rule-specific `eslint-disable` comments, one per **recorded**
  focus-ring divergence that predates the rule: `AUTH_INPUT_CLASS` in
  `AuthSplitLayout.tsx` and the `<textarea>` in `AlertsPage.tsx`. Both are
  documented at length at their call sites and both are owed to the visual pass.
  `reportUnusedDisableDirectives` is on, so resolving either divergence without
  deleting its suppression fails the lint run.

**Prose does not trip the rule.** The rule reads the AST, not raw text, so the
many comments in this codebase that quote `focus:` or `focus-visible:` to explain
a decision are invisible to it. Tailwind's scanner, by contrast, reads comments
— see the note in `src/lib/ui.ts` about a comment that emitted the rule it
denied.

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

### Empty States

Composed empty states render through **`<EmptyState>`**
(`src/components/EmptyState.tsx`) — never hand-roll a centered "no data"
block. One shared component serves BOTH mobile card views and desktop table
cells (use `compact` inside `<td>`):

- Props: `icon` (slot — caller supplies inline SVG line-art ~64px),
  `title` (`text-slate-300`), optional one-line `hint` (`text-slate-500`),
  optional `action` CTA slot.
- Built-in line-art glyphs: `ReceiptLineArt` (transactions) and
  `BellLineArt` (alerts) — stroke-only SVGs inheriting `currentColor`.
- Consumers: TransactionsPage, AlertsPage (mobile + desktop), TransactionTable.

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
