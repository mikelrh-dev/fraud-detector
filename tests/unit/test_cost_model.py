"""Expected-cost arithmetic: the tests a degenerate model cannot pass.

A cost model is only worth having if it can say a classifier is worthless.
``precision`` and ``recall`` cannot do that job. At 1% prevalence a model that
scores every legitimate transaction above every fraud still posts respectable
numbers and the report looks fine. Expected cost can, because it prices the
mistake in the reader's own money and compares it against the two policies
that need no model at all: flag nothing, or flag everything.

Every expectation here is hand-computed on a handful of rows. That is
deliberate. The failure mode being guarded against is a formula that is wrong
in a way that still returns plausible-looking numbers, and a machine-generated
oracle would inherit the same misunderstanding as the implementation. Six rows
written out by hand cannot.

The two at the bottom are the ones that earn the file:

  * a PERFECT classifier must reach exactly 0.0 expected cost, or the
    arithmetic is quietly inflating something; and
  * an INVERTED classifier (frauds scored below legitimate traffic) must be
    beaten by flagging NOTHING, at every threshold. That is the check which
    would have caught a degenerate model while every other line of the
    evaluation report still read normally.
"""

import pytest

from src.services.cost_model import (
    ConfusionCounts,
    CostProfile,
    alerts_per_day,
    breakeven_cost_ratio,
    confusion_at,
    counts_at,
    expected_cost_per_transaction,
    optimal_threshold,
    sweep,
    total_cost,
)

#: A false alarm costs one unit of analyst time; a missed fraud costs 100.
#: The absolute scale is arbitrary on purpose -- only the ratio moves decisions.
CHEAP_FP = CostProfile(false_positive_cost=1.0, false_negative_cost=100.0)

#: The two mistakes priced identically. Used only where a tie is wanted: the
#: tie-break is a property of the comparison, not of the cost ratio.
EVEN_COST = CostProfile(false_positive_cost=1.0, false_negative_cost=1.0)


class TestConfusionAt:
    def test_counts_each_cell_of_the_matrix(self) -> None:
        """Six rows, one cut, all four cells non-zero so no cell is untested.

            i  truth  score  flagged at 0.5  cell
            0    1     0.90      yes         tp
            1    0     0.20      no          tn
            2    1     0.50      yes         tp   (boundary: score == threshold)
            3    0     0.70      yes         fp
            4    1     0.10      no          fn
            5    0     0.95      yes         fp
        """
        y_true = [1, 0, 1, 0, 1, 0]
        y_score = [0.90, 0.20, 0.50, 0.70, 0.10, 0.95]

        counts = confusion_at(y_true, y_score, 0.5)

        assert counts == ConfusionCounts(tp=2, fp=2, fn=1, tn=1)
        # Every row is accounted for exactly once -- a mislabelled cell would
        # silently shrink or grow the denominator of every downstream number.
        assert counts.tp + counts.fp + counts.fn + counts.tn == len(y_true)

    def test_score_exactly_on_the_threshold_is_flagged(self) -> None:
        """The boundary convention, pinned.

        ``y_score >= threshold`` puts equality on the flagging side: the
        threshold is the LOWEST score that still counts as an alert. The
        alternative (``>``) would make two thresholds that differ only in how
        they treat equality disagree about which transactions are legitimate,
        which is exactly the ambiguity a threshold is supposed to remove.
        """
        assert confusion_at([1, 0], [0.5, 0.5], 0.5) == ConfusionCounts(
            tp=1, fp=1, fn=0, tn=0
        )

    def test_a_score_epsilon_below_the_threshold_is_not_flagged(self) -> None:
        """The other side of the same convention."""
        counts = confusion_at([1, 0], [0.4999, 0.5], 0.5)
        assert counts == ConfusionCounts(tp=0, fp=1, fn=1, tn=0)

    def test_an_empty_input_is_four_zeros(self) -> None:
        """No rows is not an error; it is an empty evaluation."""
        assert confusion_at([], [], 0.5) == ConfusionCounts(tp=0, fp=0, fn=0, tn=0)

    def test_mismatched_lengths_are_rejected(self) -> None:
        """A silent truncation here would compute a cost model over the wrong data.

        ``zip`` stops at the shorter argument without complaining, so a stray
        off-by-one in a caller's split would quietly produce plausible-looking
        numbers from a subset nobody intended to measure.
        """
        with pytest.raises(ValueError, match="same length"):
            confusion_at([1, 0, 1], [0.9, 0.1], 0.5)


class TestCountsAt:
    def test_precision_and_recall(self) -> None:
        # tp=2 fp=2 -> precision 2/4; tp=2 fn=2 -> recall 2/4
        assert counts_at(ConfusionCounts(tp=2, fp=2, fn=2, tn=94)) == (0.5, 0.5)

    def test_no_flagged_rows_gives_zero_precision(self) -> None:
        """tp+fp == 0: nothing was flagged, so precision is undefined -> 0.0.

        Not NaN and not an exception. A threshold high enough to flag nothing
        is a legitimate operating point, and a cost sweep walks through it.
        """
        assert counts_at(ConfusionCounts(tp=0, fp=0, fn=7, tn=93)) == (0.0, 0.0)

    def test_no_actual_frauds_gives_zero_recall(self) -> None:
        """tp+fn == 0: the test set contains no frauds at all -> recall 0.0."""
        assert counts_at(ConfusionCounts(tp=0, fp=7, fn=0, tn=93)) == (0.0, 0.0)

    def test_a_completely_empty_evaluation_does_not_divide_by_zero(self) -> None:
        """Both denominators zero at once -- the case that would crash."""
        assert counts_at(ConfusionCounts(tp=0, fp=0, fn=0, tn=0)) == (0.0, 0.0)


class TestCostArithmetic:
    def test_total_cost_prices_only_the_mistakes(self) -> None:
        """Correct frauds and correct clears are worth nothing.

        3 false alarms x 1.0 = 3.0, plus 2 missed frauds x 100.0 = 200.0.
        """
        counts = ConfusionCounts(tp=10, fp=3, fn=2, tn=85)
        assert total_cost(counts, CHEAP_FP) == 203.0

    def test_total_cost_of_a_perfect_classifier_is_zero(self) -> None:
        assert total_cost(ConfusionCounts(tp=10, fp=0, fn=0, tn=90), CHEAP_FP) == 0.0

    def test_expected_cost_divides_by_every_row(self) -> None:
        """100 rows (10+3+2+85), 203.0 of cost -> 2.03 per transaction."""
        counts = ConfusionCounts(tp=10, fp=3, fn=2, tn=85)
        assert expected_cost_per_transaction(counts, CHEAP_FP) == pytest.approx(2.03)

    def test_expected_cost_on_an_empty_evaluation_is_zero(self) -> None:
        """n == 0: a rate over no transactions is 0.0, never a ZeroDivisionError."""
        assert expected_cost_per_transaction(
            ConfusionCounts(tp=0, fp=0, fn=0, tn=0), CHEAP_FP
        ) == 0.0


class TestAlertsPerDay:
    def test_counts_every_flagged_row(self) -> None:
        """10 real alerts + 5 false alarms out of 100 rows, at 1000/day.

        (5 + 10) / 100 * 1000 = 150 alerts a day. Analysts clear the false
        alarms; they also have to look at the 10 real ones, so both cells
        count -- only ``fn`` is free of a human.
        """
        counts = ConfusionCounts(tp=10, fp=5, fn=2, tn=83)
        assert alerts_per_day(counts, 1000.0) == pytest.approx(150.0)

    def test_zero_rows_is_zero_alerts(self) -> None:
        assert alerts_per_day(ConfusionCounts(tp=0, fp=0, fn=0, tn=0), 50_000.0) == 0.0


class TestSweep:
    def test_returns_one_point_per_threshold_in_ascending_order(self) -> None:
        """Sorted ascending whatever order it is handed, so a caller can walk
        the result left to right and read it as a curve."""
        y_true = [1, 0, 0, 0, 1, 0]
        y_score = [0.90, 0.10, 0.85, 0.05, 0.95, 0.70]

        points = sweep(y_true, y_score, CHEAP_FP, [0.9, 0.1, 0.5])

        assert [p.threshold for p in points] == [0.1, 0.5, 0.9]

    def test_each_point_carries_its_own_arithmetic(self) -> None:
        """At 0.5 the flagged rows are 0.90, 0.85, 0.95, 0.70.

        frauds flagged: 0.90, 0.95 -> tp=2; legitimate flagged: 0.85, 0.70 -> fp=2.
        Below the cut sit 0.10 and 0.05, and BOTH are legitimate (the frauds
        are at indices 0 and 4, both flagged) -> fn=0, tn=2.
        cost = 2*1 + 0*100 = 2 over 6 rows = 0.3333.
        """
        y_true = [1, 0, 0, 0, 1, 0]
        y_score = [0.90, 0.10, 0.85, 0.05, 0.95, 0.70]

        point = sweep(y_true, y_score, CHEAP_FP, [0.5])[0]

        assert (point.tp, point.fp, point.fn, point.tn) == (2, 2, 0, 2)
        assert point.precision == pytest.approx(2 / 4)
        assert point.recall == 1.0
        assert point.expected_cost_per_transaction == pytest.approx(2 / 6)

    def test_an_empty_threshold_list_sweeps_to_nothing(self) -> None:
        assert sweep([1, 0], [0.9, 0.1], CHEAP_FP, []) == []


class TestOptimalThreshold:
    #: Hand-checked costs at C_fn/C_fp = 100, six rows, two frauds:
    #:   t=0.0 -> flag all: 4 FP, 0 FN -> 4/6   = 0.667
    #:   t=0.5 -> 2 FP, 0 FN          -> 2/6   = 0.333
    #:   t=0.8 -> 1 FP, 0 FN          -> 1/6   = 0.167   <- unique minimum
    #:   t=1.0 -> flag none: 2 FN     -> 200/6 = 33.333
    PERFECTLY_RANKED_Y = ([1, 0, 0, 0, 1, 0], [0.90, 0.10, 0.85, 0.05, 0.95, 0.70])
    GRID = [0.0, 0.5, 0.8, 1.0]

    def test_recovers_a_known_optimum(self) -> None:
        y_true, y_score = self.PERFECTLY_RANKED_Y

        best = optimal_threshold(y_true, y_score, CHEAP_FP, self.GRID)

        assert best.threshold == 0.8
        assert (best.tp, best.fp, best.fn, best.tn) == (2, 1, 0, 3)
        assert best.precision == pytest.approx(2 / 3)
        assert best.recall == 1.0
        assert best.expected_cost_per_transaction == pytest.approx(1 / 6)

    def test_ties_break_toward_the_higher_threshold(self) -> None:
        """Two cuts cost exactly the same, and the model must pick the quiet one.

        y_true = [0, 1], y_score = [0.9, 0.1], with the two mistakes priced
        identically (C_fp = C_fn = 1.0):
          t=0.05 flag both   -> 1 FP, 0 FN -> cost 1 -> 1/2 = 0.5
          t=0.50 flag the 0.9 -> 1 FP, 1 FN -> cost 2 -> 2/2 = 1.0
          t=1.00 flag none   -> 0 FP, 1 FN -> cost 1 -> 1/2 = 0.5

        0.05 and 1.00 tie at exactly 0.5. The higher threshold wins: at equal
        money the defensible operating point is the one that sends fewer
        transactions to a human. (1.0 is the degenerate "flag nothing" cut, so
        this also pins that the tie-break never inflates alert volume.)

        The equal pricing is load-bearing. At C_fn/C_fp = 100 the same two
        cuts cost 0.5 and 50.0, there is no tie, and the lowest threshold is
        correctly the minimum -- which is why this is a separate test and not
        a variation on the one above.
        """
        y_true = [0, 1]
        y_score = [0.9, 0.1]

        best = optimal_threshold(y_true, y_score, EVEN_COST, [0.05, 0.5, 1.0])

        assert best.threshold == 1.0
        assert best.expected_cost_per_transaction == pytest.approx(0.5)
        # The tie is real, not an artefact of rounding: both ends are 0.5.
        costs = {p.threshold: p.expected_cost_per_transaction
                 for p in sweep(y_true, y_score, EVEN_COST, [0.05, 0.5, 1.0])}
        assert costs[0.05] == costs[1.0] == 0.5

    def test_an_empty_grid_has_no_optimum(self) -> None:
        with pytest.raises(ValueError, match="at least one threshold"):
            optimal_threshold([1, 0], [0.9, 0.1], CHEAP_FP, [])


class TestBreakevenCostRatio:
    def test_is_ninety_nine_at_one_percent_prevalence(self) -> None:
        """One fraud in a hundred rows.

        Flagging everything costs the 99 false alarms; flagging nothing costs
        the 1 missed fraud times C_fn. They balance when C_fn is 99 times
        C_fp. Below that ratio the rational policy is to review nothing; the
        model has to be better than doing nothing to justify existing at all.
        """
        y_true = [1] + [0] * 99

        assert breakeven_cost_ratio(y_true) == pytest.approx(99.0)

    def test_is_exact_when_the_base_rate_is_exact(self) -> None:
        """p = 0.25 -> (1 - 0.25) / 0.25 = 3.0, with no rounding to hide behind."""
        y_true = [1, 0, 0, 0]
        assert breakeven_cost_ratio(y_true) == 3.0

    def test_no_frauds_at_all_is_undefined(self) -> None:
        """With no frauds there is nothing to protect, so no ratio separates
        two useful policies."""
        assert breakeven_cost_ratio([0, 0, 0]) is None

    def test_no_legitimate_traffic_is_undefined(self) -> None:
        """With no legitimate traffic there is nothing to false-alarm on."""
        assert breakeven_cost_ratio([1, 1]) is None

    def test_no_rows_is_undefined(self) -> None:
        assert breakeven_cost_ratio([]) is None

    def test_the_answer_depends_on_prevalence_and_nothing_else(self) -> None:
        """The ratio is a property of the base rate alone.

        Two corpora with the same prevalence must give the same answer even
        though their labels sit in different rows. The function accepts no
        score array and no threshold grid, so this cannot decay back into an
        O(thresholds x rows) scan without the signature changing first.
        """
        one_percent_front = [1] + [0] * 99
        one_percent_back = [0] * 99 + [1]

        assert breakeven_cost_ratio(one_percent_front) == breakeven_cost_ratio(
            one_percent_back
        )


class TestDegenerateClassifiers:
    def test_a_perfect_classifier_costs_nothing(self) -> None:
        """The upper bound. If this is not 0.0 the arithmetic is inventing cost.

        y_true = [1, 0, 1, 0], y_score = [0.90, 0.10, 0.80, 0.20]. At t=0.5 both
        frauds are flagged and neither legitimate is: tp=2 fp=0 fn=0 tn=2.
        """
        y_true = [1, 0, 1, 0]
        y_score = [0.90, 0.10, 0.80, 0.20]

        counts = confusion_at(y_true, y_score, 0.5)
        assert counts == ConfusionCounts(tp=2, fp=0, fn=0, tn=2)
        assert expected_cost_per_transaction(counts, CHEAP_FP) == 0.0
        assert optimal_threshold(y_true, y_score, CHEAP_FP, [0.5]).threshold == 0.5

    def test_an_inverted_classifier_is_beaten_by_flagging_nothing(self) -> None:
        """The property this whole module exists to expose.

        The model has the classes backwards: frauds sit at the bottom of the
        score distribution and every legitimate transaction sits above them.

            y_true  [1,    0,    0,    0,    1,    0   ]
            y_score [0.05, 0.60, 0.70, 0.80, 0.10, 0.90]

        THE COST RATIO IS LOAD-BEARING, and the module says so out loud. At
        ``C_fn/C_fp = 1`` (below this fixture's breakeven of 2.0) flagging
        nothing costs p*C_fn = 2/6 = 0.3333 and flagging everything costs
        (1-p)*C_fp = 4/6 = 0.6667, so silence is the stronger baseline and the
        model has to beat it:

            t=0.00  all 6 flagged -> 2 TP, 4 FP, 0 FN -> 4/6 = 0.6667
            t=0.55  4 FP, 2 FN                        -> 6/6 = 1.0000
            t=0.65  3 FP, 2 FN                        -> 5/6 = 0.8333
            t=0.75  2 FP, 2 FN                        -> 4/6 = 0.6667
            t=0.85  1 FP, 2 FN                        -> 3/6 = 0.5000
            t=1.00  0 FP, 2 FN                        -> 2/6 = 0.3333  <- ties

        Every cut that flags anything is worse than doing nothing; the only one
        that ties is the cut that IS doing nothing.

        Note t=0.00: every score is >= 0.0, so both frauds are caught along
        with everything else. Flagging everything on an inverted model still
        catches every fraud, because it flags everything -- which is why the
        other test below has to exist.
        """
        y_true = [1, 0, 0, 0, 1, 0]
        y_score = [0.05, 0.60, 0.70, 0.80, 0.10, 0.90]
        grid = [0.0, 0.55, 0.65, 0.75, 0.85, 1.0]

        flag_nothing_cost = 2 / 6
        points = sweep(y_true, y_score, EVEN_COST, grid)

        flagged_something = [p for p in points if p.tp + p.fp > 0]
        assert flagged_something, "the grid never flags anything, so this proves nothing"
        for point in flagged_something:
            assert point.expected_cost_per_transaction > flag_nothing_cost, (
                f"threshold {point.threshold} claims to be worth {point.expected_cost_per_transaction}, "
                f"which beats flagging nothing ({flag_nothing_cost}) -- on an inverted classifier"
            )

        # And the cost-optimal operating point of an inverted model is to
        # review nothing at all. That sentence is the whole reason to price
        # cost: precision and recall would not have said it.
        assert optimal_threshold(y_true, y_score, EVEN_COST, grid).threshold == 1.0

    def test_an_inverted_classifier_only_matters_below_the_breakeven(self) -> None:
        """The boundary of the claim above, and why it is a boundary.

        The same inverted fixture at ``C_fn/C_fp = 100`` -- an ABSURD ratio,
        a hundred missed frauds for one wasted analyst minute -- and
        breakeven ``R*`` for p = 2/6 is exactly 2.0. So flagging everything is
        already the correct policy on an inverted model:

            flag nothing  = p * C_fn      = 2*100/6 = 33.333
            flag all      = (1-p) * C_fp  = 4*1/6   =  0.667

        The t=0.00 point below therefore BEATS flagging nothing, at 0.667.
        Nothing is wrong with the arithmetic and nothing is wrong with the
        model: a cost ratio far above breakeven makes the model irrelevant,
        because reviewing every transaction is cheaper than trusting any
        classifier.

        This is why ``breakeven_cost_ratio`` exists, and why no cost report
        may quote a single ratio as if it were measured. The claim "an
        inverted model is worse than doing nothing" is true at 1x and FALSE at
        100x on this very fixture. Only the sweep shows which regime you are in.
        """
        y_true = [1, 0, 0, 0, 1, 0]
        y_score = [0.05, 0.60, 0.70, 0.80, 0.10, 0.90]

        assert breakeven_cost_ratio(y_true) == pytest.approx(2.0)

        flag_all = sweep(y_true, y_score, CHEAP_FP, [0.0])[0]
        assert (flag_all.tp, flag_all.fp, flag_all.fn) == (2, 4, 0)
        assert flag_all.expected_cost_per_transaction == pytest.approx(4 / 6)
        # Cheaper than flagging nothing, on a model that gets every row wrong.
        assert flag_all.expected_cost_per_transaction < 200 / 6
