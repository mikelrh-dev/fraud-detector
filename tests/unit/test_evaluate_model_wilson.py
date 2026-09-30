"""Pin `scripts.evaluate_model.wilson_interval` to an independent implementation.

WHY THIS TEST EXISTS. The README quotes a 95% Wilson interval next to its
precision and recall figures and tells the reader to reproduce both with
`python scripts/evaluate_model.py`. That sentence was false when it was
written: the script computed no interval at all, so the interval existed only
as prose in the README — the same "reproducibility claim that does not
reproduce" defect the surrounding section was rewritten to remove.

A closed-form interval is exactly the kind of arithmetic that is easy to get
subtly wrong and hard to notice, so it is pinned here against reference values
taken from `statsmodels.stats.proportion.proportion_confint(method="wilson")`,
which is an independent implementation. statsmodels is deliberately NOT
imported at test time: it is present in the local venv but absent from both
requirements files, so importing it would make the suite pass here and fail in
CI. The expected values are frozen below instead.
"""

import math

import pytest

from scripts.evaluate_model import wilson_interval

# (successes, n) -> (low, high), from statsmodels 0.14.6 proportion_confint.
# The first two rows are the ones the README quotes.
REFERENCE = [
    (71, 85, 0.742317, 0.899275),
    (71, 100, 0.614611, 0.789852),
    (0, 100, 0.000000, 0.036993),
    (100, 100, 0.963007, 1.000000),
    (1, 3, 0.061492, 0.792340),
]


@pytest.mark.parametrize(("k", "n", "low", "high"), REFERENCE)
def test_matches_independent_implementation(k: int, n: int, low: float, high: float) -> None:
    got_low, got_high = wilson_interval(k, n)
    assert got_low == pytest.approx(low, abs=1e-6)
    assert got_high == pytest.approx(high, abs=1e-6)


@pytest.mark.parametrize(("k", "n"), [(k, n) for k, n, _, _ in REFERENCE])
def test_brackets_the_point_estimate(k: int, n: int) -> None:
    """A 95% interval that excludes the estimate it is an interval for is
    not a conservative interval — it is a broken one."""
    low, high = wilson_interval(k, n)
    p = k / n
    assert low <= p <= high, f"{p} outside [{low}, {high}]"


@pytest.mark.parametrize(("k", "n"), [(k, n) for k, n, _, _ in REFERENCE])
def test_bounds_stay_inside_the_unit_interval(k: int, n: int) -> None:
    """This is the whole reason Wilson is used instead of the normal
    approximation: at ~1% prevalence with double-digit true positives, the
    normal approximation returns bounds outside [0, 1]."""
    low, high = wilson_interval(k, n)
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0


def test_zero_count_interval_does_not_touch_one() -> None:
    """Zero successes out of n is a real observation, not no data: the upper
    bound still excludes 1 whenever n is large enough to rule it out."""
    low, high = wilson_interval(0, 100)
    assert low == 0.0
    assert 0.0 < high < 0.05


def test_interval_narrows_as_the_sample_grows() -> None:
    """A fixed p at growing n must converge on p — otherwise the interval is
    not reporting precision at all."""
    widths = []
    for n in (100, 1000, 10000):
        low, high = wilson_interval(round(n * 0.71), n)
        widths.append(high - low)
    assert widths[0] > widths[1] > widths[2]
    assert widths[-1] < 0.03, f"n=10000 width {widths[-1]:.4f} did not reach 3 points"


def test_degenerate_input_is_nan_not_a_crash() -> None:
    """A split with no positives has no proportion to bound. Returning NaN
    lets the caller skip it; raising would take the whole report down."""
    low, high = wilson_interval(0, 0)
    assert math.isnan(low) and math.isnan(high)
