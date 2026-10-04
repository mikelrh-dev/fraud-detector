"""Evaluation harness for the deployed fraud classifier.

Run it as one command:

    python scripts/evaluate_model.py

The point of this harness is that it is *ready for real labels*. The moment
a genuine labelled fraud set exists, the answer to "is this model any good"
becomes this script pointed at that file instead of a project.

Three things it does that a plain ``model.score()`` does not:

1. **It never reports accuracy.** At 1% prevalence a model that labels
   everything legitimate scores 99% accuracy and catches nothing. PR-AUC,
   recall, precision, F1 and a calibration curve are the only numbers that
   carry information at this base rate.

2. **It separates train from held-out explicitly**, and proves SMOTE was
   confined to the training split. Resampling the test set would inflate
   every metric on this page.

3. **It states what it did not validate**, in a banner, every run. The
   numbers below are measured against synthetic data. That is a statement
   about the plumbing, not about fraud detection.

And one thing it does that a model-only report cannot do at all:

4. **It also measures the decision.** Every labelled set is reported three
   more times -- as the shipped ensemble, as the routed policy from
   ``ScoringService._classify_routed``, and as the analyst queue (fraud plus
   review) -- because the ML score is not what the system acts on. The model
   holds 0.25 of the ensemble, so a model at F1 0.77 and a deployed ensemble at
F1 0.20 can be the same system on the same afternoon. Those blocks carry one
    caveat: this corpus holds no fraud graph. Velocity is per row -- the same
    5-minute count the API reads before scoring -- so the velocity rules fire
    here as they fire in production. See ``report_decision_blocks`` and
    ``offline_context`` for exactly what is missing and why.

Usage:
    python scripts/evaluate_model.py
    python scripts/evaluate_model.py --csv path/to/real_labelled.csv
"""

import argparse
import logging
import math
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import train_xgboost_aligned as T  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split  # noqa: E402

from src.core.config import settings  # noqa: E402
from src.services.ensemble import EnsembleScorer  # noqa: E402
from src.services.feature_engine import FEATURE_NAMES  # noqa: E402
from src.services.ml_model import MLModelService  # noqa: E402
from src.services.rule_engine import RuleEngine  # noqa: E402
from src.services.scoring_service import ScoringService  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("evaluate")

MODEL_PATH = REPO_ROOT / "models" / "xgboost_paysim_v1.joblib"

#: The production scoring classes, built once. These are the objects the API
#: endpoint uses (see the module-level singletons in `src/api/v1/
#: transactions.py`), so the ensemble and routed numbers below are the ones the
#: deployed system produces from the same layers -- not a reimplementation of
#: them. `_classify_routed` is private by name; the harness calls it anyway,
#: because the alternative is transcribing the routing bands into a script,
#: and a transcription is exactly the defect this repository keeps removing.
_ENSEMBLE_SCORER = EnsembleScorer()
_RULE_ENGINE = RuleEngine()
_SCORING_SERVICE = ScoringService(
    ensemble_scorer=_ENSEMBLE_SCORER, rule_engine=_RULE_ENGINE
)

#: Split parameters copied from train_xgboost_aligned.main(). If training
#: changes them this must change too, or the two disagree about what "the
#: test set" is.
TEST_SIZE = 0.2
SPLIT_SEED = 42

#: Production decision bands, from src/core/config.py threshold_tiers.
#: A transaction is review when score >= threshold * 0.75.
THRESHOLD_TIERS = (
    (0.0, 1000.01, 70.0),
    (1000.01, 10000.01, 50.0),
    (10000.01, 50000.01, 45.0),
    (50000.01, float("inf"), 40.0),
)

BANNER = "=" * 78


def production_threshold(amounts: np.ndarray) -> np.ndarray:
    """Per-transaction fraud threshold, following the amount tier."""
    thresholds = np.zeros(len(amounts), dtype=float)
    for low, high, threshold in THRESHOLD_TIERS:
        mask = (amounts >= low) & (amounts < high)
        thresholds[mask] = threshold
    return thresholds


#: Below this distance from 0 or 1, a Wilson bound is float noise from the
#: `centre ± half` subtraction rather than a real bound, so it is snapped to
#: the closed interval.
_EPS = 1e-12


def wilson_interval(successes: int, n_total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Closed-form 95% Wilson score interval for a binomial proportion.

    Used instead of the normal approximation because at this prevalence the
    true-positive counts are in the dozens, where the normal approximation
    pushes a bound outside [0, 1] and is least trustworthy exactly where the
    README asks a reader to trust it least.

    Pure arithmetic on counts already computed by `report_metrics`, so it adds
    no modelling assumption and no dependency. `tests/unit/test_evaluate_model_wilson.py`
    pins it against statsmodels' independent implementation.
    """
    if n_total <= 0:
        return (float("nan"), float("nan"))
    p = successes / n_total
    denom = 1.0 + z * z / n_total
    centre = (p + z * z / (2 * n_total)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n_total + z * z / (4 * n_total * n_total))
    # `centre - half` suffers cancellation at the ends: with p == 0 the exact
    # lower bound is 0 but the subtraction leaves ~1e-18. Snap to the closed
    # interval instead of publishing float noise as a measurement.
    low, high = centre - half, centre + half
    return (0.0 if low < _EPS else low, 1.0 if high > 1.0 - _EPS else high)


def build_matrix(
    transactions: list[dict],
    labels: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], list[dict]]:
    """Feature matrix, labels, raw amounts, archetype tags, and the rows scored.

    `labels` is the real per-row fraud label, and it is handed to the noise
    pass because that is what the trainer does. `train_xgboost_aligned.build_training_matrix`
    calls `add_realistic_noise` with the real labels at line 946; this harness
    used to pass `np.zeros(...)`, so the fraud branch of the noise pass was
    unreachable here — the ±40% fraud amount jitter, the 3% merchant typo and
    the ±30-minute timestamp jitter never ran — while the trainer's own log
    still announced "fraud: 40.0% noise intensity".

    That is not a cosmetic mismatch. The fraud jitter is what makes ~1% of the
    corpus hard; without it this harness was measuring the model against a
    cleaner, less-noised matrix than the one it was fit on, and publishing the
    result as a held-out score. Every figure this harness prints depends on
    reconstructing the trainer's matrix exactly, so the labels are an argument
    and not an implementation detail.

    The labels are returned rather than re-derived from the rows: neither
    `generate_synthetic_data` nor `_load_synthetic_csv` writes an `is_fraud` key
    into the transaction dict (both keep it in the parallel labels array), so a
    row-level `tx.get("is_fraud", 0)` lookup yields an all-zero column on both
    corpora.

    The noised rows are returned for the same reason the labels are: the rule
    engine has to score the rows the MODEL saw, not the rows on disk. The noise
    pass moves a fraud amount by up to 40%, and `high_amount` plus
    `_magnitude_points` read that amount directly, so scoring the pre-noise rows
    would put the rule layer on a different corpus than the ML layer -- and the
    ensemble number would then be combining two different datasets and calling
    it one. Re-running `add_realistic_noise` instead would be equivalent only by
    coincidence (it reseeds `RandomState(42)` per call); returning them makes
    it structural.
    """
    archetypes = [str(t.get("archetype", "") or "") for t in transactions]
    transactions, labels = T.add_realistic_noise(
        transactions, labels,
        fraud_noise_intensity=T.FRAUD_NOISE_INTENSITY,
    )
    histories = [T.build_synthetic_history(t) for t in transactions]
    X = T.build_feature_vectors(transactions, histories)
    amounts = np.array([float(tx["amount"]) for tx in transactions])
    return X, labels, amounts, archetypes, transactions


def calibration_curve(y_true: np.ndarray, y_proba: np.ndarray, n_bins: int = 10):
    """Observed fraud rate per predicted-probability bin.

    A well-calibrated model has observed ≈ predicted in every bin. The
    vertical gap between the two series is the miscalibration, and it is the
    thing that makes a score safe to threshold on.
    """
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (y_proba >= lo) & (y_proba < hi) if i < n_bins - 1 else (y_proba >= lo)
        count = int(mask.sum())
        rows.append({
            "bin": f"[{lo:.1f}, {hi:.1f})",
            "n": count,
            "predicted": float(y_proba[mask].mean()) if count else float("nan"),
            "observed": float(y_true[mask].mean()) if count else float("nan"),
        })
    return rows


def error_breakdown(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    archetypes: list[str],
) -> None:
    """Which kind of transaction did the model get wrong?

    This is the check that makes "the overlap is realistic" an assertion
    rather than a claim. The corpus is built with two deliberate hard
    populations: fraud that is ordinary in every dimension, and legitimate
    traffic that looks fraudulent. If the model's errors are *those*, the
    ceiling is set by the data being honestly hard. If its errors are spread
    uniformly across archetypes, the data is merely noisy and the ceiling is
    an artifact.
    """
    if not archetypes or not any(archetypes):
        return
    print("\n  -- errors by archetype (are they the intended hard cases?) --")
    by_arch: dict[str, dict[str, int]] = {}
    for truth, pred, arch in zip(y_true, y_pred, archetypes):
        if not arch:
            continue
        slot = by_arch.setdefault(arch, {"n": 0, "fn": 0, "fp": 0})
        slot["n"] += 1
        if truth == 1 and pred == 0:
            slot["fn"] += 1
        if truth == 0 and pred == 1:
            slot["fp"] += 1
    print(f"  {'archetype':>18} {'n':>7} {'FN':>6} {'FN rate':>9} {'FP':>6} {'FP rate':>9}")
    for arch, slot in sorted(by_arch.items(), key=lambda kv: -kv[1]["n"]):
        fn_rate = slot["fn"] / slot["n"] if slot["n"] else 0.0
        fp_rate = slot["fp"] / slot["n"] if slot["n"] else 0.0
        print(f"  {arch:>18} {slot['n']:>7d} {slot['fn']:>6d} {fn_rate:>9.3f} "
              f"{slot['fp']:>6d} {fp_rate:>9.3f}")


def report_metrics(
    title: str,
    service: MLModelService,
    X: np.ndarray,
    y: np.ndarray,
    amounts: np.ndarray,
    archetypes: list[str] | None = None,
) -> dict:
    """Print the full metric block for one labelled set and return the numbers."""
    y_proba = np.array([service.predict(row) / 100.0 for row in X])

    print(f"\n{BANNER}\n{title}\n{BANNER}")
    print(f"  rows            {len(y)}")
    print(f"  fraud           {int(y.sum())} ({y.mean() * 100:.2f}% prevalence)")
    print(f"  mean predicted  {y_proba.mean():.4f}   mean actual {y.mean():.4f}")

    pr_auc = float(average_precision_score(y, y_proba)) if y.sum() else float("nan")
    try:
        roc_auc = float(roc_auc_score(y, y_proba))
    except ValueError:
        roc_auc = float("nan")
    brier = float(brier_score_loss(y, y_proba)) if y.sum() else float("nan")

    print("\n  -- discrimination (accuracy is meaningless at this prevalence) --")
    print(f"  PR-AUC (average precision) {pr_auc:.4f}")
    print(f"  ROC-AUC                    {roc_auc:.4f}")
    print(f"  Brier score                {brier:.4f}   (lower is better)")

    # Confusion matrix at the production threshold, per amount tier.
    thresholds = production_threshold(amounts)
    y_pred = (y_proba * 100.0 >= thresholds).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, y_pred, labels=[0, 1]).ravel()
    precision = precision_score(y, y_pred, zero_division=0)
    recall = recall_score(y, y_pred, zero_division=0)
    f1 = f1_score(y, y_pred, zero_division=0)
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    print("\n  -- at the PRODUCTION threshold (amount-tiered, review at 0.75x) --")
    print(f"  precision {precision:.4f}   recall {recall:.4f}   f1 {f1:.4f}")
    print(f"  confusion matrix: TN={tn}  FP={fp}  FN={fn}  TP={tp}")
    print(f"  false positive rate {fpr:.6f}  "
          f"({fp} false alarms per {fp + tn} legitimate)")
    if y.sum():
        print(f"  missed {fn} of {int(y.sum())} frauds ({fn / y.sum() * 100:.1f}%)")

    # Every rate above is a point estimate on a split that holds few frauds.
    # A point estimate without an interval is a claim, not a measurement, so
    # the two rates a decision actually turns on carry theirs.
    #
    # Closed-form Wilson score interval. Chosen over the normal approximation
    # because at ~1% prevalence and double-digit true positives the normal
    # approximation leaves the interval bounds outside [0, 1] and is wrong
    # exactly where it is needed. No new dependency: statsmodels agrees to
    # four decimals (tests/unit/test_evaluate_model_wilson.py).
    print("\n  -- 95% Wilson intervals (the rates a decision turns on) --")
    for label, k, n_total in (
        ("precision", tp, tp + fp),
        ("recall   ", tp, tp + fn),
    ):
        if not n_total:
            continue
        lo, hi = wilson_interval(k, n_total)
        print(f"  {label} {k / n_total:.4f}  CI [{lo:.3f} - {hi:.3f}]  "
              f"width {(hi - lo) * 100:.1f} pts  (n={n_total})")

    prec_curve, rec_curve, _ = precision_recall_curve(y, y_proba)
    print("\n  -- precision/recall at selected score cut-offs --")
    print(f"  {'cut':>6} {'precision':>10} {'recall':>8} {'flagged':>8}")
    for cut in (0.05, 0.10, 0.25, 0.50, 0.75):
        flagged = y_proba >= cut
        p = precision_score(y, flagged, zero_division=0) if flagged.any() else 0.0
        r = recall_score(y, flagged, zero_division=0) if flagged.any() else 0.0
        print(f"  {cut:>6.2f} {p:>10.4f} {r:>8.4f} {int(flagged.sum()):>8d}")
    del prec_curve, rec_curve

    print("\n  -- calibration (observed vs predicted, by probability bin) --")
    print(f"  {'bin':>14} {'n':>7} {'predicted':>10} {'observed':>10} {'gap':>9}")
    curve = calibration_curve(y, y_proba)
    for row in curve:
        pred = "     n/a" if np.isnan(row["predicted"]) else f"{row['predicted']:>10.4f}"
        obs = "     n/a" if np.isnan(row["observed"]) else f"{row['observed']:>10.4f}"
        # observed - predicted. Positive means the bin under-reports fraud.
        gap = (
            "      n/a" if np.isnan(row["observed"]) or np.isnan(row["predicted"])
            else f"{row['observed'] - row['predicted']:>9.4f}"
        )
        print(f"  {row['bin']:>14} {row['n']:>7d} {pred} {obs} {gap}")
    cal = calibration_summary(y, y_proba)
    print(f"  expected calibration error (weighted mean |observed-predicted|) "
          f"{cal['ece']:.4f}")
    print(f"  signed gap (weighted mean observed-predicted)          "
          f"{cal['mean_signed_gap']:+.4f}")

    error_breakdown(y, y_pred, archetypes)

    return {"pr_auc": pr_auc, "roc_auc": roc_auc, "brier": brier,
            "precision": float(precision), "recall": float(recall),
            "f1": float(f1), "tn": int(tn), "fp": int(fp),
            "fn": int(fn), "tp": int(tp)}


def calibration_summary(y_true: np.ndarray, y_proba: np.ndarray) -> dict:
    """Single-number verdict on absolute calibration, for before/after comparison.

    A reliability diagram shows the shape of the miscalibration; this shows its
    size, so a fix can be reported as a measurement rather than a picture.
    ``expected_calibration_error`` is the sample-weighted mean of
    ``|observed - predicted|`` over the bins that actually contain rows, and
    ``brier`` is the squared-error form. Both are dominated by the bins that
    matter, which is why they are the pair to quote.
    """
    curve = [r for r in calibration_curve(y_true, y_proba) if r["n"] > 0]
    total = float(sum(r["n"] for r in curve))
    if total == 0.0:
        return {"ece": float("nan"), "mean_abs_gap": float("nan"), "mean_signed_gap": float("nan")}
    ece = sum(r["n"] / total * abs(r["observed"] - r["predicted"]) for r in curve)
    signed = sum(r["n"] / total * (r["observed"] - r["predicted"]) for r in curve)
    return {
        "ece": float(ece),
        "mean_abs_gap": float(ece),
        "mean_signed_gap": float(signed),
    }


#: The context layer for a caller with no velocity to supply, which is 0.0.
#:
#: `ScoringService.compute_scores` derives the context layer as
#: `min(context["recent_transactions"] / 10.0 * 100, 100.0)`, so a row with no
#: recent transactions scores 0.0 by inspection rather than by transcription --
#: hence the constant instead of a call. It is the default for `report_
#: decision_blocks` when a caller supplies no `context_scores` at all.
#:
#: It is a REAL zero, not an absent layer, and that distinction is load-bearing:
#: `EnsembleScorer.combine` keeps a zero layer's weight and only redistributes
#: for `None`. So the context layer holds its 0.15 and drags every score down by
#: up to 15 points, exactly as it would on a live request from a quiet user.
OFFLINE_CONTEXT_SCORE = 0.0


def context_score_from_velocity(recent_transactions: int) -> float:
    """The context layer for one row, mirroring `compute_scores` exactly.

    Transcribed from the `context_score = min(...)` line inside
    `ScoringService.compute_scores`, because that arithmetic sits in an `async
    def` that also runs the feature engine and the model: calling it per row to
    recover one number would cost a model inference per row and change nothing
    about the number.

    It is pinned against the production path rather than trusted.
    `test_context_score_matches_the_production_formula` runs the real
    `compute_scores` at several velocities and requires this figure to move the
    ensemble by exactly `ensemble_context_weight * context_score`. If production
    ever changes the formula, that test fails here instead of the published
    numbers quietly forking away from the deployed system.
    """
    return min(recent_transactions / 10.0 * 100, 100.0)


def row_velocity(tx: dict) -> int:
    """A row's 5-minute transaction count, read the way the API reads it.

    `velocity_5min` is the corpus column behind the production
    `tx_count_last_5min`: `generate_synthetic_data` writes a 5-minute
    transaction count into it, and `build_synthetic_history` feeds that column
    straight into the feature vector. A missing, negative or unreadable value
    is 0 rather than a crash -- the same reading `_to_finite_float` gives the
    field on the request path.
    """
    try:
        return max(0, int(tx.get("velocity_5min", 0) or 0))
    except (TypeError, ValueError):
        return 0


def offline_context(recent_transactions: int = 0) -> dict:
    """The rule engine's context for a corpus that has no live graph.

    Mirrors the keys `src/api/v1/transactions.py` builds, and is explicit about
    the one it cannot fill.

    `recent_transactions` is the same 5-minute count the API reads from
    `velocity_store.get_counts` and hands to `compute_scores`, which reads it
    BEFORE scoring, so a row's velocity is always known at decision time. The
    corpus records that count per row in `velocity_5min`, and it is the same
    quantity rather than a proxy for it -- see `row_velocity`. Pinning it to 0
    is not a conservative simplification, it is a different system: a row the
    corpus marks as a velocity burst was being scored as though its user had
    been quiet for five minutes, which silently disabled `high_velocity`,
    `velocity_burst` and the velocity corroboration of `unusual_merchant`, and
    held the 0.15 context weight at a constant zero. The model was trained with
    velocity in its feature vector, so measuring the decision without it
    measured a system nobody deploys.

    `graph_features` is what a static CSV genuinely cannot supply. It stays
    empty, so `near_fraud` cannot fire, and that is a real limitation stated
    rather than papered over: the fraud graph is built from live transaction
    edges, and this corpus carries no timestamps to build them from.
    `merchant_blacklist` IS real and comes from settings, so `unusual_merchant`
    is evaluated against the production list.
    """
    return {
        "recent_transactions": int(recent_transactions),
        "known_cards": [],
        "merchant_blacklist": settings.merchant_blacklist,
        "home_country": "AR",
        "graph_features": {},
    }


def rule_and_context_scores(transactions: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Per-transaction (rule_score, context_score) from the production classes.

    Runs the real `RuleEngine` over the real rows rather than inventing a rule
    signal, so the ensemble block below is combining the same two layers the
    deployment combines. Each row is given its own velocity, read through
    `row_velocity` and `offline_context`, so the rule layer sees the velocity
    rules firing exactly as the API lets them fire and the context layer is
    derived from that count by `context_score_from_velocity`.
    """
    rule_scores: list[float] = []
    context_scores: list[float] = []
    for tx in transactions:
        context = offline_context(recent_transactions=row_velocity(tx))
        rule_score, _fired = _RULE_ENGINE.evaluate(tx, context)
        rule_scores.append(float(rule_score))
        context_scores.append(context_score_from_velocity(context["recent_transactions"]))
    return np.array(rule_scores, dtype=float), np.array(context_scores, dtype=float)


def _production_thresholds_via_scorer(amounts: np.ndarray) -> np.ndarray:
    """Thresholds from `EnsembleScorer.get_threshold`, cross-checked.

    The ML block uses `THRESHOLD_TIERS` above, transcribed from config. The
    ensemble and routed blocks use the real `EnsembleScorer.get_threshold`,
    which reads `settings.threshold_tiers` and therefore honours an env
    override. Those two can only disagree if the transcription has gone stale or
    an operator has re-tiered the deployment, and in either case the three
    blocks below would be reporting different thresholds for the same corpus.
    So it is asserted rather than assumed: a mismatch means the published
    numbers and the deployed numbers have diverged, which is precisely the
    class of drift this harness exists to make visible.
    """
    thresholds = np.array(
        [_ENSEMBLE_SCORER.get_threshold(float(a)) for a in amounts], dtype=float
    )
    transcribed = production_threshold(amounts)
    if not np.allclose(thresholds, transcribed):
        differing = sorted({(float(t), float(p)) for t, p in zip(thresholds, transcribed)
                            if not math.isclose(float(t), float(p))})
        raise AssertionError(
            f"EnsembleScorer.get_threshold disagrees with the THRESHOLD_TIERS "
            f"this harness transcribes, on {len(differing)} distinct "
            f"(deployed, transcribed) pairs, first {differing[:4]}. Either the "
            f"transcription in scripts/evaluate_model.py is stale or the "
            f"deployment is re-tiered via the env. The ML, ensemble and routed "
            f"blocks below would otherwise be graded against different "
            f"thresholds for the same rows."
        )
    return thresholds


def _binary_block(
    y: np.ndarray,
    flagged: np.ndarray,
    y_pred_label: np.ndarray | None = None,
) -> dict:
    """Precision/recall/F1, confusion cells and false-positive rate.

    `flagged` is the boolean decision a policy makes. `y_pred_label`, when
    given, is that policy's own three-valued verdict, which is what the
    archetype breakdown is reported against -- the fraud-only view would hide
    every row the policy sent to an analyst.
    """
    y_pred = flagged.astype(int)
    tn, fp, fn, tp = confusion_matrix(y, y_pred, labels=[0, 1]).ravel()
    legitimate = int((y == 0).sum())
    return {
        "rows": int(len(y)),
        "frauds": int(y.sum()),
        "legitimate_rows": legitimate,
        "precision": float(precision_score(y, y_pred, zero_division=0)),
        "recall": float(recall_score(y, y_pred, zero_division=0)),
        "f1": float(f1_score(y, y_pred, zero_division=0)),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "flagged_rows": int(y_pred.sum()),
        "false_positive_rate": (fp / legitimate) if legitimate else 0.0,
        "_y_pred": y_pred if y_pred_label is None else y_pred_label,
    }


def _print_wilson(block: dict) -> None:
    """The two rates a decision turns on, with the interval they were measured at."""
    tp, fp, fn = block["tp"], block["fp"], block["fn"]
    print("\n  -- 95% Wilson intervals (the rates a decision turns on) --")
    for label, k, n_total in (("precision", tp, tp + fp), ("recall   ", tp, tp + fn)):
        if not n_total:
            continue
        lo, hi = wilson_interval(k, n_total)
        print(f"  {label} {k / n_total:.4f}  CI [{lo:.3f} - {hi:.3f}]  "
              f"width {(hi - lo) * 100:.1f} pts  (n={n_total})")


def report_decision_blocks(
    title: str,
    y: np.ndarray,
    amounts: np.ndarray,
    rule_scores: np.ndarray,
    ml_scores: np.ndarray,
    context_scores: np.ndarray | None = None,
    archetypes: list[str] | None = None,
) -> dict:
    """Measure the DECISION, not just the model. Three blocks per labelled set.

    `report_metrics` above answers "how well does the model rank fraud". That is
    not the question the deployment answers, and the gap is the reason this
    harness exists in this form: the model holds 0.25 of the ensemble, so an ML
    score of 95 against a quiet rule layer becomes 23.75 and is classified
    `legitimate`. A model at F1 0.77 and a deployed ensemble at F1 0.20 can be
    the same system on the same afternoon. So the same figures are reported for
    the three policies the API can actually end up in:

      ensemble      the shipped score: `EnsembleScorer.combine` over the
                    production weights, graded at the amount-tiered threshold.
      routed        `ScoringService._classify_routed` -- the policy landed in
                    3db121c, which compares each LAYER to the threshold instead
                    of averaging them first.
      analyst_queue what reaches a human: `fraud` OR `review` under the routed
                    policy. A review is not a fraud verdict, but it is a row an
                    analyst is asked to look at, and its precision is the number
                    that decides whether that queue is worth staffing.

    NOT VALIDATED BY THESE BLOCKS: the corpus carries no fraud graph
    (`offline_context` leaves `graph_features` empty), so `near_fraud` cannot
    fire. Everything else the deployment reads is present, velocity included --
    each row carries its own 5-minute count, which is what the API hands to
    `compute_scores`. So these are the deployed policies measured over a corpus
    with one missing layer, not a floor.
    """
    if context_scores is None:
        context_scores = np.full(len(y), OFFLINE_CONTEXT_SCORE, dtype=float)
    for name, values in (("amounts", amounts), ("rule_scores", rule_scores),
                         ("ml_scores", ml_scores), ("context_scores", context_scores)):
        if len(values) != len(y):
            raise ValueError(
                f"{name} has {len(values)} rows, expected {len(y)} -- the layers "
                f"and the labels would describe different corpora"
            )

    thresholds = _production_thresholds_via_scorer(amounts)
    ensemble_scores = np.array([
        _ENSEMBLE_SCORER.combine(
            rule_score=float(rule_scores[i]),
            ml_score=float(ml_scores[i]),
            context_score=float(context_scores[i]),
        )
        for i in range(len(y))
    ], dtype=float)

    routed_labels = [
        _SCORING_SERVICE._classify_routed(
            rule_score=float(rule_scores[i]),
            ml_score=float(ml_scores[i]),
            context_score=float(context_scores[i]),
            threshold=float(thresholds[i]),
            amount=float(amounts[i]),
        )
        for i in range(len(y))
    ]

    ensemble_flagged = ensemble_scores >= thresholds
    routed_fraud = np.array([label == "fraud" for label in routed_labels])
    queue_flagged = np.array([label in ("fraud", "review") for label in routed_labels])

    print(f"\n{BANNER}\n{title} -- WHAT THE SYSTEM DECIDES\n{BANNER}")
    print("  The blocks below grade the deployed DECISION (ensemble weights, then")
    print("  the routed policy, then the analyst queue) instead of the ML layer")
    print("  alone. A model-only F1 of 0.77 and an ensemble F1 of 0.20 can be the")
    print("  same system on the same afternoon, because the model holds 0.25 of")
    print("  the ensemble and the rest of the weight does the arbitrating.")
    print("  CAVEAT: this corpus has no fraud graph, so near_fraud cannot fire.")
    print("  Velocity IS present -- each row carries its own 5-minute count, the")
    print("  same quantity the API reads before scoring -- so these are the")
    print("  deployed policies measured with one layer missing, not a floor.")

    # ---- ensemble: a continuous score, so it gets the full metric block ----
    y_proba = ensemble_scores / 100.0
    pr_auc = float(average_precision_score(y, y_proba)) if y.sum() else float("nan")
    try:
        roc_auc = float(roc_auc_score(y, y_proba))
    except ValueError:
        roc_auc = float("nan")
    brier = float(brier_score_loss(y, y_proba)) if y.sum() else float("nan")

    print("\n  -- (a) SHIPPED ENSEMBLE: EnsembleScorer.combine, production weights --")
    print(f"  weights            rule {settings.ensemble_rule_weight}  "
          f"ml {settings.ensemble_ml_weight}  context {settings.ensemble_context_weight}")
    print(f"  mean ensemble      {ensemble_scores.mean():.4f}   mean actual {y.mean():.4f}")
    print(f"  PR-AUC {pr_auc:.4f}   ROC-AUC {roc_auc:.4f}   Brier {brier:.4f}")
    ensemble_block = _binary_block(y, ensemble_flagged)
    _print_wilson(ensemble_block)
    calibration = calibration_summary(y, y_proba)
    print(f"  expected calibration error {calibration['ece']:.4f}   "
          f"signed gap {calibration['mean_signed_gap']:+.4f}")
    if y.sum():
        print(f"  missed {ensemble_block['fn']} of {int(y.sum())} frauds "
              f"({ensemble_block['fn'] / y.sum() * 100:.1f}%)")
    error_breakdown(y, ensemble_block["_y_pred"], archetypes or [])

    # ---- routed: a label, so discrimination metrics are undefined on it ----
    fraud_rows = int(routed_fraud.sum())
    review_rows = int(queue_flagged.sum()) - fraud_rows
    verdict_legitimate = int((~queue_flagged).sum())
    print("\n  -- (b) ROUTED POLICY: ScoringService._classify_routed (per layer) --")
    print(f"  fraud {fraud_rows}   review {review_rows}   "
          f"legitimate {verdict_legitimate}")
    routed_block = _binary_block(y, routed_fraud)
    _print_wilson(routed_block)
    print("  discrimination      n/a -- a routed verdict is a label, not a score.")
    print("                       PR-AUC/ROC-AUC/Brier need a ranked score; there")
    print("                       is none, and inventing one from hard labels")
    print("                       would print a metric that looks measured and")
    print("                       is not.")
    # The archetype table counts `pred == 1`, so it needs the fraud-only binary
    # prediction. Handing it the three-valued verdicts would print a table of
    # zeros that reads like a finding: `'fraud' == 0` is False, always.
    error_breakdown(y, routed_block["_y_pred"], archetypes or [])

    # ---- analyst queue: fraud + review, because both reach a human ----
    queue_block = _binary_block(y, queue_flagged)
    print("\n  -- (c) ANALYST QUEUE: fraud OR review (both reach a human) --")
    print(f"  queue rows {queue_block['flagged_rows']} of {len(y)} "
          f"({queue_block['flagged_rows'] / len(y) * 100:.2f}% of the corpus)")
    print(f"  precision {queue_block['precision']:.4f}   "
          f"recall {queue_block['recall']:.4f}   f1 {queue_block['f1']:.4f}")
    print(f"  confusion matrix: TN={queue_block['tn']}  FP={queue_block['fp']}  "
          f"FN={queue_block['fn']}  TP={queue_block['tp']}")
    _print_wilson(queue_block)

    for block in (ensemble_block, routed_block, queue_block):
        block.pop("_y_pred", None)

    return {
        "ensemble": {
            **ensemble_block,
            "pr_auc": pr_auc,
            "roc_auc": roc_auc,
            "brier": brier,
            "ece": calibration["ece"],
            "signed_gap": calibration["mean_signed_gap"],
            "mean_score": float(ensemble_scores.mean()),
        },
        "routed": {
            **routed_block,
            # `legitimate_rows` is inherited from `_binary_block` and means one
            # thing across all three blocks: rows whose LABEL is 0, the
            # denominator of `false_positive_rate` and of `fp + tn`. The verdict
            # distribution is a different quantity -- it counts what the POLICY
            # decided, not what the corpus is -- so it gets its own keys. It used
            # to be written over `legitimate_rows` here, which left one key name
            # meaning "9900 labelled legitimate" in the ensemble block and "9095
            # rows the policy passed" in this one: same field, two denominators,
            # and every rate compared or computed across the two was arithmetic
            # on different quantities. `verdict_legitimate` is often the smaller
            # number precisely because the policy flags legitimate traffic.
            "verdict_fraud": fraud_rows,
            "verdict_review": review_rows,
            "verdict_legitimate": verdict_legitimate,
            # Kept for the printed report's own arithmetic; the manifest publishes
            # the three `verdict_*` counts instead.
            "fraud_rows": fraud_rows,
            "review_rows": review_rows,
            "pr_auc": None,
            "roc_auc": None,
            "brier": None,
        },
        "analyst_queue": {
            **queue_block,
            # `rows` stays the corpus size in all three blocks so every confusion
            # matrix partitions its own corpus; the queue is a SUBSET of it, and
            # its size is what staffing turns on, so it gets a name of its own
            # rather than overloading `rows`. `flagged_rows` already equals it.
            "queue_rows": int(queue_block["flagged_rows"]),
            # The queue is a cut of the same routed verdicts, so it carries the
            # same three counts -- and it needs them for the same reason: its
            # `legitimate_rows` is the label denominator, and the number of rows
            # that never reached a human is a different measurement.
            "verdict_fraud": fraud_rows,
            "verdict_review": review_rows,
            "verdict_legitimate": verdict_legitimate,
            "pr_auc": None,
            "roc_auc": None,
            "brier": None,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", default=None,
        help="Real labelled CSV. When given, this corpus is the ONLY thing "
             "evaluated and the synthetic held-out set is skipped.",
    )
    args = parser.parse_args()

    service = MLModelService(model_path=str(MODEL_PATH))
    if not service.load_model():
        print(f"FATAL: could not load {MODEL_PATH}")
        raise SystemExit(1)

    print(f"\nmodel        {MODEL_PATH}")
    print(f"features     {FEATURE_NAMES}")

    if args.csv:
        transactions, labels = T._load_synthetic_csv(args.csv)
        X, _, amounts, arch_csv, rows_csv = build_matrix(transactions, labels)
        y = labels
        print(f"\nEvaluating the REAL labelled corpus: {args.csv}")
        print("NOTE: run the same command again WITHOUT --csv to see the")
        print("synthetic held-out comparison the synthetic numbers displace.")
        metrics = report_metrics(
            f"REAL LABELLED CORPUS: {args.csv}", service, X, y, amounts, arch_csv
        )
        decisions = report_decision_blocks(
            f"REAL LABELLED CORPUS: {args.csv}",
            y, amounts, *rule_and_context_scores(rows_csv),
            ml_scores=np.array([service.predict(row) for row in X]),
            archetypes=arch_csv,
        )
        summary = [("real", metrics)]
        decision_summary = [("real", decisions)]
    else:
        # Rebuild the training distribution, split it exactly as training
        # does, and prove SMOTE never touched the test side.
        transactions, y = T.load_synthetic_data(str(T.DATA_SYNTHETIC))
        X, _, amounts, arch, rows = build_matrix(transactions, y)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=TEST_SIZE, random_state=SPLIT_SEED, stratify=y
        )
        # The noised rows ride through the same split as the amounts and the
        # archetype tags, so the rule engine scores each split's own rows.
        # Same seed and same `stratify` as the pair above means the same indices
        # -- a second split would be a second, silently different corpus.
        amounts_train, amounts_test, arch_train, arch_test, rows_train, rows_test = (
            train_test_split(
                amounts, arch, rows,
                test_size=TEST_SIZE, random_state=SPLIT_SEED, stratify=y,
            )
        )

        print(f"\n{BANNER}\nPRIOR INTEGRITY CHECK (CAL-001)\n{BANNER}")
        print(f"  corpus rows           {len(y)}  fraud {int(y.sum())}"
              f"  ({y.mean() * 100:.2f}%)")
        print(f"  train rows            {len(y_train)}  fraud {int(y_train.sum())}"
              f"  ({y_train.mean() * 100:.2f}%)")
        print(f"  test rows             {len(y_test)}  fraud {int(y_test.sum())}"
              f"  ({y_test.mean() * 100:.2f}%)")

        # Falsifiable check, not a claim. Three invariants, all of which have
        # failed on this pipeline at some point:
        #
        #   1. The row count of every evaluated split is exactly its share of
        #      the corpus. A resampler inflates the row count; this asserts the
        #      training matrix the calibrator saw was the real one.
        #   2. The prior recorded in the deployed artifact equals the corpus
        #      prevalence. The artifact used to be produced by calibrating on
        #      a 33%-prior matrix, and nothing about the deployed file said so.
        #   3. The fraud branch of the noise pass actually ran on this
        #      harness's own matrix (asserted below).
        expected_train = int(round(len(y) * (1 - TEST_SIZE)))
        assert len(y_train) == expected_train, (
            f"training split has {len(y_train)} rows, expected {expected_train} "
            f"— something resampled the training matrix before calibration "
            f"(CAL-001: a calibrator fit on resampled data is calibrated to "
            f"the resampler's prior, not the data's)"
        )
        print(f"  ASSERTED: train rows == {expected_train} (the corpus share, "
              f"unresampled)")

        # Invariant 3, added after this harness was found passing noise labels.
        #
        # The fraud noise is ±40% on the amount, 3% chance of a merchant typo
        # and ±30 minutes of timestamp jitter. Legitimate noise is ±2-5%. So
        # if the fraud branch ran, at least some corpus amounts moved by more
        # than the legitimate band ever can, and the frauds in particular moved
        # far. If the harness regresses to passing zeros to the noise pass,
        # every row moves by at most 5% and this fires — which is the point:
        # the harness reconstructs the trainer's matrix to measure it, and a
        # silently different matrix produces confident numbers about a corpus
        # that was never evaluated.
        on_disk = np.array([float(t["amount"]) for t in transactions])
        drift = np.abs(amounts / on_disk - 1.0)[y == 1]
        assert drift.any() and drift.max() > 0.10, (
            f"no fraud row moved more than 10% from its on-disk amount "
            f"(max {drift.max() if drift.size else 0.0:.4f}) — the fraud "
            f"branch of add_realistic_noise did not run. Pass the real labels "
            f"to it; np.zeros(...) makes it unreachable."
        )
        print(f"  ASSERTED: fraud noise applied — {int((drift > 0.10).sum())} of "
              f"{int((y == 1).sum())} fraud rows moved >10% from the on-disk "
              f"amount (the legitimate band is ±5%)")

        stamp = getattr(service, "calibration_prior", None)
        if stamp is None:
            print("  WARNING: deployed artifact carries no calibration_prior "
                  "stamp; it predates CAL-001 and its absolute probabilities "
                  "cannot be trusted.")
        else:
            # Compared against the *train split's* prior, because that is the
            # data the calibrator was fit on. It is not the corpus prevalence:
            # a stratified split puts 385 of the 481 frauds in train, so the
            # two differ by 5e-6 for reasons that have nothing to do with
            # resampling. What must match exactly is the prior of the matrix
            # the calibrator saw, and that is what a resampler would change.
            drift = abs(float(stamp) - float(y_train.mean()))
            assert drift < 1e-9, (
                f"artifact calibration_prior {float(stamp):.9f} does not match "
                f"the training split's prior {float(y_train.mean()):.9f} "
                f"(drift {drift:.9f}) — the calibrator was fit on something "
                f"other than the un-resampled training rows (CAL-001)"
            )
            print(f"  ASSERTED: artifact calibration_prior {float(stamp):.6f} "
                  f"== training split prior {float(y_train.mean()):.6f}")
        print("  Every number below is measured at the real prevalence, not an")
        print("  artificial one.")

        metrics_train = report_metrics(
            "TRAIN SPLIT (in-sample — for reference only, not a result)",
            service, X_train, y_train, amounts_train, list(arch_train),
        )
        ml_train = np.array([service.predict(row) for row in X_train])
        rule_train, ctx_train = rule_and_context_scores(list(rows_train))
        decisions_train = report_decision_blocks(
            "TRAIN SPLIT (in-sample — reference only)",
            y_train, amounts_train, rule_train, ml_train,
            context_scores=ctx_train, archetypes=list(arch_train),
        )

        metrics = report_metrics(
            "TEST SPLIT (held out from training and from SMOTE)",
            service, X_test, y_test, amounts_test, list(arch_test),
        )
        ml_test = np.array([service.predict(row) for row in X_test])
        rule_test, ctx_test = rule_and_context_scores(list(rows_test))
        decisions = report_decision_blocks(
            "TEST SPLIT (held out from training and from SMOTE)",
            y_test, amounts_test, rule_test, ml_test,
            context_scores=ctx_test, archetypes=list(arch_test),
        )

        # A genuinely held-out corpus: same distribution, different seed, so
        # not one row is shared with training. Seed 20240101 is used nowhere
        # in the training path.
        held_tx, held_y = T.generate_synthetic_data(
            n_samples=30000, fraud_rate=0.01, seed=20240101
        )
        X_held, _, amounts_held, arch_held, rows_held = build_matrix(held_tx, held_y)
        print("\n  held-out corpus: 30000 rows, seed 20240101, never used in training")
        metrics_held = report_metrics(
            "HELD-OUT CORPUS (unseen seed, never trained on, never resampled)",
            service, X_held, held_y, amounts_held, arch_held,
        )
        ml_held = np.array([service.predict(row) for row in X_held])
        rule_held, ctx_held = rule_and_context_scores(list(rows_held))
        decisions_held = report_decision_blocks(
            "HELD-OUT CORPUS (unseen seed)",
            held_y, amounts_held, rule_held, ml_held,
            context_scores=ctx_held, archetypes=list(arch_held),
        )
        summary = [("train", metrics_train), ("test", metrics),
                   ("held-out", metrics_held)]
        decision_summary = [("train", decisions_train), ("test", decisions),
                            ("held-out", decisions_held)]

    print(f"\n{BANNER}\nWHAT THIS DOES AND DOES NOT VALIDATE\n{BANNER}")
    print("""
VALIDATED BY THESE NUMBERS
  - The training pipeline runs end to end and the artifact loads and scores.
  - The model is not degenerate: it uses more than one signal, and no single
    feature separates the classes on its own.
  - The feature contract holds: every feature varies in the data and moves
    the model's output (tests/test_model_feature_contract.py).
  - Scores are in range and the confusion matrix behaves at the production
    amount-tiered threshold.
  - SMOTE does not leak into any evaluated split.

NOT VALIDATED — AND NOT VALIDATABLE FROM THIS DATA
  - The false-positive rate against real fraud. Not close. This corpus was
    written by the same person who wrote the features, so it contains the
    model's own assumptions restated as data. Its errors are not independent
    of its training signal, and the numbers above measure self-consistency,
    not detection.
  - Recall against real attack patterns. Card testing, account takeover,
    friendly fraud, first-party abuse and money-mule networks are all
    absent as *concepts*; the archetypes here are a caricature of them.
  - Precision under real base rates. Prevalence, merchant mix and the cost
    of a false alarm are all business facts this corpus invents.
  - Calibration in the field. The curve above is calibrated against
    synthetic labels; against real labels it will move, and the thresholds
    must be re-derived.
  - Anything about drift, or about a fraudster who reads this feature list.

A high score on this page is evidence the pipeline is sound. It is NOT
evidence the system detects fraud. Only a real labelled corpus can produce
that, and until one exists the honest statement is that the model's
real-world performance is UNKNOWN.

AND THE DECISION IS NOT THE MODEL
  - The summary below prints the ML layer and the deployed decision side by
    side, because they are not the same measurement and the gap between them
    is the whole point. The model holds 0.25 of the ensemble; the other 0.75
    is rules and context, so a model that ranks well can still be averaged
    into a verdict nobody would have chosen.
  - The ensemble and routed blocks are LOWER BOUNDS. This corpus has no
    velocity window and no fraud graph, so three rules cannot fire and the
    context layer is a real 0.0 that still holds its 0.15 of the weight.
""")
    print(BANNER)

    print("\nsummary -- ML layer vs the deployed decision")
    for (name, m), (_, d) in zip(summary, decision_summary):
        ens, routed, queue = d["ensemble"], d["routed"], d["analyst_queue"]
        print(f"  {name}")
        print(f"  {'ml only':>11}  PR-AUC {m['pr_auc']:.4f}  "
              f"precision {m['precision']:.4f}  recall {m['recall']:.4f}  "
              f"F1 {m['f1']:.4f}")
        print(f"  {'ensemble':>11}  PR-AUC {ens['pr_auc']:.4f}  "
              f"precision {ens['precision']:.4f}  recall {ens['recall']:.4f}  "
              f"F1 {ens['f1']:.4f}  FP {ens['fp']}  FN {ens['fn']}")
        print(f"  {'routed':>11}  "
              f"precision {routed['precision']:.4f}  "
              f"recall {routed['recall']:.4f}  F1 {routed['f1']:.4f}  "
              f"FP {routed['fp']}  FN {routed['fn']}  "
              f"(fraud {routed['fraud_rows']} review {routed['review_rows']})")
        print(f"  {'queue':>11}  rows {queue['queue_rows']} of {queue['rows']}  "
              f"precision {queue['precision']:.4f}  "
              f"recall {queue['recall']:.4f}  F1 {queue['f1']:.4f}")


if __name__ == "__main__":
    main()
