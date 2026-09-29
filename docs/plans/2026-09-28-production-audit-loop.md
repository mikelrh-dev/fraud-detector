# Production Readiness Audit — No-Docker Loop

**Date:** 2026-09-28
**Constraint:** Docker is down. The API cannot run, no browser, no live database.
**Deliverable this plan can produce:** (1) everything demonstrably wrong, each with a
failing reproduction; (2) the exact list of what remains unprovable and what would
prove it.
**Deliverable this plan must NOT produce:** a "ready for production" verdict. That
requires a running system and is not available here.

## The loop unit

One hypothesis at a time. Never report a finding without a failing reproduction.

```
1. Assert something that could be wrong
2. Try to kill it: write the probe, break the subject, read the call site
3. Record CONFIRMED (failing repro) | REFUTED (what killed it) | UNVERIFIABLE (what it needs)
4. Next
```

**Convergence:** a full sweep that yields zero new findings. The previous audit took
three sweeps and produced 7 findings and 6 refutations, so the first sweep is never
the last.

## Domains, ordered by what this environment can actually reach

| # | Domain | Lever | Reaches? |
|---|---|---|---|
| D1 | Are the tests load-bearing | Mutation | Yes, fully |
| D2 | Backend correctness — money, NaN, transactions, soft delete | Read + probe | Mostly |
| D3 | Security — injection, authz, secrets, tenant isolation | Read + probe | Partly |
| D4 | Async / concurrency | Static forensics | Weakly — smells only |
| D5 | Migrations reversible | Read | Yes |
| D6 | Frontend contracts + the unverified visual change | Read + tsc | Partly |
| D7 | ML layer + the unwired capability | Read + probe | Partly |
| D8 | Comparative vs `origin/master` (44829d2) | Diff | Yes, fully |

## Baselines to preserve

pytest 1018 pass / 8 xfail / 0 fail · ruff clean · mypy clean 69 files ·
frontend tsc clean · 745 vitest pass · CSS 66,681 B (`e4340392…`) baseline plus the
report redesign's +1,025 B.

## Rules

- A claim with no failing reproduction is a hypothesis, not a finding.
- Refutations are recorded with equal prominence. The previous audit's six
  refutations were more informative than any of its seven findings.
- Anything needing a runtime is recorded UNVERIFIABLE with the exact command that
  would settle it, so the list doubles as the manual test script.
- **The report redesign (`a657c53`) has not been looked at.** It enters this audit
  as UNVERIFIABLE, not as approved.
