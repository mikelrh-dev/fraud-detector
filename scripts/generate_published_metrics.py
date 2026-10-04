"""Generate `docs/published_metrics.json`, the machine-written source of truth.

Run it as one command:

    python scripts/generate_published_metrics.py

WHY THIS FILE EXISTS
--------------------
Every metric this project publishes in prose -- in `README.md`, in the case
study, in the cost tables -- used to be transcribed by hand from the output of
`scripts/evaluate_model.py` and `scripts/evaluate_cost.py`. That transcription
is the defect. The harness is seeded and deterministic, so its numbers are
reproducible; but a number copied out of a terminal into a Markdown file is a
*claim* about the harness, and nobody re-checks it. Four times now a code
change moved the numbers and left the prose describing the previous run.

So the numbers stop living in prose. This script writes them to a JSON
manifest, and `tests/docs/test_published_metrics.py` fails when the
documentation and the manifest disagree -- in either direction:

  * a value the manifest publishes that no document mentions is a document
    that stopped quoting the harness, or quoted a number the harness never
    produced;
  * a value the manifest has superseded that is still present somewhere is the
    exact drift this repository keeps suffering, in the direction that is
    invisible to a reader.

THE DEPENDENCY DIRECTION
------------------------
This script does not shell out to the harnesses and parse their stdout. That
would make the producer depend on a human-readable format, so a cosmetic edit
to a `print()` would silently change what gets published. Instead it *imports*
the functions and assembles the manifest from their return values:

    from evaluate_model import (build_matrix, report_metrics, calibration_summary,
                                error_breakdown, wilson_interval, production_threshold)

`main()` is not reusable -- it returns `None` and its numbers exist only as
printed text -- so this script mirrors the orchestration `main()` performs,
calling the same functions with the same arguments. That is deliberate: a
change to `build_matrix` or to a threshold tier moves the manifest here and the
harness together, which is the point. The duplication is the orchestration, not
the arithmetic; no metric is reimplemented below.

A note on `error_breakdown`: it prints its archetype table and returns `None`,
so the rates are read from the harness's own per-archetype arithmetic through
`report_metrics`' returned confusion cells. Its own table remains the
authority for the printed report, and the counts here come from the same
`tier`-aware `production_threshold` prediction path it is fed.

WHAT IS IN THE MANIFEST
-----------------------
Keys are named after the label the documentation uses for the figure, not
after an internal variable, because the drift test compares strings: a value
is only publishable if the manifest knows what the document calls it.

    "test_split":  what README.md calls "the 10,000-row test split"
    "held_out":    the unseen-seed corpus of Chapter 4
    "cost":        the `evaluate_cost.py` sweep, keyed by cost ratio

`superseded` carries the values this manifest has retired, with the key that
replaced each one. The drift test asserts those are absent from every scoped
document. It is the only part of the file not derived from a live measurement,
and it is deliberately hand-maintained: a number can only be retired by
someone who knows what replaced it.
"""

from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.model_selection import train_test_split

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import evaluate_cost as C  # noqa: E402
import evaluate_model as E  # noqa: E402
import train_xgboost_aligned as T  # noqa: E402

from src.services.cost_model import (  # noqa: E402
    ConfusionCounts,
    CostProfile,
    alerts_per_day,
    breakeven_cost_ratio,
    counts_at,
    expected_cost_per_transaction,
    optimal_threshold,
)
from src.services.ml_model import MLModelService  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s", force=True)
logger = logging.getLogger("generate_published_metrics")

OUTPUT_PATH = REPO_ROOT / "docs" / "published_metrics.json"

#: Rows in the corpus `evaluate_model.py` loads. Asserted rather than assumed,
#: because the manifest publishes prevalence and the corpus size together and
#: a silently different corpus would publish both consistently and wrongly.
EXPECTED_CORPUS_ROWS = 50_000

#: Values retired by a previous regeneration of this manifest. Each entry maps
#: a dead string to the manifest key that supersedes it. The drift test reads
#: this list, so retiring a number is one edit here and one regeneration --
#: not a hunt through five documents.
SUPERSEDED: dict[str, str] = {
    "test_split.pr_auc": "0.7728",
    "test_split.roc_auc": "0.9181",
    "cost.optimal_threshold_at_10x": "31.00",
    "cost.sweep_high": "74.00",
    "cost.sweep_low": "0.25",
    "cost.model_cost_at_500x": "0.8052",
    "held_out.pr_auc": "0.7569",
    "held_out.roc_auc": "0.9217",
    "held_out.precision": "0.8865",
    "held_out.recall": "0.7049",
    "held_out.f1": "0.7853",
    "cost.optimal_threshold_at_1x": "11.50",
    "cost.optimal_threshold_at_100x": "0.35",
}

#: Measured, deliberately NOT quoted in the prose. A manifest that demands
#: every measured figure appear in five documents would force the wrong things
#: into them: the harness labels the train split "in-sample - for reference
#: only, not a result", and publishing an in-sample score as a headline is the
#: exact mistake the honesty sections exist to avoid.
#:
#: Each entry maps a manifest key to why it is measured but withheld. The
#: documentation test skips these and asserts the exclusions are few and carry
#: a reason, so this list cannot quietly grow into a loophole.
#: Why the six decision-block figures below are withheld from the prose. One
#: reason, six keys -- it is about the figure, not the block it sits in.
#:
#: The deployed-decision F1 is deliberately not quoted beside the model's. The
#: ensemble holds 0.25 of the score, so the same rows produce a much lower F1
#: once the rules and context arbitrate; printing "0.2012" in a README whose
#: headline is the model's precision is how a deployment scoring 0.20 gets
#: certified as the 0.77 model. The numbers are published in the manifest, which
#: is where an operator reads them.
_DECISION_WITHHELD = (
    "deployed-decision F1, not the model figure; published here so the two are "
    "never confused, withheld from prose so a lower score is not read as the "
    "model's result"
)

NOT_PUBLISHED: dict[str, str] = {
    "train_split_reference_only.pr_auc": "in-sample, not a held-out result",
    "train_split_reference_only.roc_auc": "in-sample, not a held-out result",
    "held_out.precision_ci.0": "held-out interval bound; the published interval is the test split's",
    "held_out.precision_ci.1": "held-out interval bound; the published interval is the test split's",
    "held_out.recall_ci.0": "held-out interval bound; the published interval is the test split's",
    "held_out.recall_ci.1": "held-out interval bound; the published interval is the test split's",
    "held_out.precision_ci_n": "held-out sample size behind a withheld interval",
    "held_out.ece": "calibration of a corpus the prose describes, not tabulates",
    "test_split.brier": "reported by the harness, not claimed in the docs",
    # The decision blocks are measured and published but NOT quoted in prose.
    # One entry per block per split, and only the F1: that is the figure most
    # likely to be read as `test_split.f1`, and the withheld-list cap is 15.
    # The surrounding precision/recall/cells are published but unclaimed for the
    # same reason -- they describe the deployed decision rather than the model,
    # and a decision figure quoted as the model's is the exact defect these
    # blocks were added to end.
    "ensemble_shipped.test_split.f1": _DECISION_WITHHELD,
    "ensemble_shipped.held_out.f1": _DECISION_WITHHELD,
    "routed_policy.test_split.f1": _DECISION_WITHHELD,
    "routed_policy.held_out.f1": _DECISION_WITHHELD,
    "analyst_queue.test_split.f1": _DECISION_WITHHELD,
    "analyst_queue.held_out.f1": _DECISION_WITHHELD,
}


def _round(value: float, places: int) -> float | None:
    """Round for publication, or return None when the value is not finite.

    Three normalisations, all of them things that would otherwise put a broken
    token in a file other tools have to read:

    * A signed calibration gap can round to ``-0.0``, which `json.dumps` writes
      as ``-0.0``. A document quoting "-0.0" reads as a typo, and a manifest
      carrying it makes the drift test compare "-0.0" against "0.0000" and fail
      on a rounding artefact rather than on drift.
    * ``nan`` and ``inf`` are not JSON. ``json.dumps`` emits them as the bare
      tokens ``NaN`` and ``Infinity``, which Python reads back but a strict
      JSON parser rejects -- and the manifest is a machine-written file other
      tools are expected to consume. An empty top calibration bin really does
      produce a NaN observed rate, exactly as `evaluate_model.py` prints it as
      ``n/a``, so the fix is to publish ``null`` and let the consumer read it
      the way the harness's own report does.
    """
    numeric = float(value)
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    rounded = round(numeric, places)
    return 0.0 if rounded == 0.0 else rounded


def _metrics_block(
    title: str,
    service: MLModelService,
    X: np.ndarray,
    y: np.ndarray,
    amounts: np.ndarray,
    archetypes: list[str],
) -> dict[str, Any]:
    """Every published figure for one labelled split, at the harness's rounding.

    Calls `report_metrics` so the printed report and the manifest come from the
    same invocation, then adds the figures `report_metrics` computes but does
    not return: the Wilson intervals and the calibration summary. Both come from
    the harness's own functions on the same score vector, not from a second
    pass over the model.
    """
    metrics = E.report_metrics(title, service, X, y, amounts, archetypes)

    # The same score vector `report_metrics` built internally. Recomputing it
    # here is one extra inference pass per split rather than a second source of
    # truth: `calibration_summary` needs the probabilities, and it is the
    # harness's function that owns that arithmetic.
    y_proba = np.array([service.predict(row) / 100.0 for row in X])
    thresholds = E.production_threshold(amounts)
    y_pred = (y_proba * 100.0 >= thresholds).astype(int)

    tp, fp = int(metrics["tp"]), int(metrics["fp"])
    fn = int(metrics["fn"])
    prec_lo, prec_hi = E.wilson_interval(tp, tp + fp)
    rec_lo, rec_hi = E.wilson_interval(tp, tp + fn)
    calibration = E.calibration_summary(y, y_proba)

    flagged = int(y_pred.sum())
    legitimate = int((y == 0).sum())
    frauds = int(y.sum())
    prevalence = float(y.mean())
    fpr = fp / legitimate if legitimate else 0.0

    return {
        "rows": int(len(y)),
        "frauds": frauds,
        "prevalence": _round(prevalence, 6),
        "pr_auc": _round(metrics["pr_auc"], 4),
        "roc_auc": _round(metrics["roc_auc"], 4),
        "brier": _round(metrics["brier"], 4),
        "precision": _round(metrics["precision"], 4),
        "recall": _round(metrics["recall"], 4),
        "f1": _round(metrics["f1"], 4),
        "tn": int(metrics["tn"]),
        "fp": fp,
        "fn": fn,
        "tp": tp,
        "false_positive_rate": _round(fpr, 6),
        "flagged_rows": flagged,
        "legitimate_rows": legitimate,
        "missed_frauds": fn,
        "precision_ci": [_round(prec_lo, 3), _round(prec_hi, 3)],
        "precision_ci_n": tp + fp,
        "recall_ci": [_round(rec_lo, 3), _round(rec_hi, 3)],
        "recall_ci_n": tp + fn,
        "ece": _round(calibration["ece"], 4),
        "signed_gap": _round(calibration["mean_signed_gap"], 4),
        # Per-bin, because Chapter 4 of the case study publishes a ten-row
        # reliability table and the aggregate ECE is the number that flatters
        # itself at 1% prevalence: 98% of the split sits in the bottom bin, so
        # the weighted average is dominated by a trivially well-calibrated bin.
        # Publishing the aggregate alone would let the table drift unchecked.
        "calibration_bins": [
            {
                "bin": row["bin"],
                "n": int(row["n"]),
                "predicted": _round(row["predicted"], 4),
                "observed": _round(row["observed"], 4),
                "gap": _round(row["observed"] - row["predicted"], 4),
            }
            for row in E.calibration_curve(y, y_proba)
        ],
    }


def _decision_block(
    service: MLModelService,
    X: np.ndarray,
    y: np.ndarray,
    amounts: np.ndarray,
    rows: list[dict],
) -> dict[str, Any]:
    """The deployed DECISION for one split, not the ML layer's opinion of it.

    The manifest's `test_split` block above publishes the model's F1, and that
    number is not the F1 of the system that rejects a transaction: the model
    holds 0.25 of the ensemble, so its score is averaged against 0.75 of rules
    and context before anything is compared to a threshold. Publishing only the
    model figure is how a project ends up certifying F1 0.77 for a deployment
    whose ensemble scores 0.20 -- both true, neither the same measurement.

    So this calls `evaluate_model.report_decision_blocks`, which runs the real
    `RuleEngine`, the real `EnsembleScorer` and the real
    `ScoringService._classify_routed`, and returns three blocks:

        ensemble_shipped  the weighted score at the amount-tiered threshold
        routed_policy     the per-layer routing landed in 3db121c
        analyst_queue     fraud OR review -- what actually reaches a human

Every block publishes `legitimate_rows` with ONE meaning: rows whose label is 0,
the denominator of `false_positive_rate` and of `fp + tn`. The routed blocks add
`verdict_fraud` / `verdict_review` / `verdict_legitimate` for the policy's own
verdict distribution, which is a different count over the same rows -- the policy
flags legitimate traffic, so `verdict_legitimate` is the smaller number.

    `rows` are the SAME noised rows `build_matrix` fed the feature engine, so
    the rule layer and the ML layer are reading one corpus rather than two. Each
    row also carries its own 5-minute velocity count, which is the quantity the
    API reads before scoring, so the velocity rules fire here exactly as they
    fire in production. The one caveat that travels with the numbers is the
    fraud graph: a static CSV cannot hold one, so `near_fraud` never fires.
    """
    rule_scores, context_scores = E.rule_and_context_scores(rows)
    decision = E.report_decision_blocks(
        "manifest", y, amounts,
        rule_scores=rule_scores,
        ml_scores=np.array([service.predict(row) for row in X]),
        context_scores=context_scores,
        archetypes=None,
    )

    def publish(block: dict[str, Any], *, with_discrimination: bool) -> dict[str, Any]:
        out: dict[str, Any] = {
            "rows": int(block["rows"]),
            "frauds": int(block["frauds"]),
            "legitimate_rows": int(block["legitimate_rows"]),
            "precision": _round(block["precision"], 4),
            "recall": _round(block["recall"], 4),
            "f1": _round(block["f1"], 4),
            "tn": int(block["tn"]),
            "fp": int(block["fp"]),
            "fn": int(block["fn"]),
            "tp": int(block["tp"]),
            "flagged_rows": int(block["flagged_rows"]),
            "false_positive_rate": _round(block["false_positive_rate"], 6),
            "missed_frauds": int(block["fn"]),
            "precision_ci": [
                _round(v, 3) for v in E.wilson_interval(int(block["tp"]),
                                                        int(block["tp"]) + int(block["fp"]))
            ],
            "precision_ci_n": int(block["tp"]) + int(block["fp"]),
            "recall_ci": [
                _round(v, 3) for v in E.wilson_interval(int(block["tp"]),
                                                       int(block["tp"]) + int(block["fn"]))
            ],
            "recall_ci_n": int(block["tp"]) + int(block["fn"]),
        }
        if with_discrimination:
            out.update({
                "pr_auc": _round(block["pr_auc"], 4),
                "roc_auc": _round(block["roc_auc"], 4),
                "brier": _round(block["brier"], 4),
                "ece": _round(block["ece"], 4),
                "signed_gap": _round(block["signed_gap"], 4),
                "mean_score": _round(block["mean_score"], 4),
            })
        else:
            # Published as null, not omitted: a routed verdict is a label, so
            # PR-AUC/ROC-AUC/Brier are undefined on it, and a consumer asking
            # for them should get "undefined here" rather than a missing key
            # that looks like an oversight.
            out.update({"pr_auc": None, "roc_auc": None, "brier": None,
                        "discrimination_undefined_reason": (
                            "a routed verdict is a label, not a ranked score; "
                            "PR-AUC/ROC-AUC/Brier are undefined on it"
                        )})
        return out

    ensemble = publish(decision["ensemble"], with_discrimination=True)
    routed = publish(decision["routed"], with_discrimination=False)
    queue = publish(decision["analyst_queue"], with_discrimination=False)
    # `legitimate_rows` is left exactly as `publish` wrote it, from
    # `_binary_block`: rows whose LABEL is 0, in every block. It used to be
    # overwritten here with the routed "legitimate" VERDICT count, so the same
    # key read 9900 in the ensemble block and 9095 in the routed one -- two
    # denominators under one name, and `false_positive_rate` sitting next to a
    # figure it was not the rate against. The verdict distribution is published
    # under its own keys instead.
    for block, source in ((routed, decision["routed"]), (queue, decision["analyst_queue"])):
        for key in ("verdict_fraud", "verdict_review", "verdict_legitimate"):
            block[key] = int(source[key])
    routed["fraud_rows"] = int(decision["routed"]["fraud_rows"])
    routed["review_rows"] = int(decision["routed"]["review_rows"])
    queue["queue_rows"] = int(decision["analyst_queue"]["queue_rows"])

    return {"ensemble_shipped": ensemble, "routed_policy": routed, "analyst_queue": queue}


def _cost_block(service: MLModelService) -> dict[str, Any]:
    """The cost sweep, priced on the same split `evaluate_cost.py` prices.

    Re-derives the split the way `evaluate_cost.py` does -- carrying
    `row_index` through a single `train_test_split` so the amounts that pick the
    threshold tier are the amounts belonging to the test rows, rather than a
    second split that could disagree.
    """
    transactions, y = T.load_synthetic_data(str(T.DATA_SYNTHETIC))
    X, _, amounts, _, _ = E.build_matrix(transactions, y)
    row_index = np.arange(len(y))
    _, X_test, _, y_test, _, test_index = train_test_split(
        X, y, row_index,
        test_size=E.TEST_SIZE, random_state=E.SPLIT_SEED, stratify=y,
    )
    amounts_test = amounts[test_index]

    y_score = np.array([service.predict(row) for row in X_test])
    y_list: list[int] = [int(v) for v in y_test]
    score_list: list[float] = [float(v) for v in y_score]

    n_rows = len(y_list)
    n_frauds = int(sum(y_list))
    prevalence = n_frauds / n_rows

    tiers = E.production_threshold(amounts_test)
    production_flagged = y_score >= tiers
    production_counts = ConfusionCounts(
        tp=int(np.sum(production_flagged & (y_test == 1))),
        fp=int(np.sum(production_flagged & (y_test == 0))),
        fn=int(np.sum(~production_flagged & (y_test == 1))),
        tn=int(np.sum(~production_flagged & (y_test == 0))),
    )
    prod_precision, prod_recall = counts_at(production_counts)

    grid = C.threshold_grid()
    sweep: list[dict[str, Any]] = []
    for ratio in C.COST_RATIOS:
        profile = CostProfile(
            false_positive_cost=C.FALSE_POSITIVE_COST,
            false_negative_cost=C.FALSE_POSITIVE_COST * ratio,
        )
        best = optimal_threshold(y_list, score_list, profile, grid)
        model_cost = best.expected_cost_per_transaction
        prod_cost = expected_cost_per_transaction(production_counts, profile)
        best_counts = C._counts_from_point(best)
        nothing, everything = C._no_model_baselines(n_rows, n_frauds, profile)
        sweep.append({
            "ratio": int(ratio),
            "optimal_threshold": _round(best.threshold, 2),
            "precision": _round(best.precision, 4),
            "recall": _round(best.recall, 4),
            "model_cost": _round(model_cost, 4),
            "production_cost": _round(prod_cost, 4),
            "change": _round(model_cost - prod_cost, 4),
            "alerts_per_day": round(alerts_per_day(best_counts, C.DEFAULT_TRANSACTIONS_PER_DAY)),
            "flag_nothing_cost": _round(nothing, 4),
            "flag_everything_cost": _round(everything, 4),
            "model_beats_best_no_model": bool(model_cost < min(nothing, everything)),
        })

    by_ratio = {row["ratio"]: row for row in sweep}
    opt_high = max(row["optimal_threshold"] for row in sweep)
    opt_low = min(row["optimal_threshold"] for row in sweep)

    return {
        "transactions_per_day": C.DEFAULT_TRANSACTIONS_PER_DAY,
        "false_positive_cost": C.FALSE_POSITIVE_COST,
        "cost_ratios": [int(r) for r in C.COST_RATIOS],
        "threshold_grid_points": len(grid),
        "test_rows": n_rows,
        "test_frauds": n_frauds,
        "test_prevalence": _round(prevalence, 6),
        "production_tp": production_counts.tp,
        "production_fp": production_counts.fp,
        "production_fn": production_counts.fn,
        "production_tn": production_counts.tn,
        "production_precision": _round(prod_precision, 4),
        "production_recall": _round(prod_recall, 4),
        "production_flagged": production_counts.flagged,
        "sweep_high": _round(opt_high, 2),
        "sweep_low": _round(opt_low, 2),
        "optimal_threshold_at_1x": by_ratio[1]["optimal_threshold"],
        "optimal_threshold_at_10x": by_ratio[10]["optimal_threshold"],
        "optimal_threshold_at_100x": by_ratio[100]["optimal_threshold"],
        "model_cost_at_10x": by_ratio[10]["model_cost"],
        "production_cost_at_10x": by_ratio[10]["production_cost"],
        "model_cost_at_500x": by_ratio[500]["model_cost"],
        "flag_nothing_cost_at_10x": by_ratio[10]["flag_nothing_cost"],
        "flag_everything_cost": by_ratio[10]["flag_everything_cost"],
        "breakeven_cost_ratio": _round(breakeven_cost_ratio(y_list) or 0.0, 1),
        "sweep": sweep,
    }


def _archetype_block(
    service: MLModelService,
    X: np.ndarray,
    y: np.ndarray,
    amounts: np.ndarray,
    archetypes: list[str],
) -> dict[str, Any]:
    """Per-archetype error rates, computed from the harness's own prediction path.

    `evaluate_model.error_breakdown` prints exactly this table and returns
    `None`, so it cannot be the source of a machine-readable value. The
    confusion cells below come from the same amount-tiered threshold
    `error_breakdown` is fed inside `report_metrics`, so the two agree by
    construction rather than by transcription.
    """
    y_proba = np.array([service.predict(row) / 100.0 for row in X])
    y_pred = (y_proba * 100.0 >= E.production_threshold(amounts)).astype(int)

    by_arch: dict[str, dict[str, int]] = {}
    for truth, pred, arch in zip(y, y_pred, archetypes):
        if not arch:
            continue
        slot = by_arch.setdefault(arch, {"n": 0, "fn": 0, "fp": 0})
        slot["n"] += 1
        if truth == 1 and pred == 0:
            slot["fn"] += 1
        if truth == 0 and pred == 1:
            slot["fp"] += 1

    return {
        arch: {
            "n": slot["n"],
            "fn": slot["fn"],
            "fn_rate": _round(slot["fn"] / slot["n"] if slot["n"] else 0.0, 3),
            "fp": slot["fp"],
            "fp_rate": _round(slot["fp"] / slot["n"] if slot["n"] else 0.0, 3),
        }
        for arch, slot in sorted(by_arch.items(), key=lambda kv: -kv[1]["n"])
    }


def main() -> None:
    service = MLModelService(model_path=str(E.MODEL_PATH))
    if not service.load_model():
        print(f"FATAL: could not load {E.MODEL_PATH}")
        raise SystemExit(1)

    print(f"model  {E.MODEL_PATH}")
    print("rebuilding the training distribution and splitting it exactly as "
          f"evaluate_model.py does (test_size={E.TEST_SIZE}, seed={E.SPLIT_SEED})")

    transactions, y = T.load_synthetic_data(str(T.DATA_SYNTHETIC))
    assert len(y) == EXPECTED_CORPUS_ROWS, (
        f"corpus has {len(y)} rows, expected {EXPECTED_CORPUS_ROWS}. The manifest "
        f"publishes prevalence alongside row counts; a silently different corpus "
        f"would publish both consistently and wrongly."
    )
    X, _, amounts, arch, rows = E.build_matrix(transactions, y)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=E.TEST_SIZE, random_state=E.SPLIT_SEED, stratify=y
    )
    amounts_train, amounts_test, arch_train, arch_test, rows_train, rows_test = (
        train_test_split(
            amounts, arch, rows,
            test_size=E.TEST_SIZE, random_state=E.SPLIT_SEED, stratify=y,
        )
    )

    # The same invariants evaluate_model.py asserts before it reports anything.
    # They are the difference between "these numbers are reproducible" and
    # "these numbers describe a matrix nobody measured". The fraud-noise one
    # matters most here: the whole reason this manifest's values moved is that
    # `build_matrix` started receiving real labels.
    on_disk = np.array([float(t["amount"]) for t in transactions])
    drift = np.abs(amounts / on_disk - 1.0)[y == 1]
    assert drift.any() and drift.max() > 0.10, (
        "no fraud row moved more than 10% from its on-disk amount -- the fraud "
        "branch of add_realistic_noise did not run"
    )
    stamp = getattr(service, "calibration_prior", None)
    assert stamp is not None, "deployed artifact carries no calibration_prior stamp"
    prior_drift = abs(float(stamp) - float(y_train.mean()))
    assert prior_drift < 1e-9, (
        f"artifact calibration_prior {float(stamp):.9f} != training split prior "
        f"{float(y_train.mean()):.9f} (CAL-001)"
    )

    print("train split")
    train_block = _metrics_block(
        "TRAIN SPLIT (in-sample — reference only)", service,
        X_train, y_train, amounts_train, list(arch_train),
    )
    print("test split")
    test_block = _metrics_block(
        "TEST SPLIT (held out from training and from SMOTE)", service,
        X_test, y_test, amounts_test, list(arch_test),
    )
    archetypes_block = _archetype_block(service, X_test, y_test, amounts_test, list(arch_test))

    print("decision blocks -- test split (ensemble, routed, analyst queue)")
    test_decisions = _decision_block(service, X_test, y_test, amounts_test, list(rows_test))

    print("held-out corpus (unseen seed 20240101)")
    held_tx, held_y = T.generate_synthetic_data(n_samples=30000, fraud_rate=0.01, seed=20240101)
    X_held, _, amounts_held, arch_held, rows_held = E.build_matrix(held_tx, held_y)
    held_block = _metrics_block(
        "HELD-OUT CORPUS (unseen seed)", service, X_held, held_y, amounts_held, arch_held
    )
    print("decision blocks -- held-out corpus")
    held_decisions = _decision_block(service, X_held, held_y, amounts_held, list(rows_held))

    print("cost sweep")
    cost_block = _cost_block(service)

    manifest: dict[str, Any] = {
        "_about": (
            "Machine-written source of truth for every metric this project "
            "publishes in prose. Generated by scripts/generate_published_metrics.py "
            "by importing the harnesses' own functions; never edit by hand. "
            "tests/docs/test_published_metrics.py checks the documentation against "
            "this file, and .github/workflows/metrics-drift.yml regenerates it nightly to "
            "catch harness drift the fast test cannot see."
        ),
        "harness": {
            "script": "scripts/evaluate_model.py",
            "cost_script": "scripts/evaluate_cost.py",
            "model_path": str(Path(E.MODEL_PATH).relative_to(REPO_ROOT).as_posix()),
            "test_size": E.TEST_SIZE,
            "split_seed": E.SPLIT_SEED,
            "corpus_rows": int(len(y)),
            "corpus_frauds": int(y.sum()),
            "corpus_prevalence": _round(float(y.mean()), 6),
            "train_prevalence": _round(float(y_train.mean()), 6),
            "artifact_calibration_prior": _round(float(stamp), 6),
            "held_out_seed": 20240101,
            "held_out_rows": int(len(held_y)),
            "threshold_tiers": [
                {"min_amount": lo, "max_amount": (None if hi == float("inf") else hi), "threshold": t}
                for lo, hi, t in E.THRESHOLD_TIERS
            ],
            "fraud_noise_intensity": T.FRAUD_NOISE_INTENSITY,
        },
        # Keys are the labels the documentation uses, so the drift test compares
        # like with like. `test_split` is what README.md calls the 10,000-row
        # split held out of training and SMOTE; `held_out` is the unseen-seed
        # corpus Chapter 4 publishes beside it.
        "test_split": test_block,
        "held_out": held_block,
        "train_split_reference_only": train_block,
        "test_split_archetypes": archetypes_block,
        # The DECISION, published beside the model that feeds it. `test_split`
        # above is the ML layer's F1 at the production threshold; these three
        # are what the same rows produce once the ensemble weights and the
        # routed policy are applied. They are separate keys rather than extra
        # fields on `test_split` because they are different quantities with
        # different denominators, and merging them is how "F1 0.77" came to
        # stand in for a deployed system scoring 0.20.
        "ensemble_shipped": {
            "note": (
                "EnsembleScorer.combine over the production weights "
                "(rule 0.60 / ml 0.25 / context 0.15), graded at the "
                "amount-tiered threshold. Velocity is per row (the same "
                "5-minute count the API reads before scoring), so the velocity "
                "rules fire here as they fire in production. The one missing "
                "layer is the fraud graph: a static CSV cannot hold one, so "
                "near_fraud never fires."
            ),
            "test_split": test_decisions["ensemble_shipped"],
            "held_out": held_decisions["ensemble_shipped"],
        },
        "routed_policy": {
            "note": (
                "ScoringService._classify_routed, the per-layer routing landed "
                "in 3db121c and given an ML-agreement floor in 2910fa2: fraud if "
                "ml > threshold OR (rule > threshold AND amount >= the critical "
                "floor AND ml_score >= the ML floor); review if not fraud and "
                "(rule > threshold OR ml > threshold * 0.75); legitimate "
                "otherwise. The ML floor is a third condition on the RULE branch "
                "only, so a loud model still blocks on its own and a rule branch "
                "cannot override a model calling the transaction ordinary. "
                "Discrimination metrics are null by construction -- a routed "
                "verdict is a label, not a ranked score."
            ),
            "test_split": test_decisions["routed_policy"],
            "held_out": held_decisions["routed_policy"],
        },
        "analyst_queue": {
            "note": (
                "What reaches a human: the routed policy's fraud OR review "
                "verdicts. A review is not a fraud verdict, but it is a row an "
                "analyst is asked to look at, so its precision is the number "
                "that decides whether the queue is worth staffing. Same single "
                "missing layer as the other two decision blocks: no fraud graph."
            ),
            "test_split": test_decisions["analyst_queue"],
            "held_out": held_decisions["analyst_queue"],
        },
        "cost": cost_block,
        "superseded": {
            "note": (
                "Values retired by this manifest. tests/docs/"
                "test_published_metrics.py fails if any of these still appears in "
                "a scoped document. Each maps to the manifest key that replaced it."
            ),
            "values": dict(sorted(SUPERSEDED.items())),
        },
        "not_published": {
            "note": (
                "Measured but deliberately withheld from the prose. The "
                "documentation test does not require these to appear, and it "
                "fails if this list grows without a reason attached."
            ),
            "values": dict(sorted(NOT_PUBLISHED.items())),
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"  test split  PR-AUC {test_block['pr_auc']}  ROC-AUC {test_block['roc_auc']}")
    print(f"  held-out    PR-AUC {held_block['pr_auc']}  ROC-AUC {held_block['roc_auc']}")
    for label, decisions in (("test split", test_decisions), ("held-out", held_decisions)):
        ens = decisions["ensemble_shipped"]
        routed = decisions["routed_policy"]
        queue = decisions["analyst_queue"]
        print(f"  {label} DECISION (row velocity present; no fraud graph in this corpus)")
        print(f"    ml only    F1 {test_block['f1'] if label.startswith('test') else held_block['f1']}"
              "   <- the model figure above; NOT the deployed decision")
        print(f"    ensemble   precision {ens['precision']}  recall {ens['recall']}  "
              f"F1 {ens['f1']}  FP {ens['fp']}  FN {ens['fn']}")
        print(f"    routed     precision {routed['precision']}  recall {routed['recall']}  "
              f"F1 {routed['f1']}  FP {routed['fp']}  FN {routed['fn']}  "
              f"(fraud {routed['fraud_rows']} review {routed['review_rows']})")
        print(f"    queue      rows {queue['queue_rows']} of {queue['rows']}  "
              f"precision {queue['precision']}  recall {queue['recall']}  F1 {queue['f1']}")
    print(f"  cost        optimal at 10x {cost_block['optimal_threshold_at_10x']}  "
          f"sweep {cost_block['sweep_high']} -> {cost_block['sweep_low']}  "
          f"model cost at 500x {cost_block['model_cost_at_500x']}")


if __name__ == "__main__":
    main()