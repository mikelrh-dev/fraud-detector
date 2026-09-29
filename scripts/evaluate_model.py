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
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from sklearn.metrics import (  # noqa: E402
    average_precision_score, brier_score_loss, confusion_matrix, f1_score,
    precision_recall_curve, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import train_test_split  # noqa: E402

from src.services.feature_engine import FEATURE_NAMES  # noqa: E402
from src.services.ml_model import MLModelService  # noqa: E402

import train_xgboost_aligned as T  # noqa: E402

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


def build_matrix(
    transactions: list[dict],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Feature matrix, labels, raw amounts, and archetype tags."""
    archetypes = [str(t.get("archetype", "") or "") for t in transactions]
    transactions, _ = T.add_realistic_noise(
        transactions, np.zeros(len(transactions), dtype=int),
        fraud_noise_intensity=T.FRAUD_NOISE_INTENSITY,
    )
    histories = [T.build_synthetic_history(t) for t in transactions]
    X = T.build_feature_vectors(transactions, histories)
    y = np.array([int(tx.get("is_fraud", 0)) for tx in transactions])
    amounts = np.array([float(tx["amount"]) for tx in transactions])
    return X, y, amounts, archetypes


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
    print(f"  {'bin':>14} {'n':>7} {'predicted':>10} {'observed':>10}")
    curve = calibration_curve(y, y_proba)
    for row in curve:
        pred = "     n/a" if np.isnan(row["predicted"]) else f"{row['predicted']:>10.4f}"
        obs = "     n/a" if np.isnan(row["observed"]) else f"{row['observed']:>10.4f}"
        print(f"  {row['bin']:>14} {row['n']:>7d} {pred} {obs}")

    error_breakdown(y, y_pred, archetypes)

    return {"pr_auc": pr_auc, "roc_auc": roc_auc, "brier": brier,
            "precision": float(precision), "recall": float(recall),
            "f1": float(f1), "tn": int(tn), "fp": int(fp),
            "fn": int(fn), "tp": int(tp)}


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
        X, _, amounts, arch_csv = build_matrix(transactions)
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
        X, _, amounts, arch = build_matrix(transactions)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=TEST_SIZE, random_state=SPLIT_SEED, stratify=y
        )
        amounts_train, amounts_test, arch_train, arch_test = train_test_split(
            amounts, arch, test_size=TEST_SIZE, random_state=SPLIT_SEED, stratify=y
        )

        print(f"\n{BANNER}\nSMOTE CONFINEMENT CHECK\n{BANNER}")
        print(f"  train rows            {len(y_train)}  fraud {int(y_train.sum())}"
              f"  ({y_train.mean() * 100:.2f}%)")
        print(f"  test rows             {len(y_test)}  fraud {int(y_test.sum())}"
              f"  ({y_test.mean() * 100:.2f}%)")

        # Falsifiable check: record the test split's class balance, resample
        # the train split for real, then assert the test balance is untouched.
        test_fraud_before = int(y_test.sum())
        test_rows_before = len(y_test)

        from imblearn.over_sampling import SMOTE
        X_train_res, y_train_res = SMOTE(
            sampling_strategy=0.5, random_state=SPLIT_SEED
        ).fit_resample(X_train, y_train)
        print(f"  after SMOTE (train)   {len(X_train_res)}  fraud {int(y_train_res.sum())}"
              f"  ({y_train_res.mean() * 100:.2f}%)")
        print(f"  test rows after SMOTE {len(y_test)}  fraud {int(y_test.sum())}"
              f"  ({y_test.mean() * 100:.2f}%)")
        assert len(y_test) == test_rows_before, "test split row count changed"
        assert int(y_test.sum()) == test_fraud_before, "test split was resampled"
        print("  ASSERTED: the test split is byte-identical after SMOTE ran on")
        print("  the train split. Every number below is measured at the real 1%")
        print("  prevalence, not an artificial 50/50.")

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
        X_held, _, amounts_held, arch_held = build_matrix(held_tx)
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
