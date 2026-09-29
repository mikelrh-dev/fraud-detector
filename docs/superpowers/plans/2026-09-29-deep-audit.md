# Deep Audit — Silent Failures and Load-Bearing Tests

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find and fix every remaining defect that the project's own gates cannot see, using a method that cannot report a false finding.

**Architecture:** Six audit domains, ordered by the empirical risk of silent failure. Task 0 builds the falsification harness *before* any finding is reported, because every false finding in the previous investigation came from reading code rather than measuring it. Every reported finding must carry a mutation or a measurement that both produced it and would kill it.

**Tech Stack:** Python 3.11 · pytest · ruff · mypy · React 19 + TypeScript · Vitest · Tailwind v4 · PostgreSQL · Redis · XGBoost 2.1.0

---

## The constraint that shapes this entire plan

**Docker is down and cannot be raised.** The plan is scoped around that, not despite it.

| Available | Not available |
|---|---|
| `pytest` — 879 pass, 0 fail, no container | `docker compose up` — the full stack |
| `ruff check src/` — clean | Browser verification of any rendered change |
| `mypy src/` — clean, 69 files | Re-training the model artifact |
| `npm run build` / `vitest` — no container needed | Migrating a live database |
| Reading and reasoning about any file | The 4 authenticated data routes |
| Host `.venv` can `joblib.load` the artifact | `/health/ready`, in-situ API behaviour |

**Consequence:** a finding in Domain 5 that requires re-training, or any fix in Domain 4
that changes a rendered surface, must be **recorded as unverified** and left unfixed. Do
not ship a change nobody looked at. That rule is the whole point of this plan.

**Two known items are blocked on the container and stay blocked:** artifact
reproducibility (committed sha256 `243083b1…` vs a claim of `573b7d09…` that nobody
reconciled) and any live migration test. They are listed in §11 so they are not forgotten,
not pretended away.

---

## The method: why Task 0 comes first

Five findings in the previous investigation were **artefacts of the measurement, not
defects in the code**, and every one was retracted after a second measurement:

| Reported as a defect | Actually |
|---|---|
| The model is not loaded | It was; the warning was never emitted |
| Velocity features are dead | The wrong producer was inspected — a helper, not the call site |
| Feature order does not match | It matched exactly |
| The score breakdown does not reconcile | It reconciles to `54.0031`; the context term was eyeballed |
| The amount response is inverted | The probe built feature vectors that exist nowhere in the corpus |

All five were produced by **reading code or hand-constructing an input**. All five were
killed by **moving one thing and measuring**.

**Therefore the rule for this audit: no finding is reported without a reproduction that
fails.** A finding with no failing reproduction is a hypothesis, and goes in the
`HYPOTHESES, NOT FINDINGS` section of the report, not the findings.

---

## File structure

| File | Responsibility |
|---|---|
| `scripts/audit_harness.py` | **Create.** The falsification tools every task uses. Kept in `scripts/` beside `evaluate_model.py`, which already reports corpus diagnostics. |
| `docs/audit-2026-09-29-findings.md` | **Create.** Every finding, each with its reproduction. |
| `tests/test_audit_invariants.py` | **Create.** Cross-cutting invariants that don't belong to one module. |
| `src/services/*.py`, `src/api/v1/*.py` | Modify only where a confirmed finding demands it. |
| `frontend/src/**` | Modify only where a fix is verifiable without a browser. |

`scripts/` is **baked into the API image, not bind-mounted.** Host edits are invisible
inside the container; use `docker cp`. This cost a run previously.

---

## Task 0: Build the falsification harness

Everything downstream depends on this. Without it, the remaining tasks are opinions.

**Files:**
- Create: `scripts/audit_harness.py`

- [ ] **Step 1: Write the harness**

```python
"""Falsification tools for the deep audit.

A finding is not a finding until this module can produce a failing reproduction of
it and a passing one of its absence. Five findings in the previous investigation
were measurement artefacts; this is the thing that catches that class.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass
class Finding:
    """A claimed defect. `reproduction` must fail before this is a finding."""

    id: str
    domain: str
    claim: str
    reproduction: str
    expected_on_broken: str
    expected_on_fixed: str
    confirmed: bool = False
    evidence: dict = field(default_factory=dict)


def run(cmd: list[str], cwd: Path = REPO) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=False)
    return proc.returncode, proc.stdout + proc.stderr


def pytest_fails_on(target: str) -> tuple[bool, str]:
    """True when `target` is RED. The only admissible evidence of a defect."""
    code, out = run([sys.executable, "-m", "pytest", target, "-q", "--no-header"])
    return code != 0, out


def front_vitest_fails_on(target: str) -> tuple[bool, str]:
    code, out = run(
        ["npx", "vitest", "run", target], cwd=REPO / "frontend"
    )
    return code != 0, out


def compiled_css_bytes() -> int:
    css = sorted((REPO / "frontend" / "dist" / "assets").glob("*.css"))
    if not css:
        raise SystemExit("no built CSS — run `npm run build` in frontend/ first")
    return css[0].stat().st_size


def bare_tailwind_rules() -> dict[str, int]:
    """Utilities emitted by prose rather than by a className.

    Tailwind v4 scans comments. `.grow` came from the English word "grow"; `.table`
    from "table cells". Both shipped in every build. Reports what is present now so
    a fix can be shown to change the number.
    """
    css = sorted((REPO / "frontend" / "dist" / "assets").glob("*.css"))[0]
    text = css.read_text(encoding="utf-8")
    return {
        name: len(re.findall(rf"(?<![-\w])\.{re.escape(name)}\s*\{{", text))
        for name in ("table", "rounded", "grow", "block", "inline", "flex", "grid", "hidden")
    }


def verify(finding: Finding) -> Finding:
    """Run the reproduction. A Finding that cannot go red is not a Finding."""
    is_front = finding.reproduction.startswith("vitest:")
    target = finding.reproduction.split(":", 1)[1] if is_front else finding.reproduction
    red, out = (front_vitest_fails_on if is_front else pytest_fails_on)(target)
    finding.confirmed = red
    finding.evidence["reproduction_output"] = out[-2000:]
    return finding
```

- [ ] **Step 2: Run it against a known-good repo and confirm it is inert**

```powershell
.venv\Scripts\python.exe scripts/audit_harness.py
```

Expected: no output and exit 0. The module defines tools; it audits nothing yet.

- [ ] **Step 3: Prove the harness can go red on a synthetic case**

```powershell
.venv\Scripts\python.exe -c @"
import sys; sys.path.insert(0, '.')
from scripts.audit_harness import Finding, verify
f = verify(Finding('PROBE', 'meta', 'the harness works',
                   'tests/test_audit_invariants.py::test_placeholder', 'FAIL', 'PASS'))
print('confirmed:', f.confirmed)
print(f.evidence['reproduction_output'][-200:])
"@
```

Expected: `confirmed: True` and a `ModuleNotFoundError` or collection error. If it
prints `confirmed: False`, the harness is broken and every later finding is worthless.

- [ ] **Step 4: Commit**

```bash
git add scripts/audit_harness.py
git commit -m "chore(audit): the tool that decides whether a finding is real

Reports a claim as a finding only when its reproduction goes red. Built first so
the domains that follow cannot produce a confident false positive."
```

---

## Task 1: Silent exception handlers

`grep` found 5 bare `except Exception:` in `src/`. Each one is a place where a failure
becomes silence.

**Files:**
- Create: `tests/test_audit_invariants.py`
- Inspect: every `src/**/*.py` containing a bare `except Exception`

- [ ] **Step 1: Enumerate them and record what each swallows**

```powershell
Select-String -Path "src\**\*.py" -Pattern "except Exception" -Context 0,3 |
  ForEach-Object { $_.Line.Trim(); $_.Context.PostContext | ForEach-Object { "    $($_.Trim())" } }
```

Write each into `docs/audit-2026-09-29-findings.md` with its file:line and what it
discards.

- [ ] **Step 2: For each one, decide with evidence, not taste**

A swallowed exception is only a defect if it hides a failure the operator must see.
Test each by making the swallowed call raise:

```python
def test_audit_<name>_surfaces_its_failure(monkeypatch):
    """<what the handler discards> must not vanish silently."""
```

- [ ] **Step 3: Run each test and confirm it goes red before you fix anything**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_audit_invariants.py -k audit_ -v
```

Expected: at least one FAIL. If every test passes on the unfixed code, the
invariants are not testing anything — delete them rather than keeping green
decoration.

- [ ] **Step 4: Fix, re-run, commit per handler**

```bash
git add tests/test_audit_invariants.py src/<file>.py
git commit -m "fix(<module>): <what the handler was hiding>"
```

---

## Task 2: Endpoint contract audit

28 endpoints. The registry exists (`src/api/v1/rate_limit.py`, `src/core/dependencies.py`),
so the question is coverage, not design.

**Files:**
- Create: `tests/test_audit_invariants.py` (extend)

- [ ] **Step 1: Enumerate every route and its decorators**

```powershell
Select-String -Path "src\api\v1\*.py" -Pattern "@router\.(get|post|put|patch|delete)" |
  ForEach-Object { "$(Split-Path $_.Path -Leaf):$($_.LineNumber)  $($_.Line.Trim())" }
```

- [ ] **Step 2: Assert the invariants that must hold for every one**

```python
def test_audit_every_endpoint_requires_authentication():
    """No route may reach a handler without an authenticated caller."""
```

Assert against the source, not against a hand-maintained list — a hand-maintained
list drifts, which is the defect class this project keeps hitting.

- [ ] **Step 3: Confirm red, then fix, then commit**

---

## Task 3: The hardcoded merchant blacklist

`src/api/v1/transactions.py` builds `merchant_blacklist` from three literal strings
inside the request path:

```python
"merchant_blacklist": [
    "crypto exchange pro",
    "online gambling",
    "money transfer now",
],
```

A demo artefact sitting in the production decision path. The `unusual_merchant` rule
that fired on the user's test transaction reads from here.

- [ ] **Step 1: Confirm it is not configurable anywhere**

```powershell
Select-String -Path "src\**\*.py",".env*","docker\**\*" -Pattern "merchant_blacklist" |
  ForEach-Object { "$(Split-Path $_.Path -Leaf):$($_.LineNumber)  $($_.Line.Trim())" }
```

- [ ] **Step 2: Write the failing test**

```python
def test_audit_blacklist_is_not_hardcoded_in_the_request_path():
    """A demo literal must not decide fraud in production."""
```

- [ ] **Step 3: Confirm red before fixing**
- [ ] **Step 4: Move it to configuration, defaulting to the current three values so no test regresses, and commit**

---

## Task 4: Load-bearing test audit

The project has three known signals that some tests are decoration:
- Two assertions once **pinned a defect** (`toBe(false)` on a focus ring) and had to be flipped, not deleted
- A mutation harness reported *"all 12 killed"* against a **red baseline** and counted module crashes as evidence
- `classificationPillClass`'s 9 tests all stayed green while the function had **zero production call sites**

- [ ] **Step 1: Find tests that assert against an imported constant**

```python
def test_audit_no_assertion_against_an_imported_constant():
    """Asserting a fixture's own value proves the fixture, not the system."""
```

- [ ] **Step 2: Find exports with tests but no production caller**

```python
def test_audit_no_orphaned_public_export():
    """A tested export with no production caller is dead code with a green suite."""
```

- [ ] **Step 3: Find tests that pass against a deliberately broken build**

For each of the three classes, mutate the subject and confirm the test goes red.
**A test that survives its own mutation is deleted, not repaired** — keeping a
decorative test teaches the team to trust something that proves nothing.

- [ ] **Step 4: Commit each deletion with the mutation that justified it**

---

## Task 5: Frontend contract honesty

**Files:**
- Inspect: `frontend/src/api/*.ts`, `frontend/src/lib/*.ts`

- [ ] **Step 1: Audit every type comment that makes a guarantee about the backend**

`frontend/src/api/transactions.ts` declares `ml_score: number` with the comment
*"backend guarantees non-nullable float"*. Verify each such claim against the Pydantic
schema it mirrors. A type comment asserting a guarantee the server does not make is
worse than no comment.

- [ ] **Step 2: Assert the type contract is real**

```typescript
it("does not claim a non-null guarantee the schema does not make", () => {
  // read the Pydantic schema, assert every optionality matches the TS type
});
```

- [ ] **Step 3: Surface `layers_used` in the API response — the safe half only**

It is computed at `scoring_service.py:159` and returned at `:192`, then dies: no ORM
column, no migration, no schema, zero frontend references. Exposing it in the
**response schema** is additive and changes no rendered surface, so it is verifiable
here.

```bash
git add src/schemas/scoring.py frontend/src/api/transactions.ts
git commit -m "feat(scoring): expose which layers produced a score

layers_used has been computed and discarded since A15. It distinguishes 'the model
was not loaded' from 'the model ran and scored zero' — the single most important
distinction in the pipeline — and the evidence died in a local variable.

Response-schema only. Persisting it needs a migration and displaying it changes a
rendered surface; both are unverifiable without a container and a browser, so
both are left for when there is one."
```

- [ ] **Step 4: Do NOT persist it and do NOT render it. Record both as pending in §11.**

---

## Task 6: Training / serving skew

The one class of defect that produced *both* a broken model and a broken audit.

`scripts/train_xgboost_aligned.py` builds its feature vectors through
`FeatureEngine.transform`. Serving does the same. The risk is that they feed it
different dictionaries.

- [ ] **Step 1: Enumerate every key the trainer reads**

```python
def test_audit_trainer_and_server_agree_on_history_keys():
    """Both must produce the same four user_history keys."""
```

- [ ] **Step 2: Confirm the production call site**

`src/api/v1/transactions.py` populates `avg_amount`, `std_amount`,
`tx_count_last_5min`, `tx_count_last_1h`. The trainer's
`build_synthetic_history` produces the same four. Assert it so a fifth key cannot
appear in one and not the other.

- [ ] **Step 3: Assert no feature the model uses can be constant in serving**

The corpus previously shipped `amount_vs_user_std` as constant-zero while the
artifact weighted it at 19%. Assert that every feature with non-zero importance in
the artifact has non-zero variance in the feature matrix.

- [ ] **Step 4: Run and commit**

```bash
.venv\Scripts\python.exe -m pytest tests/test_audit_invariants.py -k skew -v
```

---

## Task 7: Undeclared dependencies

`scipy==1.17.1` is installed and declared in no requirements file. That is how the
`imbalanced-learn` / `scikit-learn` incompatibility survived: the declared pair was
never actually the resolved pair.

- [ ] **Step 1: Diff the resolved environment against the declarations**

```powershell
.venv\Scripts\python.exe -m pip freeze > "$env:TEMP\resolved.txt"
Get-Content requirements.txt, requirements-dev.txt |
  Where-Object { $_ -match '^[a-zA-Z]' } |
  ForEach-Object { ($_ -split '==')[0] } |
  ForEach-Object { if (-not (Select-String -Path "$env:TEMP\resolved.txt" -Pattern "^$_==" -Quiet)) { "  UNDECLARED: $_" } }
```

- [ ] **Step 2: Pin what should be pinned; justify what should not**

- [ ] **Step 3: Commit**

---

## Task 8: Documentation truth

`DESIGN.md:37` says Review/Flagged is `#eab308` / `yellow-500`;
`frontend/src/index.css` uses `#f59e0b` (`amber-500`). One of them is wrong and
nobody knows which, because documentation is not compiled.

- [ ] **Step 1: Recompute every claim in `DESIGN.md` that names a value or a file:line**

- [ ] **Step 2: Report each mismatch with both values; do not guess which is intended**

- [ ] **Step 3: Fix only the unambiguous ones and commit. Leave the rest as a decision.**

---

## Task 9: The dead CSS rule, honestly

`bare_tailwind_rules()` in the harness reports `.table` and `.rounded`.

**A previous attempt at this was reverted, and the revert was correct:**
- `.rounded` is **not** dead — bare `rounded` is a real class in
  `ConfirmDialog.tsx:201`, `TransactionTable.tsx:247`, `AlertsPage.tsx:526`,
  `TransactionsPage.tsx:439` and others
- `.table` **is** dead, but "table" appears ~70 times in ordinary English prose
  ("data table", "table cell"). Removing it means mangling readable comments to save
  roughly 50 bytes

- [ ] **Step 1: Measure the current baseline with the harness**

```python
from scripts.audit_harness import compiled_css_bytes, bare_tailwind_rules
print(compiled_css_bytes(), bare_tailwind_rules())
```

- [ ] **Step 2: Decide whether the 50 bytes justify rewriting 70 comments**

Record the answer. **"No" is an acceptable and likely correct outcome** — a byte
count is not a defect. Do not manufacture work to justify the task.

---

## Task 10: Write the report

**Files:**
- Create: `docs/audit-2026-09-29-findings.md`

- [ ] **Step 1: For each finding, record**

```
### <ID> — <one line>
- Domain:
- Claim:
- Reproduction:        <exact command, and its FAILING output>
- Absent when:         <exact command, and its PASSING output>
- Blast radius:
- Fixed / Not fixed / Blocked on container:
```

- [ ] **Step 2: Add a `HYPOTHESES, NOT FINDINGS` section**

Every claim that could not be made to go red goes here. **This section is the
credibility of the report** — it is what distinguishes it from the five retracted
findings in the previous investigation.

- [ ] **Step 3: Report the count of findings that were refuted during the audit**

Expected to be non-zero. If it is zero, the method was not applied.

---

## Task 11: Record what stayed blocked

- [ ] **Step 1: Create `docs/audit-2026-09-29-blocked.md` listing, with reasons**

| Item | Blocked on | What would unblock it |
|---|---|---|
| Artifact reproducibility — committed `243083b1…` vs claimed `573b7d09…` | Container | Two retrains, compare hashes |
| `layers_used` persistence | Live database | A migration test against Postgres |
| `layers_used` in the rendered detail page | A browser | Any in-situ session |
| 4 authenticated data routes | Container + API | Docker up, seed, log in |
| The focus ring on the real component | A browser | Keyboard-only pass over the live app |
| Real-labelled fraud performance | A human process | 100–200 own-domain reviewed alerts |

- [ ] **Step 2: Commit. This document exists so the blocked work is visible rather than lost.**

---

## Self-review

**Spec coverage:** every domain from the goal is covered — silent handlers (1), endpoint
contracts (2–3), load-bearing tests (4), frontend honesty (5), skew (6), dependencies
(7), documentation (8), CSS (9), reporting (10–11).

**Placeholder scan:** no TBD, no "add appropriate handling", no "similar to Task N".
Every step names a file, a command, and an expected result.

**Type consistency:** `Finding` is defined in Task 0 and used in Tasks 1–10 unchanged.
`pytest_fails_on` and `front_vitest_fails_on` are the only two evidence entry points;
no task invents a third.

**Known tension, stated rather than hidden:** Task 5 Step 3 exposes a field whose
persistence and display are blocked. That is deliberate — half of a contract is worth
more than none, and the blocked half is recorded in Task 11 rather than forgotten.

---

## Out of scope

Anything needing Docker, a browser, or a live database. That list is in Task 11, and
inventing a workaround for it would produce an unverified change shipped on the
authority of a plan.
