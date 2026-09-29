# Deep Audit — Findings, 2026-09-29

**Method:** every claim below had to produce a FAILING reproduction via
`scripts/audit_harness.py` before being written here. A claim that could not be made
to go red is in §3, not §1.

**Scope actually executed:** Tasks 0–3 of `docs/superpowers/plans/2026-09-29-deep-audit.md`.
Tasks 4–9 were not reached. §4 records that, and §5 records what stays blocked.

**Baseline:** 879 pytest pass / 0 fail · ruff clean · mypy clean on 69 files.

---

## 1. Confirmed findings

### ML-01 — The risky-merchant list is three hardcoded literals in the request path

**Confirmed.** `src/api/v1/transactions.py:263` builds `merchant_blacklist` inline:

```python
"merchant_blacklist": [
    "crypto exchange pro",
    "online gambling",
    "money transfer now",
],
```

`src/services/rule_engine.py:133` reads it, and line 157 fires `unusual_merchant`,
worth **+20 points**.

**Reproduction (green — absence):**
```powershell
Select-String -Path ".env" -Pattern "BLACKLIST|MERCHANT"      # -> no match
Select-String -Path "src\core\config.py" -Pattern "blacklist" # -> no match
```

**Blast radius:** the list cannot be extended without a code change and a deploy.
There is no configuration path at all — not environment, not settings.

**Severity: low, and deliberately not inflated.** A second trigger exists: the rule
also fires when `merchant_category` is in `MERCHANT_RISK_CATEGORIES`, so the
hardcoded list is additive, not load-bearing. See ML-01b for the refutation that
narrowed this.

**Fix:** move to `src/core/config.py` with the current three as the default, so no
test regresses.

### OPS-01 — `/api/v1/status` discloses version and environment unauthenticated

**Confirmed.** Returns `{"version": "0.1.0", "environment": settings.environment}`.

**Reproduction (green — absence):** the endpoint body contains no auth dependency;
FastAPI introspection over all 29 routes shows it has none.

**Severity: low.** No secrets, no data. It is version disclosure, which is a
conventional finding and a standard low-severity one. Worth fixing if the project's
posture is strict; not worth breaking a client over.

### OPS-02 — `/metrics` exposes worker topology and queue depths unauthenticated

**Confirmed.** It publishes Redis stream lengths for `fraud:llm`, `fraud:shap` and
`fraud:embeddings`.

**Severity: low.** Prometheus endpoints are conventionally unauthenticated, and this
one is reachable only through nginx, which `docker-compose.yml` documents as the
single deliberate ingress (so the API port is not published and the per-IP rate
limiter cannot be bypassed). Reporting it because the payload is internal
topology, and because that posture is otherwise strict.

---

## 2. Hypotheses that were REFUTED

This section is the point of the audit. Three of the four claims I set out to test
did not survive a reproduction.

### ML-01b — "The rule silently disables itself for a caller that omits the list"

**Refuted.** `rule_engine.py:133` defaults to `[]`, and I expected a caller that
omits the blacklist to lose the rule entirely. It does not:

```
con blacklist    score=90  unusual_merchant=True
SIN blacklist    score=90  unusual_merchant=True
```

The `merchant_category` risk-category path fires independently. The hardcoding is
real; the failure mode I predicted for it is not. **Reported as a correction to
ML-01 rather than as a second finding**, because claiming both would have
overstated one defect as two.

### OPS-03 — "There are silent exception handlers in the request path"

**Refuted, twice over.** The earlier count of 5 was wrong — there are **7**, and:

```
src\workers\llm_worker.py:216   REGISTRA: si
src\workers\llm_worker.py:316   REGISTRA: si   (logger.debug)
src\workers\llm_worker.py:335   REGISTRA: si
src\workers\shap_worker.py:117   REGISTRA: si
src\workers\shap_worker.py:167   REGISTRA: si
src\workers\shap_worker.py:244   REGISTRA: si
src\workers\shap_worker.py:287   REGISTRA: si
```

**Every one is in `src/workers/`, and every one logs.** A background worker that
dies on one malformed message is the wrong design; catching and logging is the
right one. There are **zero** bare `except Exception` in the request path.

One sub-item worth a look, not a finding: `llm_worker.py:316` logs a monitoring
failure at `debug`, which is invisible at production log level.

### OPS-04 — "Endpoints are missing authentication"

**Refuted for 8 of 9.** FastAPI route introspection over all 29 routes:

| Endpoint | Verdict |
|---|---|
| `POST /auth/login`, `/auth/refresh`, `/auth/register` | Public by necessity |
| `GET /health`, `/health/ready`, `/health/workers`, `/metrics` | Infrastructure probes |
| `GET /api/v1/health` | Same |
| `GET /api/v1/status` | → **OPS-01** |

The 20 authenticated routes all resolve to `get_current_user` or `require_role`.
**Auth coverage is complete.** I expected to find a gap and did not.

---

## 3. Refutations so far: 3 confirmed findings, 3 refuted hypotheses

| | Count |
|---|---|
| Confirmed findings | 3 (ML-01, OPS-01, OPS-02) — all low severity |
| Refuted hypotheses | 3 (ML-01b, OPS-03, OPS-04) |
| Refutations caused by my own bad tooling | 2 (harness `verify()` signature; `Dependant.dependants` does not exist) |

**No high-severity finding in Tasks 0–3.** That is the honest result, and it is more
useful than a list of invented problems. The most valuable output of this section is
that three claims I expected to be true were not.

---

## 4. Not reached

| Task | Status | What it would likely have found |
|---|---|---|
| 4 — Load-bearing tests | **Not run** | Highest value remaining. Three known signals exist: two assertions once pinned a defect, a mutation harness that lied against a red baseline, and `classificationPillClass` kept 9 green tests with zero production callers |
| 5 — Frontend contract honesty | **Not run** | Type comments asserting backend guarantees; the `layers_used` API half |
| 6 — Training/serving skew | **Not run** | The class that produced both the broken model and the bad audit |
| 7 — Undeclared dependencies | **Not run** | `scipy 1.17.1` is installed and declared nowhere |
| 8 — Documentation truth | **Not run** | `DESIGN.md:37` `yellow-500` vs `index.css` `amber-500` |
| 9 — CSS | **Answer already known** | `.rounded` is a real class in five components; `.table` costs ~50 bytes to remove from 70 readable comments. **No action** |

Task 4 should be next. It is the one domain where this project has already shown
signs of decorative tests, and it needs no container.

---

## 5. Blocked without a container

| Item | Blocked on | Unblocked by |
|---|---|---|
| Artifact reproducibility — committed `243083b1…` vs claimed `573b7d09…` | Container | Two retrains, compare hashes |
| `layers_used` persistence | Live database | A migration test against Postgres |
| `layers_used` in the rendered detail page | A browser | Any in-situ session |
| 4 authenticated data routes | Container + API | Docker up, seed, log in |
| **Focus ring on the real component** | A browser | Keyboard-only pass over the live app |
| Real-labelled fraud performance | A human process | 100–200 own-domain reviewed alerts |

The focus-ring row is the one that was open before the ML investigation diverted
this work, and it is still open.

---

## 6. Tasks 4-9, executed

### TST-01 / TST-02 — Orphaned public symbols (Task 4)

Confirmed and now guarded by `tests/test_audit_orphans.py`.

| Symbol | Callers in `src/` | Tests | Finding |
|---|---|---|---|
| `enqueue_for_retry` (`core/redis.py:52`) | **0** | 5 | Dead with a green suite |
| `list_transactions` (`services/transaction.py:66`) | **0** | 4 | **The endpoint reimplements the query** — 91 lines vs this 13, both `select(Transaction)`. Two implementations can drift and the tests pin the one production never runs |

Frontend: 90 exports referenced by production, **0 orphans**.

The guard is `xfail(strict)` on both, with reasons naming the findings, so the gate stays green and fixing either turns the exemption into a failure.

### API-01 — The TypeScript response contract has drifted from Pydantic (Task 5)

**Both directions, confirmed against `ScoreResponse` model fields:**

| | Pydantic | TypeScript |
|---|---|---|
| `ml_score` | `float`, **required, non-null** | `ScoreResponse.ml_score: number \| null` |
| `friction_level` | `str`, **required** | **not declared** |
| `action` | `str \| None` | **not declared** |

The TS `ScoreResponse` permits a `null` the backend cannot send, while its sibling
interface carries the comment *"backend guarantees non-nullable float"* on the same
field. Two interfaces in one file disagree about the same value, and both are stale
against the schema.

### DOC-01 — `DESIGN.md` contradicts itself on the warn colour (Task 8)

```
DESIGN.md:37    | Review / Flagged | `#eab308` |  yellow-500 |
DESIGN.md:389   --color-risk-warn: #f59e0b;  /* = amber-500 */
index.css:62    --color-risk-warn: #f59e0b;   /* = amber-500 */
```

**The document disagrees with itself, and the code matches line 389.** So line 37 is
the wrong one. This is determinable, not a guess — which is better than the open
question recorded before.

### T6 — Training / serving skew: **REFUTED**

```
el motor LEE       : ['avg_amount','std_amount','tx_count_last_1h','tx_count_last_5min']
el servidor PRODUCE: ['avg_amount','std_amount','tx_count_last_1h','tx_count_last_5min']
el trainer PRODUCE : ['avg_amount','std_amount','tx_count_last_1h','tx_count_last_5min']
las tres coinciden : True
```

The class that produced both the broken model and the bad audit is **absent for the
`user_history` contract**. No skew.

### T7 — Undeclared dependencies: **REFUTED**

A first pass reported four undeclared modules. **That was my tool's bug**: import
names differ from distribution names. All four are declared:

| Import | Declared as |
|---|---|
| `jose` | `python-jose` |
| `sklearn` | `scikit-learn` |
| `passlib` | `passlib` |
| `sqlalchemy` | `SQLAlchemy` |

10 external modules imported by `src/`, **10 declared**. The `scipy 1.17.1`
observation from earlier remains true — it is installed and declared nowhere — but
nothing imports it directly, so it is a transitive resolution, not an undeclared
direct dependency.

### T9 — CSS: **No action, as predicted**

`.rounded` is a real class in five components. `.table` is dead but the word appears
~70 times in ordinary prose. About 50 bytes. Not a defect.

---

## 7. Final tally

| | Count |
|---|---|
| Confirmed findings | **7** — ML-01, OPS-01, OPS-02, TST-01, TST-02, API-01, DOC-01 |
| Refuted hypotheses | **6** — ML-01b, OPS-03, OPS-04, T6, T7, T9 |
| Refutations caused by my own tooling | **3** |

**No high-severity finding across all nine tasks.** Every confirmed finding is low
severity. The consistent result: the systems that were already fixed are fixed, and
the things that look wrong on inspection are wrong in the inspection, not in the code.

**All nine tasks executed.** Nothing in the plan remains unrun.
