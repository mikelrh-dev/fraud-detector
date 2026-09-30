"""Cost sensitivity for the deployed fraud classifier.

Run it as one command:

    python scripts/evaluate_cost.py

WHY THIS EXISTS ALONGSIDE evaluate_model.py
-------------------------------------------
``evaluate_model.py`` answers "can this model tell the two classes apart".
This script answers a different and prior question: "given what a false alarm
costs and what a missed fraud costs, is this model worth running at all".

The second question has no answer without two numbers nobody here has, and
this script deliberately does not invent them. The cost of a false alarm is
analyst time at your company. The cost of a missed fraud is your loss rate.
Both are yours to supply, and every figure below is conditioned on the ratio
between them.

So the output is a SWEEP, not a recommendation. The optimal threshold is
different at every ratio, it moves by an order of magnitude across the range
tested here, and any single one of these numbers quoted alone is
meaningless. That is not a limitation of the analysis; it is the finding.

The baseline nobody usually prints is the one that matters most: flag
everything, and flag nothing. Neither needs a model, and a model that cannot
beat both of them at a given cost ratio is not a model -- it is an expense.

Same split as the main harness (test_size=0.2, random_state=42, stratified),
so the numbers here are directly comparable with evaluate_model.py's.

Usage:
    python scripts/evaluate_cost.py
    python scripts/evaluate_cost.py --transactions-per-day 200000
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import evaluate_model as E  # noqa: E402
import train_xgboost_aligned as T  # noqa: E402

from src.services.cost_model import (  # noqa: E402
    ConfusionCounts,
    CostProfile,
    OperatingPoint,
    alerts_per_day,
    breakeven_cost_ratio,
    counts_at,
    expected_cost_per_transaction,
    optimal_threshold,
)
from src.services.ml_model import MLModelService  # noqa: E402

#: Cost ratios swept in the sensitivity table. The span is deliberate: 1x is
#: "a missed fraud hurts no more than a wasted analyst minute" and 500x is
#: "a missed fraud ruins a customer's year". Any answer that does not change
#: across that span was never really about cost.
COST_RATIOS = (1, 5, 10, 25, 50, 100, 500)

#: ASSUMPTION, not a measurement: one false alarm is priced at 1.0 unit. The
#: absolute scale is arbitrary and cancels out of every comparison below;
#: only the RATIO against a missed fraud is load-bearing. What "1.0 unit"
#: means in practice -- ten seconds of analyst time, a hundred seconds -- is
#: the reader's call, and the row it lands on will be a different one.
FALSE_POSITIVE_COST = 1.0

#: ASSUMPTION, not a measurement. The corpus has no timestamps, so nothing
#: here knows how many transactions a real day holds. This is a round number
#: the reader is expected to replace with their own volume.
DEFAULT_TRANSACTIONS_PER_DAY = 50_000.0

#: Score scale. MLModelService.predict() returns a calibrated probability
#: multiplied by 100, so the production tiers (40-70) and the flat grid below
#: live on the same 0-100 scale and are directly comparable.
SCORE_SCALE = "0-100 (calibrated probability x 100)"

#: The flat grid the optimum is searched over. Dense where the scores
#: actually live: at ~1% prevalence almost everything scores under 10, so a
#: uniform grid over 0-100 would waste most of its resolution.
def threshold_grid() -> list[float]:
    """0.05 steps up to 10, then 0.5 steps to 100. 381 points."""
    grid = [i * 0.05 for i in range(0, 201)]
    grid += [10.0 + i * 0.5 for i in range(1, 181)]
    return grid


def _counts_from_point(point: OperatingPoint) -> ConfusionCounts:
    """Rebuild the confusion cells behind a swept ``OperatingPoint``.

    Sweeping once per ratio re-derives the same cells every time, so this
    keeps the cell arithmetic in the module rather than open-coding a second
    copy of it here.
    """
    return ConfusionCounts(tp=point.tp, fp=point.fp, fn=point.fn, tn=point.tn)


def _no_model_baselines(
    n_rows: int,
    n_frauds: int,
    profile: CostProfile,
) -> tuple[float, float]:
    """Cost per transaction of flagging nothing and of flagging everything.

    The two policies that need no model. Computed through the same arithmetic
    as everything else, from the cells each policy produces, so they cannot
    drift from the numbers they are compared against.
    """
    n_legit = n_rows - n_frauds
    flag_nothing = ConfusionCounts(tp=0, fp=0, fn=n_frauds, tn=n_legit)
    flag_everything = ConfusionCounts(tp=n_frauds, fp=n_legit, fn=0, tn=0)
    return (
        expected_cost_per_transaction(flag_nothing, profile),
        expected_cost_per_transaction(flag_everything, profile),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transactions-per-day",
        type=float,
        default=DEFAULT_TRANSACTIONS_PER_DAY,
        help="ASSUMPTION. Volume used to turn per-transaction costs into "
             "per-day money. The corpus has no timestamps, so nothing here "
             "knows your real figure. Default 50000.",
    )
    args = parser.parse_args()
    per_day = args.transactions_per_day

    # force=True because importing the harness leaves the root logger at
    # whatever level the trainer configured, and model-load INFO lines would
    # otherwise land in the middle of the report.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s", force=True)

    service = MLModelService(model_path=str(E.MODEL_PATH))
    if not service.load_model():
        print(f"FATAL: could not load {E.MODEL_PATH}")
        raise SystemExit(1)

    # -- the same held-out split evaluate_model.py uses, so the two agree ----
    #
    # ``row_index`` rides along as the third array purely to recover WHICH rows
    # landed in the test side. Which rows land there is fixed by
    # (y, test_size, random_state, stratify) and is therefore identical to the
    # split evaluate_model.py performs -- the extra array is carried, not used
    # to decide. Without it, the amounts would have to be split by a second,
    # independently-called train_test_split and alignment with X_test would be
    # an assumption rather than a fact. The production threshold is chosen
    # PER ROW from the amount, so a misaligned pair would silently produce a
    # perfectly plausible-looking confusion matrix.
    transactions, y = T.load_synthetic_data(str(T.DATA_SYNTHETIC))
    X, _, amounts, _ = E.build_matrix(transactions)
    row_index = np.arange(len(y))
    # sklearn interleaves: for each array it returns train then test. Verified
    # empirically rather than assumed, because the wrong unpacking order here
    # silently pairs every test feature row with the wrong label -- and the
    # length assertion below would not catch it.
    _, X_test, _, y_test, _, test_index = train_test_split(
        X, y, row_index,
        test_size=E.TEST_SIZE, random_state=E.SPLIT_SEED, stratify=y,
    )
    amounts_test = amounts[test_index]

    assert len(X_test) == len(y_test) == len(amounts_test) == len(test_index), (
        "the test split produced mismatched lengths; the amount tiers would be "
        "applied to the wrong rows"
    )
    assert len(np.unique(test_index)) == len(test_index), (
        "the test split returned a row twice, so per-row costs would be double counted"
    )
    # The length check above cannot catch a WRONG UNPACKING ORDER, which pairs
    # every test feature row with a label belonging to a different transaction
    # and still produces four numbers that look entirely reasonable. Comparing
    # the split against the indices it must have come from can, so do that
    # instead of trusting the return order.
    assert np.array_equal(y_test, y[test_index]), (
        "the unpacked test labels do not belong to the unpacked test rows"
    )
    assert np.array_equal(X_test, X[test_index]), (
        "the unpacked test features do not belong to the unpacked test rows"
    )

    y_score = np.array([service.predict(row) for row in X_test])
    y_list: list[int] = [int(v) for v in y_test]
    score_list: list[float] = [float(v) for v in y_score]

    n_rows = len(y_list)
    n_frauds = int(sum(y_list))
    prevalence = n_frauds / n_rows

    print(f"\n{E.BANNER}")
    print("COST MODEL: THE COST FIGURES ARE ASSUMPTIONS, NOT MEASUREMENTS")
    print(E.BANNER)
    print("""
  Every number on this page is CONDITIONAL. This script measured the model's
  confusion counts; it did not and cannot measure either cost that turns those
  counts into money:

    C_fp = cost of ONE false alarm  (analyst time to clear a legitimate txn)
    C_fn = cost of ONE missed fraud (your realised loss)

  Neither number is a fact about this project, and neither is quoted anywhere
  in industry literature in this file. They are business facts about YOUR
  operation, and you have not supplied them. This script therefore prices a
  false alarm at an arbitrary 1.0 unit and SWEEPS the ratio C_fn/C_fp across
  1x to 500x. The absolute scale is irrelevant -- it divides out of every
  comparison -- and only the ratio moves a decision.

  If you leave this page after reading one row of the table below, you have
  read it wrong. The rows disagree, and the disagreement is the result.
""")

    print(f"  model                {E.MODEL_PATH}")
    print(f"  split                test_size={E.TEST_SIZE} random_state={E.SPLIT_SEED} "
          f"stratified (identical to evaluate_model.py)")
    print(f"  test rows            {n_rows}  fraud {n_frauds} "
          f"({prevalence * 100:.3f}% prevalence)")
    print(f"  score scale          {SCORE_SCALE}")

    # ------------------------------------------------------------------
    # 2. The operating point actually running in production.
    # ------------------------------------------------------------------
    tiers = E.production_threshold(amounts_test)
    production_flagged = y_score >= tiers
    production_counts = ConfusionCounts(
        tp=int(np.sum(production_flagged & (y_test == 1))),
        fp=int(np.sum(production_flagged & (y_test == 0))),
        fn=int(np.sum(~production_flagged & (y_test == 1))),
        tn=int(np.sum(~production_flagged & (y_test == 0))),
    )
    prod_precision, prod_recall = counts_at(production_counts)

    print(f"\n{E.BANNER}")
    print("CURRENT PRODUCTION OPERATING POINT (amount-tiered threshold)")
    print(E.BANNER)
    print("  This is what the deployed system does today. Its cost still depends")
    print("  on the ratio, so no single cost is printed against it yet -- the")
    print("  table further down prices it at every ratio.")
    print("\n  threshold tiers    " + "  ".join(
        f"[{lo:g}, {hi:g}) -> {t:g}" if hi != float("inf") else f"[{lo:g}, inf) -> {t:g}"
        for lo, hi, t in E.THRESHOLD_TIERS
    ))
    print(f"  confusion          TP={production_counts.tp}  FP={production_counts.fp}  "
          f"FN={production_counts.fn}  TN={production_counts.tn}")
    print(f"  precision          {prod_precision:.4f}")
    print(f"  recall             {prod_recall:.4f}")
    missed = production_counts.fn / n_frauds * 100 if n_frauds else float("nan")
    print(f"  frauds missed      {production_counts.fn} of {n_frauds} ({missed:.1f}%)")
    print(f"  flagged rows       {production_counts.flagged} of {n_rows} "
          f"({production_counts.flagged / n_rows * 100:.3f}%)")
    print(f"  alerts/day         {alerts_per_day(production_counts, per_day):,.0f}"
          f"   [ASSUMPTION: {per_day:,.0f} transactions/day]")
    print("  expected cost      not quoted here -- it is a function of C_fn/C_fp,")
    print("                     and quoting one value would be exactly the mistake")
    print("                     this script exists to avoid. See the table below.")

    # ------------------------------------------------------------------
    # 3. Sensitivity sweep.
    # ------------------------------------------------------------------
    grid = threshold_grid()
    print(f"\n{E.BANNER}")
    print("SENSITIVITY: OPTIMAL THRESHOLD vs COST RATIO")
    print(E.BANNER)
    print("  A flat threshold is swept over " + f"{len(grid)} points"
          " (0.05 steps to 10, 0.5 steps to 100).")
    print("  Costs are per transaction, in units where C_fp = 1.0.")
    print("  'change' is the optimal flat point minus the production point:")
    print("  NEGATIVE is a saving, POSITIVE is a loss.\n")
    header = (
        f"  {'C_fn/C_fp':>9} {'opt t':>7} {'precision':>10} {'recall':>8} "
        f"{'model':>9} {'prod':>9} {'change':>9} {'alerts/day':>11}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

    rows: list[dict] = []
    for ratio in COST_RATIOS:
        profile = CostProfile(
            false_positive_cost=FALSE_POSITIVE_COST,
            false_negative_cost=FALSE_POSITIVE_COST * ratio,
        )
        best = optimal_threshold(y_list, score_list, profile, grid)
        best_counts = _counts_from_point(best)
        model_cost = best.expected_cost_per_transaction
        prod_cost = expected_cost_per_transaction(production_counts, profile)
        change = model_cost - prod_cost
        rows.append({
            "ratio": ratio,
            "best": best,
            "counts": best_counts,
            "model_cost": model_cost,
            "prod_cost": prod_cost,
            "change": change,
        })
        print(
            f"  {ratio:>9d} {best.threshold:>7.2f} {best.precision:>10.4f} "
            f"{best.recall:>8.4f} {model_cost:>9.4f} {prod_cost:>9.4f} "
            f"{change:>+9.4f} {alerts_per_day(best_counts, per_day):>11,.0f}"
        )

    # Derived from the sweep above, never hardcoded. These two literals used to
    # read "76.00 down to 0.40" and "0.9904" — figures from an earlier corpus
    # that the table beside them no longer agreed with, so the narrative
    # contradicted the numbers printed two lines above it. The README then
    # quoted the narrative, which is how a stale threshold range reached a
    # document describing a model that had since been retrained.
    opt_high = max(r["best"].threshold for r in rows)
    opt_low = min(r["best"].threshold for r in rows)
    print("\n  Read the 'opt t' column top to bottom before anything else. The")
    print("  cost-optimal threshold is not a constant of the model; it is a")
    print(f"  function of the ratio, and it moves from {opt_high:.2f} down to {opt_low:.2f} across")
    print("  this range -- two orders of magnitude, and a different operating")
    print("  point for every belief about cost a reader might hold.")
    savings = sum(1 for r in rows if r["change"] < 0)
    if savings == 0:
        verdict = "a flat re-threshold is more expensive at EVERY ratio tested"
    elif savings == len(rows):
        verdict = "a flat re-threshold is cheaper at EVERY ratio tested"
    else:
        verdict = (f"it is cheaper at {savings} ratios and more expensive at the "
                   f"other {len(rows) - savings}")
    print(f"\n  Against today's tiered point, {verdict}.")
    if 0 < savings < len(rows):
        print("  The verdict CHANGES SIGN inside the sweep, which is the whole")
        print("  argument for not quoting any one of these rows as the answer.")
    else:
        print("  That it does not change sign here is a fact about THIS model on")
        print("  THIS corpus. It is not a licence to pick a row, and it says")
        print("  nothing about a real labelled corpus, which is the only thing")
        print("  these numbers are waiting for.")

    # -- the baselines that need no model ---------------------------------
    print(f"\n{E.BANNER}")
    print("THE TWO POLICIES THAT NEED NO MODEL")
    print(E.BANNER)
    print("  The model only earns its place if it beats BOTH of these. Neither")
    print("  requires a classifier, a threshold or a model artifact.\n")
    base_header = (
        f"  {'C_fn/C_fp':>9} {'flag nothing':>14} {'flag everything':>16} "
        f"{'best no-model':>15} {'model':>9} {'model wins?':>13}"
    )
    print(base_header)
    print("  " + "-" * (len(base_header) - 2))
    for row in rows:
        profile = CostProfile(
            false_positive_cost=FALSE_POSITIVE_COST,
            false_negative_cost=FALSE_POSITIVE_COST * row["ratio"],
        )
        nothing, everything = _no_model_baselines(n_rows, n_frauds, profile)
        best_baseline = min(nothing, everything)
        which = "flag nothing" if nothing <= everything else "flag EVERYTHING"
        wins = row["model_cost"] < best_baseline
        row["best_baseline"] = best_baseline
        row["baseline_name"] = which
        row["nothing"] = nothing
        row["everything"] = everything
        print(
            f"  {row['ratio']:>9d} {nothing:>14.4f} {everything:>16.4f} "
            f"{best_baseline:>15.4f} {row['model_cost']:>9.4f} "
            f"{('yes' if wins else 'NO'):>13}"
        )
    # Derived, not hardcoded — see the note on the sweep narrative above. The
    # flag-everything cost is a function of the held-out prevalence alone, so it
    # is identical on every row by construction rather than by coincidence.
    everything_fixed = rows[0]["everything"]
    print("\n  Why 'flag everything' ever wins: at ~1% prevalence it false-alarms")
    print("  on 99 of every 100 rows to catch 1, so it is only worth doing when a")
    print("  miss is ruinous relative to wasted analyst time -- which is what the")
    print("  ratio measures, not the model. That is why the baseline is FIXED at")
    print(f"  {everything_fixed:.4f} across the table while 'flag nothing' rises with the ratio.")
    losses = [r for r in rows if r["model_cost"] >= r["best_baseline"]]
    if losses:
        worst = max(losses, key=lambda r: r["model_cost"] - r["best_baseline"])
        print(f"\n  AT RATIO {worst['ratio']} THE MODEL LOSES to "
              f"'{worst['baseline_name']}': {worst['model_cost']:.4f} against "
              f"{worst['best_baseline']:.4f}.")
        print("  The honest reading there is that the classifier is worth less than")
        print("  the cheapest thing you could do instead, which is switch it off.")
    else:
        print("\n  On THIS corpus and THIS model, the optimal flat point beats both")
        print("  no-model policies at every ratio tested. Read that as a statement")
        print("  about arithmetic on synthetic counts, not as a clearance: the same")
        print("  sweep on a real labelled corpus may well produce a 'NO' here, and")
        print("  that row is the one to act on.")

    # ------------------------------------------------------------------
    # 4. Breakeven.
    # ------------------------------------------------------------------
    breakeven = breakeven_cost_ratio(y_list)
    print(f"\n{E.BANNER}")
    print("BREAKEVEN COST RATIO")
    print(E.BANNER)
    if breakeven is None:
        print("  Undefined: this test split has no frauds, or no legitimate")
        print("  traffic. With nothing to protect, or nothing to false-alarm on,")
        print("  no ratio separates two useful policies.")
    else:
        print("  C_fn/C_fp at which flagging EVERY transaction costs exactly as")
        print(f"  much as flagging NONE:  {breakeven:,.1f}")
        print()
        print(f"  In plain English: a missed fraud has to be {breakeven:,.1f}x more")
        print("  expensive than a false alarm before 'review every single")
        print("  transaction' becomes as cheap as 'review none'.")
        print()
        # The floor the model must clear flips at the breakeven: flag-nothing
        # below it, flag-everything above. The flag-everything figure is the
        # one that does NOT move with the ratio (it never misses a fraud), so
        # it is read from any row rather than recomputed.
        nothing_floor = rows[0]["nothing"]
        all_floor = rows[0]["everything"]
        ratio_of_floors = all_floor / nothing_floor if nothing_floor else float("inf")
        print(f"  Below {breakeven:,.1f}:1 the cheaper no-model policy is to review")
        print("  NOTHING, so the model only has to beat a floor of")
        print(f"  {nothing_floor:.4f} per transaction.")
        print(f"  Above {breakeven:,.1f}:1 that policy flips to review EVERYTHING, and")
        print(f"  the floor jumps to {all_floor:.4f} -- about {ratio_of_floors:,.0f}x")
        print("  harder to clear, and it does not move with the ratio at all.")
        print()
        print("  IMPORTANT, because the tempting reading of this number is wrong:")
        print("  crossing the breakeven does NOT make the model worthless. It moves")
        print("  the bar the model has to clear, from 'be better than doing nothing'")
        print("  to 'be better than reviewing everything'. Whether the model clears")
        print("  the new bar is a separate measurement, and it is the 'model wins?'")
        print("  column above.")
        above = [r for r in rows if r["ratio"] > breakeven]
        if above:
            top = max(above, key=lambda r: r["ratio"])
            count = len(above)
            plural = "sits" if count == 1 else "sit"
            print()
            print(f"  On THIS corpus {count} of the {len(rows)} tested ratios {plural}")
            print(f"  above the breakeven, up to {top['ratio']}x. At {top['ratio']}x the")
            print(f"  model still costs {top['model_cost']:.4f} against the")
            print(f"  {all_floor:.4f} flag-everything bar, so it still wins.")
            print("  The breakeven marks where the bar moves; it does not by itself")
            print("  condemn the model. A number that DID condemn it would have to")
            print("  show the optimum above the flag-everything column, not merely a")
            print(f"  ratio above {breakeven:,.1f}.")
        print()
        print("  Note what this is NOT: it says nothing about whether the model is")
        print("  any good. It is a property of the base rate alone -- it is the")
        print("  same number whether the model is excellent or inverted, which is")
        print("  exactly why it cannot be used as evidence either way.")

    # ------------------------------------------------------------------
    # 5. What this comparison is not.
    # ------------------------------------------------------------------
    print(f"\n{E.BANNER}")
    print("KNOWN SIMPLIFICATION AND WHAT THIS DOES NOT VALIDATE")
    print(E.BANNER)
    print(f"""
  KNOWN SIMPLIFICATION
  The swept optimum is a FLAT threshold, while production uses an AMOUNT-TIERED
  threshold (40-70 depending on the transaction amount). The two policies are
  therefore not directly comparable, and every 'change' figure above is
  APPROXIMATE. A properly optimized tiered policy could sit on the other side
  of the production point from the flat one, and this table cannot show it.

  ALSO NOT VALIDATED
  - The cost figures. They are assumptions, restated in the banner.
  - The volume. {per_day:,.0f} transactions/day is an assumption; the corpus has
    no timestamps and cannot tell you your real figure. Every per-day number
    scales linearly with it.
  - Anything about the amount tiering being optimal. Pricing the tiered policy
    properly means sweeping tiers, which is a different script.
  - The grid resolution. The optimum is the best of {len(grid)} cuts, not the
    best cut in existence. Between two adjacent grid points the ranking can
    differ; the reported threshold is a grid point, not a continuous optimum.
  - The synthetic corpus itself. Same caveat as evaluate_model.py: this
    measures self-consistency against data written by the same person who
    wrote the features, not detection in the field. The COST figures above
    inherit that ceiling exactly, because the confusion counts they are applied
    to were measured on it.

  A cost model on synthetic counts is arithmetic, not evidence. It is the
  right arithmetic to have ready the moment a real labelled corpus exists --
  and until then, the honest statement is that the model's real-world cost
  per transaction is UNKNOWN.
""")
    print(E.BANNER)
    print(f"\n  per-day conversions above use the ASSUMPTION of {per_day:,.0f}")
    print("  transactions/day. Re-run with --transactions-per-day to change it.")
    print(E.BANNER)


if __name__ == "__main__":
    main()
