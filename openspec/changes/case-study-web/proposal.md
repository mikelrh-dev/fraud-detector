# Proposal: case-study-web

## Intent

The fraud-detector project is a production-grade hybrid detection system (rules + ML + LLM) with 337 tests, but has no standalone portfolio page to communicate its architectural decisions. The README serves as both developer docs and overview, but cannot tell the "decision story" — WHY each choice was made, what was rejected, and what was learned. A static case-study page fills this gap for technical interviews, portfolio showcases, and architecture discussions.

## Scope

### In Scope
- `case-study/index.html` — English version, static HTML
- `case-study/es.html` — Spanish version, same structure
- `case-study/styles.css` — shared CSS (DESIGN.md tokens as CSS variables, system font stack, dark-only)
- Inline SVG architecture diagram (3-layer pipeline: Rules → ML → Context)
- 3 decision stories with rejected alternatives: (a) 3-layer ensemble 0.60/0.25/0.15, (b) LLM explains but never decides, (c) Redis Streams + consumer groups + DLQ
- Verified metrics section (9 rules, 337 tests, 23 endpoints — exact from README)
- CTA linking to GitHub repo (no demo link)
- CI-invisible: folder at repo root, not touched by `.github/workflows/ci.yml`

### Out of Scope
- Deployment setup (no VPS config, no GitHub Pages)
- Screenshots or live demo (app requires Docker stack)
- Build step, bundler, or external CDN dependencies
- Light mode or theme toggle
- Interactive elements beyond navigation/links
- Personal data from wiki (profile references, personal reflections)

## Capabilities

### New Capabilities
None — this is a static page, not a system capability. No specs in `openspec/specs/` are created or modified.

### Modified Capabilities
None — no existing spec behavior changes.

## Approach

Static HTML + CSS only. DESIGN.md tokens (hex values, font stack, spacing) are copied into CSS custom properties — no Tailwind, no build tooling. Material Symbols are replaced with inline SVG icons for offline `file://` support. Content is extracted from README.md (metrics) and wiki decision docs (architecture rationale), never copied verbatim. Structure follows cognitive-doc-design patterns: hook → diagram → stories → metrics → CTA.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `case-study/` (new) | New | 3 files: index.html, es.html, styles.css |
| `README.md` | None | Source of truth for metrics, not modified |
| `.github/workflows/ci.yml` | None | CI only touches `frontend/` and `src/` |
| `DESIGN.md` | None | Tokens referenced, not modified |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Content drift (metrics diverge from README) | Medium | Metrics section documents README as source of truth; no hardcoded copies |
| DESIGN.md token changes break case-study styling | Low | CSS variables are self-contained copies, not imports; document dependency |
| Wiki personal data leaks into case study | Low | Content extracted manually from decision docs only; profile references explicitly excluded |

## Rollback Plan

Delete `case-study/` folder. Zero impact on existing app, CI, or deployment.

## Dependencies

- None. Pure static HTML/CSS with zero build requirements.

## Success Criteria

- [ ] `case-study/index.html` opens via `file://` double-click and displays correctly
- [ ] `case-study/index.html` serves via `python -m http.server` without errors
- [ ] Architecture SVG renders inline (no external image requests)
- [ ] All metrics match README.md exactly (9 rules, 337 tests, 23 endpoints)
- [ ] No external CDN calls (fonts use system stack, icons are inline SVG)
- [ ] CI pipeline (`ci.yml`) remains unchanged and passes
- [ ] Spanish version (`es.html`) has equivalent content and structure
