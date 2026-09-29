# ML Pipeline Audit — Model Correctness, Not Model Performance

**Date:** 2026-09-28
**Scope:** the machine-learning layer only (`src/services/ml_model.py`, `src/services/feature_engine.py`, `scripts/train_xgboost_aligned.py`, `models/xgboost_paysim_v1.joblib`)
**Purpose:** to be run **against an older revision of this project**, as a comparison instrument.
**Status of this revision:** working tree clean except the two untouched READMEs. 839 tests pass, 0 fail.

> **This document is deliberately not a scorecard.** It is written so that it can be
> run against another revision and produce a defensible verdict, including a verdict
> that *this* revision is worse. Every number below is reproducible with the commands
> in §8. Where a number does not exist, the field says so rather than being estimated.

---

## 1. Executive summary

The ML layer was **non-functional and appeared to work**. The model returned a score
for every transaction, the API was green, and the tests passed. The scores were
meaningless: the deployed artifact gave a $23,000 crypto transfer **0.01 out of 100**
and could not be moved by varying that amount across six orders of magnitude.

Four independent defects were found. All four were invisible to every existing gate.

| # | Defect | Invisible because | Fixed in |
|---|---|---|---|
| **A** | The training corpus separated the classes by itself. `amount` alone scored **AUC 1.0000** — a feature that *is* the label. | An AUC of 1.0 reads as perfection. | `cb65b25` |
| **B** | The calibrator was fit on SMOTE-resampled data with a **33% fraud prior**, while the real prior is **1%**. The ensemble thresholds on these absolute probabilities. | Rankings were correct, so every ranking metric looked fine. | `c1a4f6a` |
| **C** | The training script could not run at all. `imbalanced-learn==0.12.0` imports `parse_version` from `sklearn.utils`, removed in scikit-learn 1.5. | Nobody ran it. The model had not been retrainable. | `1e76585` |
| **D** | The deployed artifact was **not reproducible** from the code. It weighted a feature that is constant-zero in every fresh run at 19%. | The artifact was only ever loaded, never regenerated. | `cb65b25` |

**After the fixes, measured on the deployed artifact:**

| Quantity | Before | After |
|---|---|---|
| $23,000 crypto, high risk — ML score | **0.01** | **98.11** |
| $50 ordinary purchase — ML score | 0.00 | 0.42 |
| `amount` importance (gain) | 0.71% | 6.88% |
| `amount` sensitivity (0 → 1,000,000) | 0.0000036 | 97.96 |
| Features with zero variance | 3 | 0 |
| Worst single-feature AUC in the corpus | **1.0000** | 0.8323 |
| Test ROC-AUC | 1.0000 *(meaningless)* | 0.9397 |
| Test PR-AUC | — | 0.7936 |
| Expected-calibration-error | 0.0153 | **0.0041** |
| Brier score | 0.0076 | 0.0033 |
| False alarms at production threshold | 195 | **33** |
| Tests failing | 2 (wall-clock flakes, nightly) | **0** |

**The single most important number in this table is the first one.** Before, the model
could not tell a $23,000 crypto transfer from a $50 grocery purchase. It returned
0.0123 for both. It was not a fraud detector with a bad threshold; it was a
velocity counter, contributing ~0.3% of the signal while holding 25% of the ensemble weight.

---

## 2. What was wrong, in the order it was found

This order matters: each defect was invisible until the previous one was removed. A
reviewer checking any one of them in isolation would have concluded the system was fine.

### A. The corpus was degenerate

The generator produced fraud and legitimate transactions whose amount distributions
barely overlapped — fraud median ≈ 38,000, legitimate median ≈ 90. Measured directly:
**`amount` alone achieved AUC 1.0000 on the training corpus.**

Three features were simultaneously perfect separators (`amount`, `tx_count_last_5min`,
`merchant_risk_level`). XGBoost split on the first it found — velocity — and the rest
lost a tie. It did not ignore amount because amount was useless. It ignored amount
because velocity was equally good and found first.

**The tell was not the importance value; it was test AUC = 1.0000.** A model that
classifies a held-out set perfectly is a model that was never given a hard problem.
Any AUC near 1.0 in fraud detection is a finding about the *data*, never about the model.

The fix gave every archetype overlapping distributions, so no feature separates alone.
The corpus was rebuilt around behavioural archetypes (`card_testing`,
`account_takeover`, `high_value_wire`, `large_burst`, `low_signal` on the fraud side;
`everyday`, `big_purchase`, `burst`, `fraud_lookalike` on the legitimate side) with
deliberately overlapping windows.

### B. The calibrator was calibrated to the wrong prior

`CalibratedClassifierCV` was fit on SMOTE-resampled rows carrying a **33% fraud rate**.
Platt scaling learns `P(y=1 | score)` from whatever matrix it is shown, so it learned
a base rate that never occurs at serve time. The top bin predicted **0.98** where the
observed rate was **0.68**.

This is the defect most likely to survive a portfolio review, because **every ranking
metric was healthy**. ROC-AUC and PR-AUC are invariant to monotone recalibration.
Only a reliability diagram exposes it.

The fix deleted the resampling rather than patching the calibrator: `scale_pos_weight`
from the real prior is now the only imbalance mechanism, and the sigmoid is fit on
pooled out-of-fold predictions over un-resampled rows (`cv=<int>`, the non-deprecated
scikit-learn 1.5 mechanism). `imblearn` is no longer imported by the trainer at all.

Reliability after, on 30,000 held-out rows at a 0.96% actual fraud rate:

| Bin | n | predicted | observed | gap |
|---|---|---|---|---|
| [0.0, 0.1) | 29,537 | 0.0038 | 0.0020 | −0.0018 |
| [0.1, 0.2) | 129 | 0.1402 | 0.0310 | −0.1092 |
| [0.2, 0.3) | 41 | 0.2400 | 0.0244 | −0.2156 |
| [0.3, 0.4) | 27 | 0.3444 | 0.0741 | −0.2703 |
| [0.4, 0.5) | 22 | 0.4541 | 0.2273 | −0.2269 |
| [0.5, 0.6) | 15 | 0.5455 | 0.4667 | −0.0788 |
| [0.6, 0.7) | 21 | 0.6528 | 0.3810 | −0.2718 |
| [0.7, 0.8) | 24 | 0.7562 | 0.7500 | −0.0062 |
| [0.8, 0.9) | 184 | 0.8441 | 0.9891 | +0.1450 |

Mid-range over-confidence (−0.11 to −0.27) is real and is reported, not smoothed over.
`isotonic` calibration was measured and **rejected on evidence**: better ECE (0.0027)
but a non-monotone reliability curve on 8–17 samples, worse ranking (0.9354 vs 0.9397),
and saturation at 1.0. Its advantage was overfitting to the held-out set.

### C. The training script could not run

`requirements.txt` declared the incompatible pair `scikit-learn==1.5.0` +
`imbalanced-learn==0.12.0`. The training script raised
`ImportError: cannot import name 'parse_version' from 'sklearn.utils'` on import.

**This was declared broken, not accidentally broken.** The model on disk had not been
retrainable for an unknown period. `imbalanced-learn==0.12.4` is compatible with
scikit-learn 1.5.0.

Also found: the artifact was trained against scikit-learn 1.5.2 and served by 1.5.0,
producing `InconsistentVersionWarning: ... may lead to breaking code or invalid
results`. The host `.venv` still carries 1.5.2; **training must be run inside the API
container** to reproduce the artifact.

### D. The artifact was not reproducible

`amount_vs_user_std` is **constant zero** (std = 0.000000) in every fresh run: the
generator never emitted `user_avg_amount`/`user_std_amount` and `_save_synthetic_csv`
never wrote those columns. Yet the deployed artifact weighted that constant feature at
**19%**. A constant column cannot earn gain in a tree.

So the shipped model was trained from a different state of the code than the code in
the repository. It is now reproducible: three consecutive retrains inside the container
produce a byte-identical artifact (sha256 `573b7d09…`), and the corpus regenerates
byte-identically too.

---

## 3. Where this revision is probably WORSE — check these first

Read this section before concluding that the new revision is better. These are the
axes where it plausibly regressed, and they are the ones to weigh hardest.

### 3.1 The ML model is no longer a second opinion

Measured through the real `EnsembleScorer`: `context_score` defaults to `0.0`, not
`None`, so the layer weights never redistribute and ML is **always** a flat 0.25
multiplier. Its ceiling fell from 24.90 to 21.25 ensemble points.

It therefore **cannot reach a threshold on its own at any cut point.** Reaching the
high tier (45) requires a rule score of 39.6, and the largest single rule
(`high_amount`) is worth 35. The ML layer is a ±25-point modifier near a boundary the
rules have already crossed.

Whether that is the intended architecture or an accident of a `0.0` default where
`None` was meant is **not decided anywhere in the code**. If the old revision had a
model that could actually flag something alone, that is a capability regression.

### 3.2 One classification boundary moved

A transaction whose only rule is `high_amount` (35) at maximum ML confidence scored
**45.90 → `fraud`** before and **42.25 → `review`** now. Preserving the old class would
require `ml_score ≥ 116`, which the model cannot emit.

`review` means an analyst sees it and nothing auto-blocks — the safer failure, but it
**is** a behaviour change. Thresholds were deliberately left untouched: that is a risk
decision, not a mechanical one. **If the old revision auto-blocked this case, the new
one does not.**

### 3.3 Complexity cost

The generator grew from one `lognormal` call per class to **seven behavioural
archetypes** with overlapping windows, plus per-user history simulation, plus round-number
snapping, plus archetype tags threaded through evaluation. The model grew from a flat
feature set to a 10-feature contract with a per-feature invariant test.

This is a genuine cost, not a neutral one:

- **A portfolio reviewer has to understand far more to explain the project.**
- Every archetype is a claim about real fraud patterns, and each is a chance to be wrong.
- `docs/`, the trainer and the evaluator are tightly coupled; changing the corpus
  means three files move together.
- A second generator (`scripts/generate_synthetic_data.py`) exists purely for the demo
  seed. It is now fenced off with a separate path and a separate stamp
  (`demo_seed_v1` vs `trainer_v3`) so it cannot clobber the corpus — **a guard that
  exists because the project nearly broke itself this way.**

If the older revision is simpler and still correct, that is a defensible choice, not a
failure. Simplicity is a portfolio asset.

### 3.4 The metric that looks best is the least informative

ROC-AUC moved 0.9303 → 0.9397 and PR-AUC 0.7876 → 0.7936 after the corpus fix. Those
deltas are small and were measured on **synthetic data written by the same author as the
features**. They are not evidence of improved fraud detection. A revision that reports
a *lower* AUC on a more honest corpus may be the better project.

**Compare the corpus, not the metric.**

### 3.5 Regression risks introduced by this work

| Risk | State |
|---|---|
| Retraining off the pinned version produces a different artifact | Mitigated: train inside the container; host `.venv` is 1.5.2 and must not be used |
| Corpus schema and trainer expectations drift apart again | Mitigated: trainer refuses a foreign stamp before parsing a row; a test pins the two stamps apart |
| Drift monitor has no validity | The reference table held **0 rows**. Now refuses to seed below 200 rows rather than seeding from 11. A `model_sha256` column is the real fix and is **not done** |
| Someone aligns the two generator stamps to silence the guard | A test exists specifically to catch this degenerate "fix" |
| Rule-engine tests fail 6 hours a day | Fixed. `VelocityStore` takes an injectable `Clock`; `RuleEngine` deliberately did not, because it reads the transaction's own timestamp, not the wall clock |

---

## 4. Comparison worksheet

Run both revisions through this. Fill the right-hand column from the older project.
**Do not skip a row you cannot measure** — an unmeasured row is itself a finding.

| Check | This revision | Older revision | Better? |
|---|---|---|---|
| $23,000 crypto, high risk — ML score | 98.11 | | |
| $50 ordinary purchase — ML score | 0.42 | | |
| Model responds to `amount`? (0 → 1,000,000) | yes, 97.96 | | |
| Worst single-feature AUC in the corpus | 0.8323 | | *lower is better here* |
| Test ROC-AUC | 0.9397 | | *context-dependent — see §3.4* |
| Test PR-AUC | 0.7936 | | *context-dependent* |
| ECE | 0.0041 | | *lower is better* |
| Brier | 0.0033 | | *lower is better* |
| Mean predicted vs actual fraud rate | 0.0118 vs 0.0096 | | *close is better* |
| False alarms at production threshold | 33 | | |
| Can the training script run? | yes | | *any answer other than "yes" fails* |
| Artifact reproducible from a clean checkout? | yes, byte-identical | | |
| Model/artifact version skew | none (train in container) | | |
| Features with zero variance | 0 | | |
| Contract test exists per feature? | yes | | |
| Backend tests passing | 839 / 0 fail | | *count alone is not quality* |
| `ruff` / `mypy` clean? | yes / yes | | |
| Can the ML layer flag alone? | **no** | | *capability check* |
| Number of distinct claims about fraud the code makes | 7 archetypes | | *lower is more defensible* |

### The two questions that decide the verdict

1. **Does the older revision's model respond to the amount at all?** If it does, and
   the current one also does, the ML capability is comparable and the comparison turns
   on engineering quality, where this revision is ahead.
2. **Could the older revision's training script run?** If not, then whatever numbers it
   reports came from an artifact nobody can regenerate — and this revision is
   categorically better regardless of the metric column.

---

## 5. What this work does NOT establish

**The model has never seen a real fraudulent transaction.** Every number in this
document — the reliability table, PR-AUC 0.7936, the 33 false alarms, the threshold
arithmetic — was measured against a corpus written by the same author who wrote the
features. It contains the model's own assumptions restated as data.

Calibrating a model to a synthetic prior tells you the calibrator works. It says nothing
about whether the prior, the features, or the fraud archetypes resemble reality. This
work made the model's **self-consistency measurable** and its **failure modes visible**.
That is what it does, and it is less than it looks like.

Named limits, in order:

1. **No real labels.** Zero. Every performance figure is self-consistency. There is no
   true false-positive rate at production volume.
2. **The archetypes are a caricature.** Friendly fraud, first-party abuse and mule
   networks are absent *as concepts*, not merely under-represented.
3. **3% of "fraud" is a labelled-noise population**, which places a hard ceiling on
   achievable AUC. That ceiling is a property of the corpus, not of the model.
4. **54% of false positives are `fraud_lookalike`** — honest customers buying crypto at
   3am during a sale. Honest, and it will happen in production.
5. **Nothing has been tested against drift, or against an adversary who reads the
   feature list.**
6. The drift monitor is not yet a monitor. It was made to refuse to lie, not made correct.

---

## 6. The methodological note

Five findings during this investigation were **artifacts of the measurement, not defects
in the code**, and each was reported with confidence before being retracted:

| Reported | Why it was wrong |
|---|---|
| "The model is not loaded" | It was. The warning simply was not emitted. |
| "The velocity features are structurally dead" | Read the wrong producer — a helper, not the call site. The call site populates them correctly. |
| "The feature order does not match" | The artifact's `feature_names` stamp matches `FEATURE_NAMES` exactly. |
| "The score breakdown does not reconcile" | It reconciles to the thousandth: `0.5·85 + 0.25·0.0123 + 0.25·20 = 54.0031`. The context term was estimated by eye. |
| "The amount response is inverted above ~$5,000" | The probe held `amount_vs_user_std = 4.0` fixed while pushing amount to $1,000,000 — a combination that exists nowhere in the corpus. On real corpus vectors the response is monotonic: 43 → 72 across the amount range. |

The distinction that matters: every one of those five was produced by **reading code or
constructing a synthetic input**, and every one was killed by **measuring the artifact**.
The four real defects in §1 were each found by measurement in the first place.

**The method that worked was never "look at the code". It was always "move one thing and
watch what the number does".** That is the transferable finding of this audit, and it is
worth more in a portfolio than the metrics.

---

## 7. Architectural note

Three layers, with a deliberate division of labour:

- **Rule engine** — deterministic, explainable, contributes the hard boundary. Carries
  the current detection.
- **ML model** — a 25% modifier. Contributes ranking within a band the rules have
  already entered. See §3.1: it cannot decide alone, and that is not decided in code.
- **LLM** — generates the narrative report only. **It never decides.** This separation is
  correct and should be stated explicitly in any portfolio presentation: the generative
  component is downstream of the decision, not part of it.

The `layers_used` field on a score records which layers actually contributed, so a score
computed with a missing layer is distinguishable from a full one. **The API exposes it
and the frontend reads it zero times** — the honesty the backend records is not yet
surfaced. A reviewer looking for where the UI could mislead a user should start there.

---

## 8. Reproducing every number

```powershell
# Gates
.venv\Scripts\python.exe -m pytest tests/ -v --cov=src
ruff check src/
mypy src/

# Model behaviour: does it move when a feature moves?
# Run INSIDE the container — the host .venv has a different scikit-learn.
docker compose exec -T api python -c "..."

# Contract test — must FAIL on any pre-cb65b25 artifact
docker compose exec -T api python -m pytest tests/ -k contract -v

# Reliability / calibration report
docker compose exec -T api python scripts/evaluate_model.py

# Full pipeline verdict, with the AUC by archetype
docker compose exec -T api python scripts/evaluate_model.py --archetypes
```

Retraining reproducibility:

```powershell
docker compose exec -T api python scripts/train_xgboost_aligned.py
# three consecutive runs must produce sha256 573b7d09…
```

> `/app/scripts` is **baked into the image**, not bind-mounted. Host edits to
> `scripts/` are invisible inside the container; use `docker cp`. This cost a run.

---

## 9. Verdict template

Fill this in after running the comparison, and **do not soften it**:

```
Old revision:  <one line — what it is and what its model was worth>
New revision:  <one line>

The new revision is better because:      <the single strongest verified reason>
The new revision is worse because:       <the single strongest verified reason>
The verdict rests on:                    <which of §4's two questions decided it>
The claim I would NOT make in an interview:
  <e.g. "it detects real fraud" — because there are no real labels>
```

The last field matters most. Anyone can report an AUC. The credibility of this project
rests on being the person who says *"and here is what that number does not prove"*.
