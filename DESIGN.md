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
| Action base | `#dc2626` | `red-600` |
| Action hover | `#b91c1c` | `red-700` |
| Focus ring | `#ef4444` | `red-500`, 2px offset |

---

## Typography

- **Body / UI:** Geist Variable — self-hosted via `@fontsource-variable/geist` (imported in `src/main.tsx`, before `index.css`)
- **Monospace** (IDs, card numbers, UUIDs): JetBrains Mono — self-hosted via `@fontsource/jetbrains-mono`
- Declared as `--font-sans` / `--font-mono` inside the `@theme` block of `frontend/src/index.css`
- Google Fonts CDN links for Inter/JetBrains Mono were REMOVED from `index.html` (Material Symbols Outlined stays on CDN until the icon-system phase)

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
- **Primary:** `bg-red-600`, text white, hover `bg-red-700`, 8px radius, 12px 24px padding
- **Secondary:** transparent, border `slate-700`, text `slate-300`, hover `bg-slate-800`
- **Danger:** same as primary (this product's primary action IS risky)
- **Ghost:** text only, `slate-400`, hover text `slate-100`

### Badges / Pills

All badges render through the **`Badge` primitive** (`src/components/Badge.tsx`) — never hand-roll pill styling:

- **Tone prop** (semantic, zero hardcoded hex): `clean` → `risk-clean`, `warn` → `risk-warn`, `critical` → `risk-critical`, `info` → `status-info`
- **Background:** semantic color at 10% opacity (`bg-risk-XXX/10`)
- **Border:** 1px solid semantic color at 30% opacity (`border-risk-XXX/30`)
- **Text:** full semantic color (`text-risk-XXX`)
- **Padding/radius:** `rounded-full`; sizes `md` (px-3 py-1 text-sm) and `sm` (px-2 py-0.5 text-[11px])
- **Icon slot:** optional Material Symbols glyph via the `icon` prop
- Consumers: `ClassificationBadge` (approved/flagged/blocked), `AlertStatusBadge` (open→warn, reviewed→info, resolved→clean)

### Charts

Chart colors come from **`src/lib/chart-theme.ts`** (`THEME`). Rule: **no literal hex inside chart components** — enforced by `chart-theme.test.ts`. The hex values in `THEME` must mirror the `@theme` CSS tokens in `index.css` until Tailwind exposes theme vars to JS; both sides are guarded by tests.

### Tables
- Header: `slate-800` bg, `slate-400` text, 12px / 500
- Rows: alternating `slate-900` / `slate-950`
- Row hover: `slate-800`
- Cell padding: 12px 16px
- Borders: 1px solid `slate-800` between rows

### Score Gauge (ensemble risk score, 0-100)
- Track: `slate-800`
- Fill: linear gradient `green-500` → `yellow-500` → `red-500`
- Marker: white vertical bar, subtle glow
- Height: 12px, full radius
- Score: 32px / 700 displayed above the bar in white

---

## Iconography

- **Material Symbols Outlined** (Google Fonts) — chosen by Stitch during design generation
- **Decision:** keep Material Symbols for design fidelity and zero-dependency loading (Google Fonts CDN)
- Default size: 20px in nav, 18-20px in cards
- Stroke: variable, controlled by `font-variation-settings`
- Required icon set (used by the app): `dashboard`, `payments`, `notifications_active`, `policy`, `rule`, `add`, `logout`, `arrow_forward`

---

## Motion

- Hover transitions: 150ms ease-out
- No bounce or playful animations
- Loading: subtle pulse (`slate-700` ↔ `slate-800`) on skeleton placeholders
- Score gauge fill: 400ms ease-out on first render

---

## Don'ts

- No bright white backgrounds (eye strain during long analyst shifts)
- No drop shadows for elevation (use borders + subtle bg shifts)
- No gradient backgrounds on the page level (gauge is the only exception)
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

### SHAP Stacking
- Rows: `flex flex-col sm:flex-row items-start sm:items-center gap-1 sm:gap-3`
- Labels: `w-full sm:w-44 truncate` with `title` attribute for full text on hover
- Direction badge: `w-auto sm:w-24`

### Skeleton Grid
- ScoreResultCard skeleton: `grid grid-cols-1 sm:grid-cols-3` (stacks below 640px)

### Testing Note
- jsdom does not process Tailwind `max-md:` or `md:` media queries — tests assert className presence, not computed styles
