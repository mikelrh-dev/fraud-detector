"""Expected-cost arithmetic for the fraud classifier.

EVERY COST FIGURE IN THIS MODULE IS AN INPUT THE CALLER SUPPLIES.

Nothing here measured anything. There is no benchmark, no survey result, no
industry average, no default, and no fallback value: a ``CostProfile`` is
always built by the caller out of its own belief about what a false alarm
costs its analysts and what a missed fraud costs its business. This module
holds no opinion about either number, and if it appears to hold one, that is
a bug.

That is the whole design. Expected cost can only answer "how does the decision
change as your beliefs change", so the only honest way to use this module is to
sweep the ratio ``C_fn / C_fp`` across a range and read off the shape of the
answer. A single threshold quoted as *the* right one is a claim this module
deliberately refuses to make on the caller's behalf.

Only the RATIO moves a decision, because every threshold is chosen by
minimising an expected cost and a uniform scale factor divides straight back
out. The absolute scale matters when reporting money to a human; it does not
matter when comparing two operating points.

Pure domain math: no I/O, no model loading, no sklearn, no pandas, no numpy.
The file copies and imports on its own.

Degenerate denominators return 0.0 rather than raising. A base rate of zero, a
threshold high enough to flag nothing and an empty evaluation are all real
operating states for a cost sweep to walk through, not programming errors. The
one thing that does raise is a genuinely ambiguous input -- mismatched array
lengths, or an empty threshold grid with no optimum to return.
"""

from dataclasses import dataclass
from typing import Sequence

__all__ = [
    "ConfusionCounts",
    "CostProfile",
    "OperatingPoint",
    "alerts_per_day",
    "breakeven_cost_ratio",
    "confusion_at",
    "counts_at",
    "expected_cost_per_transaction",
    "optimal_threshold",
    "sweep",
    "total_cost",
]


@dataclass(frozen=True)
class ConfusionCounts:
    """The four cells of a confusion matrix. Raw counts, nothing derived.

    Attributes:
        tp: frauds the model flagged.
        fp: legitimate transactions the model flagged.
        fn: frauds the model let through.
        tn: legitimate transactions the model left alone.
    """

    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def total(self) -> int:
        """Every row the evaluation covered."""
        return self.tp + self.fp + self.fn + self.tn

    @property
    def flagged(self) -> int:
        """Every row that reached a human: true alerts and false alarms alike.

        Both cells, because ``fn`` is the only mistake that costs no analyst
        time.
        """
        return self.tp + self.fp


@dataclass(frozen=True)
class CostProfile:
    """The two cost figures, both supplied by the caller, in one currency.

    Attributes:
        false_positive_cost: cost of ONE false alarm -- the analyst time it
            takes to clear a legitimate transaction.
        false_negative_cost: realised loss from ONE missed fraud.

    Neither figure has a default and neither has a plausible-looking one to
    fall back on, so there is no default to give. A reader who cannot fill
    both in has not yet decided what they are measuring, and a made-up number
    would hide that rather than expose it.
    """

    false_positive_cost: float
    false_negative_cost: float

    @property
    def ratio(self) -> float | None:
        """``C_fn / C_fp``, or None when a false alarm is free.

        None rather than infinity when the denominator is zero: "every alert
        is worth it" is a different statement from "the ratio is enormous",
        and collapsing them would let a free-false-alarm caller silently
        select every threshold as optimal.
        """
        if self.false_positive_cost == 0.0:
            return None
        return self.false_negative_cost / self.false_positive_cost


@dataclass(frozen=True)
class OperatingPoint:
    """One point on the threshold axis, with its arithmetic already done.

    Attributes:
        threshold: the score cut this point was evaluated at, on whatever
            scale the caller passed in.
        tp: frauds flagged.
        fp: legitimate transactions flagged.
        fn: frauds missed.
        tn: legitimate transactions left alone.
        precision: ``tp / (tp + fp)``, or 0.0 when nothing was flagged.
        recall: ``tp / (tp + fn)``, or 0.0 when the evaluation held no frauds.
        expected_cost_per_transaction: the cost of this operating point,
            divided by every row it covered.
    """

    threshold: float
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    expected_cost_per_transaction: float


def confusion_at(
    y_true: Sequence[int],
    y_score: Sequence[float],
    threshold: float,
) -> ConfusionCounts:
    """Split a labelled set into the four confusion-matrix cells at one cut.

    A row is FLAGGED when ``y_score >= threshold``. Equality is on the
    flagging side, which makes the threshold the lowest score that still
    counts as an alert. The alternative (``>``) would let two cuts differing
    only in their treatment of equality disagree about which transactions are
    legitimate -- precisely the ambiguity a threshold exists to remove.

    An empty input returns four zeros. That is a real state for a sweep to
    pass through, not a degenerate one.

    Args:
        y_true: 1 for fraud, 0 for legitimate. Any zero is legitimate; only a
            non-zero counts as fraud.
        y_score: One score per row, on the caller's own scale. Compared
            directly against ``threshold``, so the caller must keep the two on
            the same scale.
        threshold: The cut, inclusive.

    Returns:
        The four cell counts.

    Raises:
        ValueError: If the two sequences differ in length. ``zip`` truncates
            silently at the shorter argument, which would compute a cost
            model over a subset nobody intended to measure and report it as if
            it covered everything.
    """
    if len(y_true) != len(y_score):
        raise ValueError(
            f"y_true and y_score must have the same length; got {len(y_true)} and "
            f"{len(y_score)}. zip() truncates silently, so the confusion counts "
            f"would describe only the shorter one."
        )

    tp = fp = fn = tn = 0
    for truth, score in zip(y_true, y_score):
        flagged = score >= threshold
        if truth:
            if flagged:
                tp += 1
            else:
                fn += 1
        elif flagged:
            fp += 1
        else:
            tn += 1

    return ConfusionCounts(tp=tp, fp=fp, fn=fn, tn=tn)


def counts_at(counts: ConfusionCounts) -> tuple[float, float]:
    """Return ``(precision, recall)`` for a set of confusion counts.

    A ratio with a zero denominator is 0.0 here, never NaN and never an
    exception:

    * precision, ``tp / (tp + fp)``, is undefined when nothing was flagged;
    * recall, ``tp / (tp + fn)``, is undefined when the evaluation held no
      frauds at all.

    Both are states a threshold sweep genuinely visits -- a cut high enough to
    stay silent, and a corpus with no fraud in it -- and a cost report has to
    survive both. Precision is also 0.0 rather than undefined when the model
    flags only legitimate rows, which is what a 0 denominator means there in
    substance.
    """
    flagged = counts.fp + counts.tp
    actual = counts.tp + counts.fn
    precision = counts.tp / flagged if flagged else 0.0
    recall = counts.tp / actual if actual else 0.0
    return precision, recall


def total_cost(counts: ConfusionCounts, profile: CostProfile) -> float:
    """Total cost of an operating point, in the profile's currency.

    ``fp * C_fp + fn * C_fn``. Correct outcomes cost nothing: a caught fraud
    and a correctly cleared legitimate transaction are both worth zero here,
    because the only thing left to pay for is the mistake.
    """
    return counts.fp * profile.false_positive_cost + counts.fn * profile.false_negative_cost


def expected_cost_per_transaction(counts: ConfusionCounts, profile: CostProfile) -> float:
    """Cost of an operating point divided by every row it covered.

    Per-transaction rather than total on purpose: the corpora these counts
    come from differ in size by an order of magnitude, and a raw total would
    make a small evaluation look cheaper than a large one purely because it
    saw fewer transactions.

    Returns 0.0 when the evaluation was empty. A rate over nothing is not
    infinite, it is absent, and 0.0 is the value that keeps it out of the way
    of a comparison.
    """
    if counts.total == 0:
        return 0.0
    return total_cost(counts, profile) / counts.total


def alerts_per_day(counts: ConfusionCounts, transactions_per_day: float) -> float:
    """Flagged rows per day at this operating point.

    ``(fp + tp) / n * transactions_per_day`` -- the false alarms plus the real
    alerts, because both reach a human. Only ``fn`` is the one mistake that
    costs nobody any time.

    ``transactions_per_day`` is the caller's figure and is not checked against
    anything: no volume is correct for a business nobody has measured. What the
    caller must not do is read this as a forecast rather than a rate per unit
    of volume.

    Returns 0.0 when the evaluation was empty.
    """
    if counts.total == 0:
        return 0.0
    return counts.flagged / counts.total * transactions_per_day


def sweep(
    y_true: Sequence[int],
    y_score: Sequence[float],
    profile: CostProfile,
    thresholds: Sequence[float],
) -> list[OperatingPoint]:
    """Evaluate every threshold and return the points in ascending threshold order.

    Sorted on the way out whatever order it was handed, so a caller can read
    the result left to right as a curve without re-sorting it.

    The threshold grid is the caller's, and its resolution is part of the
    result: an optimum found only because the grid happened to land on it is
    not the same claim as one found on a fine grid. Report the grid alongside
    any optimum taken from here.
    """
    points: list[OperatingPoint] = []
    for threshold in sorted(thresholds):
        counts = confusion_at(y_true, y_score, threshold)
        precision, recall = counts_at(counts)
        points.append(
            OperatingPoint(
                threshold=float(threshold),
                tp=counts.tp,
                fp=counts.fp,
                fn=counts.fn,
                tn=counts.tn,
                precision=precision,
                recall=recall,
                expected_cost_per_transaction=expected_cost_per_transaction(counts, profile),
            )
        )
    return points


def optimal_threshold(
    y_true: Sequence[int],
    y_score: Sequence[float],
    profile: CostProfile,
    thresholds: Sequence[float],
) -> OperatingPoint:
    """The cheapest threshold on the grid, with ties broken toward the HIGHER cut.

    Chosen as the point minimising ``expected_cost_per_transaction``.

    TIES BREAK TOWARD THE HIGHER THRESHOLD, because a higher cut flags fewer
    transactions and at equal money the defensible operating point is the
    quieter one: nobody is paged for an alert that a cheaper decision would
    have caught anyway. It is also the conservative direction, which matters
    when the cost profile is a guess -- preferring the cut that does less is
    preferring the one that is wrong in the less expensive way.

    The tie-break is implemented by letting a later point replace an earlier
    one on an equal cost, over a grid that is sorted ascending. Two thresholds
    whose costs differ only by floating-point noise are therefore resolved
    toward the higher one, which is the intended behaviour rather than an
    accident of iteration order.

    Args:
        y_true: 1 for fraud, 0 for legitimate.
        y_score: One score per row, on the same scale as ``thresholds``.
        profile: The caller's cost figures.
        thresholds: The grid to search. The answer is the best point ON THIS
            GRID, not the best threshold in existence; see ``sweep``.

    Returns:
        The winning ``OperatingPoint``.

    Raises:
        ValueError: If the grid is empty. There is no optimum over nothing,
            and returning a fabricated point would be worse than saying so.
    """
    points = sweep(y_true, y_score, profile, thresholds)
    if not points:
        raise ValueError(
            "optimal_threshold needs at least one threshold to choose between; "
            "an empty grid has no optimum."
        )

    best = points[0]
    for point in points[1:]:
        # ``<=`` rather than ``<``, over an ascending grid: an equal cost lets
        # the later (higher) threshold take it. See the docstring for why.
        if point.expected_cost_per_transaction <= best.expected_cost_per_transaction:
            best = point
    return best


def breakeven_cost_ratio(y_true: Sequence[int]) -> float | None:
    """The ``C_fn / C_fp`` ratio at which "flag everything" stops being a bad idea.

    Takes no score array and no threshold grid, because the answer depends only
    on the base rate. Where any cut is placed is not an input to it, so nothing
    is accepted that could suggest otherwise: a ``thresholds`` argument here
    would be a parameter the function cannot honour, and an earlier draft of
    this module carried one until it raised a TypeError in a real caller.

    DERIVATION
    ----------
    Let ``p`` be the fraud prevalence and ``R = C_fn / C_fp`` the cost ratio.
    Neither policy below involves a model, which is the point of comparing
    against them.

    Flag NOTHING: every fraud is missed, and no legitimate transaction is
    ever flagged.
        cost per transaction = p * C_fn = p * R * C_fp

    Flag EVERYTHING: every fraud is caught, and every legitimate transaction
    is flagged.
        cost per transaction = (1 - p) * C_fp

    Flagging everything beats flagging nothing as soon as

        (1 - p) * C_fp  <=  p * R * C_fp
        (1 - p)         <=  p * R
        R               >=  (1 - p) / p

    so the breakeven ratio is ``R* = (1 - p) / p``.

    Read plainly: below ``R*`` a classifier has to be better than reviewing
    every single transaction to justify existing at all, and at ``R*`` exactly
    it does not matter whether the model is switched on. At 1% prevalence
    ``R* = 99``: a missed fraud must be ninety-nine times more expensive than
    a false alarm before flagging everything is rational.

    Note what this ratio is NOT. It says nothing about whether the model is
    good, only where the point sits at which the answer stops depending on
    the model. A strong model pushes its optimum well below ``R*``; a
    degenerate one is already beaten long before it.

    Args:
        y_true: 1 for fraud, 0 for legitimate.
        y_score: Unused; present for signature symmetry.
        thresholds: Unused; present for signature symmetry.

    Returns:
        ``(1 - p) / p``, or None when the prevalence is 0 or 1. With no frauds
        there is nothing to protect, and with no legitimate traffic there is
        nothing to false-alarm on, so no ratio separates two useful policies.
    """
    total = len(y_true)
    if total == 0:
        return None

    prevalence = sum(1 for truth in y_true if truth) / total
    if prevalence <= 0.0 or prevalence >= 1.0:
        return None

    return (1.0 - prevalence) / prevalence
