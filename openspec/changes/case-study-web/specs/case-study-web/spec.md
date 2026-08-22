# Case Study Web Specification

## Purpose

Static bilingual portfolio page (EN/ES) presenting the fraud-detector's architectural decisions, metrics, and design rationale. Zero build dependencies — must render from `file://` or a local HTTP server.

## Requirements

### Requirement: Local Rendering

The page MUST render correctly when opened via `file://` and when served via `python -m http.server`. No external network requests (CDN fonts, external scripts, remote images) are permitted for core content.

#### Scenario: file:// double-click opens English page

- GIVEN `case-study/index.html` exists on disk
- WHEN the user opens it via `file://` in a browser
- THEN the page renders with correct layout, styling, and inline SVG
- AND no network requests to external origins are visible in DevTools

#### Scenario: python -m http.server serves both pages

- GIVEN the user runs `python -m http.server` from the repo root
- WHEN navigating to `/case-study/index.html` and `/case-study/es.html`
- THEN both pages load without 404 errors
- AND all styles from `styles.css` are applied

#### Scenario: Offline complete rendering

- GIVEN the device has no internet connection
- WHEN either language page is opened via `file://`
- THEN all visual elements (text, SVG, styling) render identically to the online version

---

### Requirement: Content Accuracy

All metrics displayed on the case-study page MUST match README.md source-of-truth values exactly. Enumerated values: 9 rules, 337 tests, 23 endpoints, ensemble weights 0.60/0.25/0.15, threshold tiers ($0–$1K ≥70, $1K–$10K ≥50, $10K–$50K ≥45, $50K+ ≥40).

#### Scenario: Metrics match README

- GIVEN README.md contains the metrics: 9 rules, 337 tests, 23 endpoints, weights 0.60/0.25/0.15
- WHEN the case-study page renders the metrics section
- THEN each displayed number is identical to the README value
- AND no rounded, approximate, or derived values replace exact figures

#### Scenario: Threshold tiers match README

- GIVEN README.md defines threshold tiers as: $0–$1K ≥70, $1K–$10K ≥50, $10K–$50K ≥45, $50K+ ≥40
- WHEN the case-study page presents the threshold tier table
- THEN all four tiers and their threshold values match README exactly

---

### Requirement: Language Parity

`es.html` MUST contain the same sections, information structure, and factual content as `index.html`, with Spanish copy and `lang="es"`. `index.html` MUST have `lang="en"`.

#### Scenario: Structural parity between language pages

- GIVEN both `index.html` and `es.html` exist
- WHEN both pages are parsed for section headings (h1, h2, h3)
- THEN `es.html` contains the same number of sections and same information hierarchy as `index.html`

#### Scenario: HTML lang attributes correct

- GIVEN `index.html` and `es.html` are served
- WHEN inspecting the `<html>` element of each
- THEN `index.html` has `lang="en"` and `es.html` has `lang="es"`

#### Scenario: Spanish copy is not raw English

- GIVEN `es.html` is rendered
- WHEN reading the body text content
- THEN all visible text is in Spanish (not English placeholders or untranslated strings)

---

### Requirement: Cross-Linking

Each language page MUST link to the other language version. Both pages MUST link to the GitHub repository.

#### Scenario: EN ↔ ES bidirectional links exist

- GIVEN `index.html` and `es.html` are rendered
- WHEN inspecting navigation or language-toggle elements
- THEN `index.html` contains a link whose href resolves to `es.html`
- AND `es.html` contains a link whose href resolves to `index.html`

#### Scenario: GitHub repo link present on both pages

- GIVEN both language pages are rendered
- WHEN inspecting anchor elements
- THEN both pages contain at least one link to `https://github.com/mikelrh-dev/fraud-detector`

---

### Requirement: Dark-Only Theme

The page MUST use a dark-only theme. Colors MUST be defined as CSS custom properties copied from DESIGN.md tokens. No light mode or theme toggle.

#### Scenario: DESIGN.md tokens present as CSS variables

- GIVEN `case-study/styles.css` is loaded
- WHEN inspecting computed styles on the page
- THEN CSS custom properties exist matching DESIGN.md hex values: page-bg `#020617`, card-bg `#0f172a`, border `#1e293b`, text-primary `#f1f5f9`, text-secondary `#cbd5e1`, text-muted `#94a3b8`, accent `#dc2626`

#### Scenario: No light mode toggle exists

- GIVEN either language page is rendered
- WHEN inspecting the DOM
- THEN no theme-toggle button, switch, or `prefers-color-scheme` media query that changes the color scheme exists

---

### Requirement: No Personal Data

The page content MUST contain zero personal information sourced from the `wiki/` directory — no profile references, personal reflections, or biographical data.

#### Scenario: Personal data absent from HTML

- GIVEN both `index.html` and `es.html` are rendered
- WHEN inspecting visible text and meta tags
- THEN no content references personal names, biographical details, or wiki-specific personal reflections from `wiki/`

---

### Requirement: Inline Architecture Diagram

The architecture diagram MUST render as inline SVG within the HTML. No external image files (`.png`, `.jpg`, `.svg` files) are required for the core diagram content.

#### Scenario: SVG renders inline without external files

- GIVEN `index.html` is opened via `file://`
- WHEN inspecting the architecture diagram section
- THEN the diagram is an inline `<svg>` element in the DOM
- AND no `<img src="...">` or `<object>` tags reference external image files for the diagram

#### Scenario: Diagram depicts 3-layer pipeline

- GIVEN the architecture SVG renders
- WHEN inspecting SVG text/elements
- THEN the diagram visually represents the 3-layer pipeline: Rules → ML → Context → Ensemble
