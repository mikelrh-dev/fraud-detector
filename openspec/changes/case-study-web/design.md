# Design: case-study-web

## Technical Approach

Static HTML + CSS case study page (`case-study/` folder). Two HTML files (EN/ES) share a single `styles.css`. No build step, no JS frameworks, no external CDN requests. DESIGN.md tokens are manually copied into CSS custom properties — a documented manual-sync dependency. All icons are inline SVG. Architecture diagram is an inline `<svg>` element with semantic fraud colors.

## Architecture Decisions

### Decision: CSS Token Strategy

**Choice**: Copy DESIGN.md hex values into CSS custom properties in `styles.css`
**Alternatives considered**: Tailwind CDN (rejected — adds external dependency, breaks `file://` offline); CSS `@import` from DESIGN.md (rejected — not a valid CSS source)
**Rationale**: Self-contained CSS file. Zero network requests. Manual sync documented as a comment block at the top of `styles.css` listing source hex values for each variable.

### Decision: Language Handling

**Choice**: Two complete HTML files (`index.html`, `es.html`) sharing `styles.css`
**Alternatives considered**: Single HTML with JS-based language toggle (rejected — adds JS dependency, breaks zero-JS goal); `data-` attributes with CSS `:lang()` (rejected — overly complex for 2 languages)
**Rationale**: Simplest approach. Each file is self-contained. Cross-links in nav bar. No JS needed. `lang="en"` / `lang="es"` on `<html>` elements for accessibility.

### Decision: SVG Architecture Diagram

**Choice**: Inline `<svg>` in each HTML file, duplicated (not shared via `<img>`)
**Alternatives considered**: External `.svg` file referenced via `<img>` (rejected — breaks `file://` with CSP, adds extra file); shared via `<object>` (rejected — same CSP issue)
**Rationale**: Inline SVG renders identically across `file://` and `http.server`. Duplicated in both language files (small overhead, no build tool needed to deduplicate). `<title>` elements and `aria-label` on groups for screen reader accessibility.

### Decision: Font Stack

**Choice**: System font stack per DESIGN.md — Inter fallback chain for body, JetBrains Mono for metrics/numbers
**Alternatives considered**: Google Fonts CDN (rejected — external dependency, breaks offline); Distinctive display fonts per design-taste-frontend (rejected — DESIGN.md tokens are project source of truth)
**Rationale**: DESIGN.md is authoritative. System stack means zero network requests. JetBrains Mono used exclusively for score numbers, metric values, and weight figures to create visual hierarchy.

### Decision: Card Pattern for Decision Stories

**Choice**: DESIGN.md card spec — `background: var(--color-card-bg)` (#0f172a), `border: 1px solid var(--color-border-subtle)` (#1e293b), `border-radius: 12px`, `padding: 24px`
**Alternatives considered**: Glassmorphism cards (rejected — decorative, not aligned with "analyst at 2am" brand); borderless with spacing only (rejected — cards need visual containment for scannable decision stories)
**Rationale**: Follows DESIGN.md component spec exactly. Cards are for elevation-required hierarchy (decision stories need visual grouping). Subtle bg shifts instead of shadows per DESIGN.md "Don'ts".

## File Layout

```
case-study/
├── index.html      # English version (lang="en")
├── es.html         # Spanish version (lang="es")
└── styles.css      # Shared CSS (DESIGN.md tokens as custom properties)
```

3 files total. No subdirectories. No build artifacts.

## Page Section Anatomy

```
┌─────────────────────────────────────────────┐
│  HEADER / NAV                               │
│  "Fraud Detector" brand + EN|ES toggle      │
│  + GitHub repo link                         │
├─────────────────────────────────────────────┤
│  HOOK / HERO                                │
│  h1: project tagline                        │
│  Subtitle: what it does (1 sentence)        │
│  3 stat pills: 9 rules · 337 tests · 23 endpoints │
├─────────────────────────────────────────────┤
│  ARCHITECTURE DIAGRAM (inline SVG)          │
│  h2: "How It Works"                         │
│  3-layer flow: Rules → ML → Context →       │
│  Ensemble → Storage → Workers → DLQ         │
├─────────────────────────────────────────────┤
│  DECISION STORIES (3 cards)                 │
│  h2: "Key Decisions"                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ Card 1   │ │ Card 2   │ │ Card 3   │    │
│  │ Ensemble │ │ LLM      │ │ Redis    │    │
│  │ 0.60/    │ │ explains │ │ Streams  │    │
│  │ 0.25/    │ │ never    │ │ + DLQ    │    │
│  │ 0.15     │ │ decides  │ │          │    │
│  └──────────┘ └──────────┘ └──────────┘    │
├─────────────────────────────────────────────┤
│  METRICS STRIP                              │
│  Inline stat blocks (no cards, just data)   │
│  Threshold tier table                       │
├─────────────────────────────────────────────┤
│  CTA FOOTER                                 │
│  "View on GitHub" button (red-600)          │
│  Language toggle link                       │
└─────────────────────────────────────────────┘
```

## SVG Diagram Design

### Layout
- Horizontal flow, left-to-right, 3 stages + storage + workers
- Max-width: 1280px (matches DESIGN.md `--spacing-max-content`)
- ViewBox: `0 0 1200 400` (scalable, readable at 1280px)

### 3-Layer Pipeline Flow

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  Layer 1    │   │  Layer 2    │   │  Layer 3    │
│  Rule Engine│──▶│  XGBoost    │──▶│  Context    │
│  9 rules    │   │  10 features│   │  User basel.│
└─────────────┘   └─────────────┘   └─────────────┘
       │                │                │
       └────────────────┼────────────────┘
                        ▼
              ┌─────────────────┐
              │   Ensemble      │
              │  0.60 / 0.25 / │
              │     0.15        │
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │  PostgreSQL +   │
              │  Redis Streams  │
              └────────┬────────┘
                       ▼
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ┌─────────┐  ┌─────────┐  ┌─────────┐
    │ Worker 1│  │ Worker 2│  │ Worker 3│
    │ Scoring │  │ LLM     │  │ Alert   │
    └─────────┘  └─────────┘  └─────────┘
                       │
                       ▼ (failure)
              ┌─────────────────┐
              │  DLQ (Dead      │
              │  Letter Queue)  │
              └─────────────────┘
```

### Semantic Fraud Colors in SVG
- Layer boxes: `var(--color-border-subtle)` stroke, `var(--color-card-bg)` fill
- Arrow connectors: `var(--color-text-muted)` (#94a3b8)
- Ensemble box: `var(--color-primary-container)` (#dc2626) accent border
- DLQ: `var(--color-status-blocked)` (#ef4444) — fraud/blocked state
- Worker boxes: `var(--color-status-info)` (#3b82f6) — info/neutral state
- Labels: `var(--color-text-secondary)` (#cbd5e1)
- Weight numbers: `var(--color-text-primary)` (#f1f5f9) in JetBrains Mono

### Accessibility
- `<title>` element inside `<svg>` for screen reader announcement
- `role="img"` and `aria-label="Architecture diagram: 3-layer fraud detection pipeline"` on `<svg>`
- Each layer group has `<title>` child: "Layer 1: Rule Engine", "Layer 2: XGBoost ML", "Layer 3: Context Analysis"
- Ensemble group title: "Ensemble scoring with weights 0.60, 0.25, 0.15"
- Minimum 4.5:1 contrast ratio on all text against dark backgrounds (verified: #f1f5f9 on #020617 = 16.7:1)

## Typography

Per DESIGN.md scale, applied via CSS custom properties:

| Element | Font | Size | Weight | Color |
|---------|------|------|--------|-------|
| h1 (hero) | Inter stack | 32px | 700 | `--color-text-primary` |
| h2 (section) | Inter stack | 18px | 600 | `--color-text-primary` |
| h3 (card title) | Inter stack | 16px | 600 | `--color-text-primary` |
| Body | Inter stack | 14px | 400 | `--color-text-secondary` |
| Metric numbers | JetBrains Mono | 32px | 700 | `--color-text-primary` |
| Metric labels | Inter stack | 12px | 400 | `--color-text-muted` |
| Stat pills | Inter stack | 12px | 500 | `--color-text-secondary` |

Font stacks:
```css
--font-body: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
--font-mono: "JetBrains Mono", ui-monospace, Menlo, monospace;
```

## Accessibility Plan

- Contrast: all text passes WCAG AA on dark backgrounds (primary #f1f5f9 on #020617 = 16.7:1; secondary #cbd5e1 on #020617 = 11.4:1; muted #94a3b8 on #020617 = 6.5:1)
- Focus states: `2px solid var(--color-focus-ring)` (#ef4444) with 2px offset on all interactive elements
- Semantic headings: single h1, h2 per section, h3 for card titles — strict hierarchy
- `prefers-reduced-motion: reduce` — disable any CSS transitions (minimal transitions planned: hover states only)
- Language: `lang="en"` / `lang="es"` on `<html>`; cross-links in nav
- SVG: `role="img"`, `aria-label`, `<title>` elements on diagram and groups
- No external font loading means no FOUT/FOIT — text is always visible

## Verification Hooks for sdd-verify

| Check | How to verify |
|-------|---------------|
| Metrics match README | `grep "9 rules" case-study/index.html` — must exist; same for "337 tests", "23 endpoints" |
| Threshold tiers | `grep "≥ 70" case-study/index.html` (and ≥ 50, ≥ 45, ≥ 40) — all 4 tiers present |
| Lang attributes | `grep 'lang="en"' case-study/index.html` and `grep 'lang="es"' case-study/es.html` |
| Cross-links | `grep "es.html" case-study/index.html` and `grep "index.html" case-study/es.html` |
| GitHub link | `grep "github.com/mikelrh-dev/fraud-detector" case-study/index.html` |
| No external requests | `grep -E "(https?://|cdn\.|fonts\.)" case-study/index.html` — must return zero matches (except GitHub link) |
| Inline SVG | `grep "<svg" case-study/index.html` — must exist; no `<img src=` for diagram |
| CSS variables | `grep "var(--color-" case-study/styles.css` — must use DESIGN.md token names |
| No light mode | `grep "prefers-color-scheme" case-study/styles.css` — must return zero matches |
| No personal data | `grep -iE "(mikel|profile|personal)" case-study/index.html` — must return zero matches |

## Content Source Mapping

| Case study section | Source | Notes |
|-------------------|--------|-------|
| Metrics (9 rules, 337 tests, 23 endpoints) | README.md lines 7, 24 | Exact values, no rounding |
| Ensemble weights 0.60/0.25/0.15 | README.md line 56 | Formula: `0.60 × rule + 0.25 × ml + 0.15 × context` |
| Threshold tiers | README.md lines 61-66 | **Discrepancy noted**: spec says $1K–$10K ≥50, but tests show ≥60. Use README values (≥50, ≥45, ≥40) as source of truth per proposal |
| Decision 1: 3-layer ensemble | wiki/decisions/fraud-detector-3-layer-architecture.md | Extract rationale, not personal reflections |
| Decision 2: LLM explains, never decides | README.md line 7 + wiki decision doc | "the LLM never decides, it only explains" |
| Decision 3: Redis Streams + DLQ | openspec/changes/event-driven-redis-streams/proposal.md | Consumer groups, XAUTOCLAIM, DLQ pattern |

## Risks

| Risk | Mitigation |
|------|------------|
| DESIGN.md tokens change → styles.css stale | Document dependency in CSS comment header; keep hex values minimal |
| Threshold tier values may drift between README and tests | Implementer MUST verify against README.md (authoritative) not test files |
| SVG diagram duplication across EN/ES | Acceptable for 2 files; no build tool to deduplicate |
| Spanish translation quality | Use neutral/professional Spanish; avoid Rioplatense unless user requests |

## Migration / Rollout

No migration required. New folder, zero impact on existing app, CI, or deployment. Delete `case-study/` to rollback.

## Open Questions

- [ ] Verify threshold tier values: README says $1K–$10K ≥50 but test_ensemble.py tests $1001-10000 → threshold 60. Which is correct? (Flagged to implementer — use README values per proposal contract)
