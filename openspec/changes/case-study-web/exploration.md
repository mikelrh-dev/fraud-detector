# Exploration: case-study-web

## Current State

The fraud-detector project is a complete hybrid fraud detection system (rules + ML + LLM) with a polished React 19 frontend, 337 tests, and a well-documented README in English and Spanish. The project has no standalone portfolio/case-study page. The README serves as both developer docs and portfolio overview, but cannot tell the "decision story" — WHY architectural choices were made, what was rejected, and what was learned. That narrative lives scattered across wiki/ (gitignored), openspec/ changes, and inline README sections.

## Affected Areas

- **`DESIGN.md`** — source of truth for visual tokens (colors, typography, spacing, components). Self-contained and sufficient for building a standalone static page without any framework dependency.
- **`README.md` / `README.es.md`** — verified metrics (9 rules, 337 tests, 23 endpoints, ensemble formula), architecture diagram, design decisions section. Content-ready for extraction.
- **`wiki/decisions/fraud-detector-3-layer-architecture.md`** — portfolio-grade decision doc with alternatives considered, rejected approaches, and rationale. Contains 4 rejected alternatives with clear pros/cons.
- **`wiki/projects/fraud-detector.md`** — project overview with metrics table, outcomes, and role description. Contains personal data (profile references) that must NOT leak into the case study.
- **`openspec/changes/`** — 7 completed changes, each with proposal.md containing decision rationale:
  - `three-layer-fraud-detection` — foundational architecture decision
  - `event-driven-redis-streams` — why Streams over lists (rejected alternatives documented)
  - `shap-feature-attribution` — XAI decision, snapshot vs recalc tradeoff
  - `redis-velocity-features` — Redis offload from Postgres, fallback strategy
  - `restrictive-merchant-blacklist` — category vs name matching
  - `scoring-breakdown-in-responses` — API response shape design
  - `transaction-creation-flow` — frontend architecture, DESIGN.md alignment
- **`docker/nginx.conf`** — SPA routing + API proxy pattern, static asset caching headers. Reusable for case-study deployment.
- **`docker-compose.yml`** — 8 services, Oracle Free Tier RAM limits mentioned in proposal risk tables.
- **`.github/workflows/ci.yml`** — builds `frontend/` only (working-directory: ./frontend). A new static folder at repo root would NOT be picked up by CI. No CI impact.

## Approaches

### 1. Top-level `case-study/` folder (recommended)

- **Pros**: Clean separation from app code; CI ignores it (CI only builds frontend/); easy to deploy independently (just the folder); clear intent in repo structure
- **Cons**: None significant — static HTML/CSS has zero build dependencies
- **Effort**: Low

### 2. `docs/case-study/` nested under docs/

- **Pros**: Groups with documentation
- **Cons**: `docs/` directory already exists but has no clear convention; may confuse with API docs or guides; harder to deploy as standalone static site
- **Effort**: Low

### 3. Standalone repo

- **Pros**: Completely independent deployment
- **Cons**: Loses proximity to source material (README, DESIGN.md, openspec); duplication risk; overkill for a single page
- **Effort**: Medium

## Recommendation

**Approach 1: `case-study/` top-level folder.** Reasons:
- CI safety: `.github/workflows/ci.yml` only touches `frontend/` and `src/` — a `case-study/` folder is invisible to CI
- Gitignore: no conflict — `wiki/` is gitignored but case study content is derived, not copied
- Deployment: the folder can be served by any static host (nginx, GitHub Pages, VPS) with zero config
- DESIGN.md tokens are reusable: extract hex values, font stack, spacing into plain CSS variables (no Tailwind dependency needed for a static page)

## Key Findings

1. **DESIGN.md is self-contained**: All hex values, font families, spacing units, component specs, and Tailwind @theme tokens are documented. A static HTML+CSS page can inherit brand consistency without any build tooling. The CSS variable block at the bottom of DESIGN.md provides exact values for `--color-*`, `--spacing-*` tokens.

2. **Content is rich and ready**: README.md has verified metrics (9 rules, 337 tests, 23 endpoints, ensemble formula, 8 services). Wiki decision doc has 4 rejected alternatives with clear rationale. Openspec proposals contain additional decision stories (Redis Streams over lists, SHAP snapshot vs recalc, category vs name matching).

3. **Wiki content has personal data**: `wiki/projects/fraud-detector.md` references `profile/mikel.md` and contains TODOs asking for personal info. The case study must extract ONLY technical/project content, never copy wiki files directly. The decision doc (`fraud-detector-3-layer-architecture.md`) is clean — no personal data.

4. **CI is safe**: The workflow only runs `frontend/` lint/test/build and `src/` lint/test. A new static folder at root is completely ignored.

5. **Deployment evidence**: `OPERATIONAL_GUIDE.md` has a "SIGUIENTE PASO: DEPLOY A VPS" section with generic Docker deploy commands. `docker/nginx.conf` handles SPA routing for the app. No evidence of a specific Oracle VPS domain or nginx reverse-proxy config for external hosting — the user would need to provide that. The `three-layer-fraud-detection` proposal mentions "Oracle Free Tier (24GB)" in the risk table, confirming the VPS exists.

6. **No screenshots exist in repo**: The demo runs locally (localhost:3000). Screenshots would need the app running. The case study could use placeholder images or a "live demo" CTA instead.

## Open Questions for Proposal Phase

1. **Language**: English only? Spanish only? Bilingual with toggle? (README has both versions — bilingual is feasible but doubles content maintenance)
2. **Deployment target**: Oracle VPS (already hosts another project per user) vs GitHub Pages? VPS allows custom domain; GitHub Pages is free but subdomain-only.
3. **Screenshots**: Include real screenshots (requires running demo + screenshot tooling)? Or use architecture diagrams + code snippets only?
4. **Custom domain**: Does the user have a domain to use? Or subdomain on existing VPS domain?
5. **Dark-only vs light section**: DESIGN.md is dark-first. Should the case study follow the same dark theme, or include a light section for contrast/readability?
6. **Scope of "3 key decisions"**: Which 3? Candidates:
   - 3-layer ensemble (rules + ML + context, LLM outside scoring)
   - Redis Streams over lists (consumer groups, XAUTOCLAIM, DLQ)
   - SHAP explainability (snapshot vs recalc, async worker)
   - XGBoost over Isolation Forest (supervised + TreeExplainer)
   - LLM explains but never decides (separation of concerns)

## Risks

1. **Content duplication / drift**: README metrics and case study metrics must stay in sync. If the project grows (more tests, more endpoints), the case study becomes stale. Mitigation: reference README as source of truth, not copy numbers.
2. **Personal data leakage**: Wiki files contain profile references and personal opinions. The case study must NEVER copy wiki content verbatim — only extract technical facts. Mitigation: explicitly define what's portable (architecture decisions, metrics) vs what's not (personal reflections, profile data).
3. **CI pipeline**: Zero risk — `ci.yml` does not touch `case-study/`. Verified by reading the workflow file.
4. **DESIGN.md token drift**: If DESIGN.md tokens change (e.g., new color added), the static CSS in case-study won't auto-update. Mitigation: document the dependency and keep token references minimal (copy hex values, don't import).
5. **Deployment friction**: If deploying to VPS, the user needs to configure nginx to serve the static folder. The existing `docker/nginx.conf` is for the app, not the case study. A separate nginx server block or GitHub Pages would be needed.
