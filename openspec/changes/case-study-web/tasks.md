# Tasks: case-study-web

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 800–1000 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: styles.css → PR 2: index.html → PR 3: es.html + cross-links + verification |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | CSS token foundation + base styles | PR 1 | ~150–200 lines. Foundation everything else depends on. |
| 2 | index.html full EN page + inline SVG | PR 2 | ~350–450 lines. Depends on PR 1. |
| 3 | es.html + cross-links + local verification | PR 3 | ~350–400 lines. Depends on PR 2. |

## Phase 1: CSS Token Foundation

- [x] 1.1 Create `case-study/styles.css` with DESIGN.md token comment header listing source hex values, then CSS custom properties: `--color-page-bg` (#020617), `--color-card-bg` (#0f172a), `--color-border-subtle` (#1e293b), `--color-text-primary` (#f1f5f9), `--color-text-secondary` (#cbd5e1), `--color-text-muted` (#94a3b8), `--color-primary` (#dc2626), `--color-focus-ring` (#ef4444), `--color-status-info` (#3b82f6)
- [x] 1.2 Add font-stack custom properties: `--font-body` (Inter system stack) and `--font-mono` (JetBrains Mono stack)
- [x] 1.3 Add base reset, box-sizing, body styles (background, font, color), and `*` focus outline using `--color-focus-ring`
- [x] 1.4 Add typography scale: h1 (32px/700), h2 (18px/600), h3 (16px/600), body (14px/400), metric numbers (JetBrains Mono, 32px/700), metric labels (12px/400), stat pills (12px/500)
- [x] 1.5 Add layout classes: `.container` (max-width 1280px, centered), `.nav`, `.hero`, `.section`, `.cards-grid` (3-col flex), `.card` (border/bg/radius/padding per design), `.metric-strip`, `.threshold-table`, `.footer-cta`
- [x] 1.6 Add SVG-specific styles: `#architecture-diagram` max-width, responsive scaling, layer box fills/strokes using CSS vars, arrow colors, ensemble accent border
- [x] 1.7 Add `prefers-reduced-motion: reduce` media query disabling transitions

**Verify**: `grep "var(--color-" case-study/styles.css` returns 9+ token variables; `grep "prefers-color-scheme" case-study/styles.css` returns zero matches.

## Phase 2: English Page Structure + Content

- [x] 2.1 Create `case-study/index.html` with `<!DOCTYPE html>`, `<html lang="en">`, `<head>` containing charset, viewport, title "Fraud Detector — Case Study", `<link rel="stylesheet" href="styles.css">`, zero external requests
- [x] 2.2 Build nav: "Fraud Detector" brand text, EN|ES language toggle link (`<a href="es.html">`), GitHub repo link (`<a href="https://github.com/mikelrh-dev/fraud-detector">`)
- [x] 2.3 Build hero: h1 tagline, subtitle sentence, 3 stat pills: "9 rules · 337 tests · 23 endpoints"
- [x] 2.4 Build "How It Works" section with inline `<svg>` for architecture diagram (viewBox `0 0 1200 400`, `role="img"`, `aria-label`, `<title>` elements per design spec) — 3-layer flow boxes + arrows + Ensemble + PostgreSQL + Workers + DLQ using semantic fraud colors
- [x] 2.5 Build "Key Decisions" section: 3 `.card` elements — (1) 3-layer ensemble with weights 0.60/0.25/0.15, (2) LLM explains never decides, (3) Redis Streams + DLQ pattern
- [x] 2.6 Build metrics strip: stat blocks for rules/tests/endpoints + threshold tier table (4 rows: $0–$1K ≥70, $1K–$10K ≥50, $10K–$50K ≥45, $50K+ ≥40) — values from README.md
- [x] 2.7 Build footer CTA: "View on GitHub" button (accent color), language toggle link

**Verify**: `grep 'lang="en"' case-study/index.html`; `grep "<svg" case-study/index.html`; `grep "≥ 70\|≥ 50\|≥ 45\|≥ 40" case-study/index.html` all 4 tiers; `grep "github.com/mikelrh-dev/fraud-detector" case-study/index.html`; `grep -E "https?://|cdn\.|fonts\." case-study/index.html` returns only the GitHub link.

## Phase 3: Spanish Page Parity

- [x] 3.1 Create `case-study/es.html` mirroring index.html structure with `<html lang="es">`, same `<head>` (charset, viewport, title "Fraud Detector — Caso de Estudio", stylesheet link)
- [x] 3.2 Translate nav: brand same, toggle links to `index.html`, GitHub link same
- [x] 3.3 Translate hero section: h1, subtitle, stat pills (numbers stay identical)
- [x] 3.4 Duplicate inline SVG architecture diagram (identical markup, Spanish `<title>` elements: "Capa 1: Motor de Reglas", "Capa 2: XGBoost ML", "Capa 3: Análisis de Contexto")
- [x] 3.5 Translate decision story cards (same factual content, Spanish prose)
- [x] 3.6 Translate metrics strip labels and threshold table header text (numbers identical)
- [x] 3.7 Translate footer CTA (same GitHub link, Spanish button text)

**Verify**: `grep 'lang="es"' case-study/es.html`; `grep "es.html" case-study/index.html` (EN→ES link); `grep "index.html" case-study/es.html` (ES→EN link); count h1/h2/h3 headings in both files — must match.

## Phase 4: Cross-Links + Final Local Verification

- [x] 4.1 Confirm bidirectional language links: `index.html` href resolves to `es.html`, `es.html` href resolves to `index.html`
- [x] 4.2 Confirm GitHub link on both pages: `grep "github.com/mikelrh-dev/fraud-detector"` in both files
- [x] 4.3 Confirm zero external network requests: `grep -E "https?://|cdn\.|fonts\."` on both files — only GitHub link and stylesheet href allowed
- [x] 4.4 Confirm no personal data: `grep -iE "mikel|profile|personal|wiki"` on both files — must return zero matches
- [x] 4.5 Local file:// smoke test: open `case-study/index.html` in browser — verify layout, dark theme, SVG renders, no console errors
- [x] 4.6 Local http.server test: run `python -m http.server` from repo root, navigate to `/case-study/index.html` and `/case-study/es.html` — both load, styles applied, no 404s
- [x] 4.7 Verify content accuracy: spot-check 9 rules, 337 tests, 23 endpoints, weights 0.60/0.25/0.15, threshold tiers match README.md exactly
