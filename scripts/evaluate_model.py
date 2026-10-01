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

from src.services.feature_engine import FEATURE_NAMES  # noqa: E402
from src.services.ml_model import MLModelService  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("evaluate")

MODEL_PATH = REPO_ROOT / "models" / "xgboost_paysim_v1.joblib"

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
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Feature matrix, labels, raw amounts, and archetype tags.

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
    """
    archetypes = [str(t.get("archetype", "") or "") for t in transactions]
    transactions, labels = T.add_realistic_noise(
        transactions, labels,
        fraud_noise_intensity=T.FRAUD_NOISE_INTENSITY,
    )
    histories = [T.build_synthetic_history(t) for t in transactions]
    X = T.build_feature_vectors(transactions, histories)
    amounts = np.array([float(tx["amount"]) for tx in transactions])
    return X, labels, amounts, archetypes


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
        X, _, amounts, arch_csv = build_matrix(transactions, labels)
        y = labels
        print(f"\nEvaluating the REAL labelled corpus: {args.csv}")
        print("NOTE: run the same command again WITHOUT --csv to see the")
        print("synthetic held-out comparison the synthetic numbers displace.")
        metrics = report_metrics(
            f"REAL LABELLED CORPUS: {args.csv}", service, X, y, amounts, arch_csv
        )
        summary = [("real", metrics)]
    else:
        # Rebuild the training distribution, split it exactly as training
        # does, and prove SMOTE never touched the test side.
        transactions, y = T.load_synthetic_data(str(T.DATA_SYNTHETIC))
        X, _, amounts, arch = build_matrix(transactions, y)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=TEST_SIZE, random_state=SPLIT_SEED, stratify=y
        )
        amounts_train, amounts_test, arch_train, arch_test = train_test_split(
            amounts, arch, test_size=TEST_SIZE, random_state=SPLIT_SEED, stratify=y
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
        metrics = report_metrics(
            "TEST SPLIT (held out from training and from SMOTE)",
            service, X_test, y_test, amounts_test, list(arch_test),
        )

        # A genuinely held-out corpus: same distribution, different seed, so
        # not one row is shared with training. Seed 20240101 is used nowhere
        # in the training path.
        held_tx, held_y = T.generate_synthetic_data(
            n_samples=30000, fraud_rate=0.01, seed=20240101
        )
        X_held, _, amounts_held, arch_held = build_matrix(held_tx, held_y)
        print("\n  held-out corpus: 30000 rows, seed 20240101, never used in training")
        metrics_held = report_metrics(
            "HELD-OUT CORPUS (unseen seed, never trained on, never resampled)",
            service, X_held, held_y, amounts_held, arch_held,
        )
        summary = [("train", metrics_train), ("test", metrics),
                   ("held-out", metrics_held)]

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
""")
    print(BANNER)

    print("\nsummary")
    for name, m in summary:
        print(f"  {name:>10}  PR-AUC {m['pr_auc']:.4f}  ROC-AUC {m['roc_auc']:.4f}  "
              f"precision {m['precision']:.4f}  recall {m['recall']:.4f}  "
              f"F1 {m['f1']:.4f}  FP {m['fp']}  FN {m['fn']}")


if __name__ == "__main__":
    main()
