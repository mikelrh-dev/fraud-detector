"""Amount-response contract: risk must not fall as amount rises on a wire path.

The gap this fills
------------------
``tests/test_model_feature_contract.py`` (8d78e44) checks that every feature
*varying* moves the output, and that no feature separates the classes. It
cannot catch an inverted response, because the inverted model *did* respond
to ``amount`` — it responded in the wrong direction. Sensitivity and
direction are different properties, and only the first was under test.

Measured on the artifact that shipped at 4006aad, sweeping amount on a
crypto / 03:00 path with every other feature held fixed:

    $1,000 -> 84.36     $10,000 -> 77.24    $100,000 -> 47.72
    $2,000 -> 84.62     $50,000 -> 49.07    $1,000,000 -> 41.78

The response peaked at $2,000 and then fell monotonically to $1,000,000, so a
$1,000,000 crypto transfer scored less than half of a $5,000 one. The ML layer
ranked the highest-value transfer as the safest. Root cause was the corpus
(AMT-001); the corpus is fixed, and this contract is what stops it returning.

Why the path is a *wire* path and not a burst path
--------------------------------------------------
The honest answer is that the amount response is not monotone in every
velocity regime, and pretending otherwise would be a test that asserts
something false about fraud.

At burst-level velocity — a dozen transactions inside five minutes at a crypto
exchange at 03:00 — *many small transactions is the fraud signature*. That is
card testing, and it is a real pattern. A model that scores a $10 burst
higher than a $1,000,000 one is behaving correctly there, not defectively.
So the strong monotonicity contract is asserted on the wire and mule regimes,
where amount genuinely is the discriminating variable, and the burst regime
gets a separate, coarser assertion plus an explicit write-up of the exception
rather than a silent omission.

Measured on the artifact that shipped at 4006aad and on the AMT-001 retrain,
across all four regimes (crypto, 03:00, avg $200, std $500). "peak-trough" is
the depth of the response, i.e. the largest amount-driven swing in the score:

    regime                 4006aad $10 -> $1,000,000    retrain $10 -> $1,000,000
    quiet    v5=1  v1=4    0.16 -> 80.34  (saturated)    0.18 -> 77.43
    elevated v5=4  v1=18   0.15 ->  6.10  INVERTED       0.14 -> 73.47
    burst    v5=10 v1=50  84.53 -> 41.78  INVERTED      80.20 -> 77.62
    heavy    v5=18 v1=80  84.98 -> 84.37  (saturated)   81.27 -> 81.27

    peak-to-trough depth:
    regime                 4006aad   retrain
    quiet                     80.81     77.25
    elevated                  40.66     73.33
    burst                     42.75     18.26
    heavy                      0.61      0.21

    On 4006aad the elevated path peaked at $5,000 (40.81) and fell to 5.93 at
    $50,000, and the burst path peaked at $100 (84.53) and fell to 41.78 at
    $1,000,000. The quiet and heavy paths were already saturated on 4006aad,
    which is why ``test_wire_path_response_is_non_decreasing`` passes on the
    defective artifact: its tail-off is 0.63 points, inside the tolerance. The
    discriminating assertions on 4006aad are
    ``test_elevated_velocity_response_is_non_decreasing`` (34.88-point drop)
    and ``test_burst_path_does_not_invert_catastrophically`` (42.75 > 40). On
    the retrain, all seven pass.

The tolerance, derived from the consumer
----------------------------------------
:data:`NON_MONOTONICITY_TOLERANCE` is 1.0 risk-score point, derived from the
ensemble's decision geometry rather than from whatever the current model
emits — the same shape as ``SENSITIVITY_FLOOR`` in the sibling contract.

``ml_score`` enters ``EnsembleScorer`` at weight 0.25
(``settings.ensemble_ml_weight``). The decision boundaries are ``review`` at
``threshold * 0.75`` and ``fraud`` at ``threshold``, over the amount tiers
70 / 50 / 45 / 40. The tightest tier therefore places its two boundaries 10
ensemble points apart (30 and 40), and **10 is the narrowest gap between any
two adjacent boundaries anywhere in the system.**

``EnsembleScorer`` renormalises the weights of whichever layers produced a
signal to sum to 1, so ``ml_score`` carries 0.25 when rule, ML and context all
speak, and up to 1.0 when it is the only live layer. A decrease of D points in
``ml_score`` moves the ensemble by somewhere in [0.25 D, 1.0 D]. To reorder a
classification even in the worst case, D must exceed 10 risk points; nominally
it would have to exceed 40. We allow 1.0 — an order of magnitude inside the
worst case, forty-fold inside the nominal one — so no inversion this test
admits can move a transaction across a boundary. It is loose enough to absorb
the exact plateaus a tree ensemble produces: stepping $500,000 -> $1,000,000
lands in the same leaf and returns a bit-identical score.

What this test does NOT establish
---------------------------------
Read this before treating a green run as evidence the model works.

1. **It is three paths, not the space.** ``amount`` is swept with the other
   nine inputs pinned to three fixed merchant/velocity/hour configurations. A
   model can be monotone on all three and inverted on a dozen others —
   different merchants, different user histories, different amounts relative
   to the user's own baseline. Passing is one necessary condition, not a
   sufficient one.
2. **It cannot be evidence of real-world detection.** The corpus is
   synthetic, written by the same author as the features. Monotonicity here is
   *internal consistency* — the model agrees with the design intent encoded in
   the corpus. It says nothing about whether any of it transfers to real
   transactions, and it is not a substitute for a labelled real corpus. The
   model has never seen a real fraudulent transaction.
3. **It says nothing about calibration.** A perfectly monotone model can
   still emit systematically wrong probabilities. That is a separate contract
   (``TestModelCalibrationContract``).
4. **Non-decreasing is weaker than correct.** A flat response — the model
   refusing to let amount matter at all — passes the strong assertions. That
   is why the liveness assertions exist: they require the sweep to span a
   range and to end above where it started, so the contract cannot pass
   vacuously against an inert model.
5. **The burst regime is not covered by the strong contract, and is not
   covered fully by the coarse one.** ``test_the_burst_path_does_not_invert``
   only bounds the *depth* of the trough. It does not assert the shape, and
   the response there is genuinely non-monotone by design. A future corpus
   change could make the burst response worse in character while still
   passing the depth bound.
6. **It does not detect a wrong threshold policy.** Whether 40 is the right
   value for the last tier's boundary is a risk decision for a human.
"""

import os
from pathlib import Path

import pytest

from src.services.feature_engine import FeatureEngine
from src.services.ml_model import MLModelService

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The deployed artifact. Overridable so the contract can be pointed at a
#: historical artifact to demonstrate that it actually fails on the defect it
#: was written for — a regression guard nobody has ever seen fail is not
#: known to be a guard.
MODEL_PATH = Path(
    os.environ.get("FRAUD_MODEL_PATH", REPO_ROOT / "models" / "xgboost_paysim_v1.joblib")
)

#: Permitted decrease between adjacent sweep points, in risk-score points
#: (0-100). See the module docstring for the derivation.
NON_MONOTONICITY_TOLERANCE = 1.0

#: Permitted peak-to-trough depth of the amount response on the burst path.
#: 40 risk points is the worst case in which an ml_score decrease can reorder
#: a classification at all: the narrowest boundary gap is 10 ensemble points,
#: and the ML layer's weight renormalises to 1.0 when it is the only live
#: layer. Anything deeper than this is a response that would, by itself,
#: reorder real decisions.
BURST_PATH_MAX_DEPTH = 40.0

#: A geometric ladder, one step per half-decade, from a routine transfer to
#: the corpus's ``MAX_AMOUNT`` ceiling. Geometric rather than linear because
#: the defect lived between $2,000 and $1,000,000 — a linear ladder over that
#: span spends most of its points on amounts nobody transacts at.
RISK_PATH_AMOUNTS = (
    10.0, 100.0, 500.0, 1_000.0, 5_000.0, 10_000.0, 50_000.0,
    100_000.0, 250_000.0, 500_000.0, 1_000_000.0,
)

#: The transaction under the sweep is fixed: a crypto exchange transfer at
#: 03:00, i.e. the merchant, the hour and the risk level are held constant and
#: only amount varies. User history is fixed at a $200 average with a $500
#: standard deviation, so `amount_vs_user_avg` and `amount_vs_user_std` move
#: with amount exactly as they do in production.
SWEEP_TX = {
    "merchant_category": "cryptocurrency",
    "timestamp": "2024-01-15T03:00:00+00:00",
}
SWEEP_HISTORY_BASE = {"avg_amount": 200.0, "std_amount": 500.0}

#: velocity regime -> (tx_count_last_5min, tx_count_last_1h).
#:   quiet     a wire: one transfer, nothing else happening
#:   elevated  a compromised account or a mule, mildly active
#:   burst     a dozen transactions in five minutes: the card-testing regime
#:   heavy     saturated; the model treats velocity as decisive on its own
VELOCITY_REGIMES = {
    "quiet": (1, 4),
    "elevated": (4, 18),
    "burst": (10, 50),
    "heavy": (18, 80),
}

#: Minimum spread a sweep must exhibit for a monotonicity assertion to carry
#: meaning. 10 risk points is 40 ensemble points at weight 0.25 and four
#: times the narrowest boundary gap, so a model that cannot move this much
#: along the path is inert rather than monotone.
MIN_LIVE_SPAN = 10.0


def _sweep(service, engine, v5: int, v1: int) -> list[tuple[float, float]]:
    history = {**SWEEP_HISTORY_BASE, "tx_count_last_5min": v5, "tx_count_last_1h": v1}
    return [
        (amount, service.predict(engine.transform(
            {**SWEEP_TX, "amount": amount}, user_history=history)))
        for amount in RISK_PATH_AMOUNTS
    ]


def _format(sweep: list[tuple[float, float]]) -> str:
    return ", ".join(f"${a:,.0f}->{s:.2f}" for a, s in sweep)


@pytest.fixture(scope="module")
def service() -> MLModelService:
    if not MODEL_PATH.exists():
        pytest.skip(f"model not present at {MODEL_PATH}")
    svc = MLModelService(model_path=str(MODEL_PATH))
    if not svc.load_model():
        pytest.skip(f"model at {MODEL_PATH} failed to load")
    return svc


@pytest.fixture(scope="module")
def sweeps(service) -> dict[str, list[tuple[float, float]]]:
    engine = FeatureEngine()
    return {name: _sweep(service, engine, v5, v1) for name, (v5, v1) in VELOCITY_REGIMES.items()}


def _assert_monotone(sweep: list[tuple[float, float]], regime: str) -> None:
    violations = [
        (lo, hi, s_lo, s_hi, s_lo - s_hi)
        for (lo, s_lo), (hi, s_hi) in zip(sweep, sweep[1:])
        if s_hi < s_lo - NON_MONOTONICITY_TOLERANCE
    ]
    assert not violations, (
        f"risk fell as amount rose on the {regime!r} velocity path "
        f"(tolerance {NON_MONOTONICITY_TOLERANCE} point(s)):\n"
        + "\n".join(
            f"  ${lo:,.0f} -> ${hi:,.0f}: {s_lo:.2f} -> {s_hi:.2f} ({drop:.2f} point drop)"
            for lo, hi, s_lo, s_hi, drop in violations
        )
        + f"\nfull sweep: {_format(sweep)}\n"
        "High-value transfer fraud is a real pattern; a model that ranks a "
        "large crypto transfer as safer than a mid-value one is mis-ranking "
        "the single most valuable thing it could catch."
    )


def _assert_live_and_rising(sweep: list[tuple[float, float]], regime: str) -> None:
    scores = [s for _, s in sweep]
    span = max(scores) - min(scores)
    assert span >= MIN_LIVE_SPAN, (
        f"the {regime!r} path spans only {span:.2f} risk points across "
        f"${RISK_PATH_AMOUNTS[0]:,.0f}-${RISK_PATH_AMOUNTS[-1]:,.0f}, below the "
        f"{MIN_LIVE_SPAN} needed for a monotonicity assertion to mean anything. "
        f"The model is inert on amount here, so 'non-decreasing' would pass for "
        f"the wrong reason.\nmeasured: {_format(sweep)}"
    )
    assert scores[-1] > scores[0], (
        f"the top of the {regime!r} sweep scores no higher than the bottom "
        f"(${RISK_PATH_AMOUNTS[0]:,.0f} -> {scores[0]:.2f}, "
        f"${RISK_PATH_AMOUNTS[-1]:,.0f} -> {scores[-1]:.2f}). The path is live "
        f"but not rising, so the model treats amount as uninformative here "
        f"rather than as evidence.\nmeasured: {_format(sweep)}"
    )


class TestAmountResponseOnWirePaths:
    """Risk must not fall as amount rises where amount is the signal.

    A wire and a mule transfer are the high-value fraud vectors this system
    exists to catch, and in that regime amount is the discriminating variable
    rather than an incidental one. Monotonicity is a design invariant here.
    """

    def test_wire_path_response_is_non_decreasing(self, sweeps):
        """A single quiet wire: risk must not fall as the amount grows."""
        _assert_monotone(sweeps["quiet"], "quiet")

    def test_elevated_velocity_response_is_non_decreasing(self, sweeps):
        """A compromised account or mule, mildly active: same invariant."""
        _assert_monotone(sweeps["elevated"], "elevated")

    def test_wire_path_is_live_and_rising(self, sweeps):
        """Guard the guard: an inert or flat model must not pass as monotone."""
        _assert_live_and_rising(sweeps["quiet"], "quiet")

    def test_elevated_velocity_path_is_live_and_rising(self, sweeps):
        """Guard the guard, for the elevated regime."""
        _assert_live_and_rising(sweeps["elevated"], "elevated")


class TestAmountResponseOnBurstPath:
    """The burst regime is excluded from the strong contract, on purpose.

    At burst velocity the amount prior genuinely runs the other way: card
    testing is many small transactions, so a $10 burst at a crypto exchange
    at 03:00 is more suspicious than a $1,000,000 one, and a model that says
    so is right. Asserting strict monotonicity here would assert something
    false about fraud.

    What is asserted instead is the *depth* of the trough. The defect at
    4006aad was not merely non-monotonicity on this path, it was a 42.75-point
    collapse from 84.53 at $100 down to 41.78 at $1,000,000 — a response that
    would, on its own, reorder every decision it touched. Any depth beyond
    :data:`BURST_PATH_MAX_DEPTH` is that same failure again.
    """

    def test_burst_path_does_not_invert_catastrophically(self, sweeps):
        """The peak-to-trough depth on a card-testing burst stays bounded."""
        sweep = sweeps["burst"]
        scores = [s for _, s in sweep]
        depth = max(scores) - min(scores)
        assert depth <= BURST_PATH_MAX_DEPTH, (
            f"the burst path drops {depth:.2f} risk points from its peak to its "
            f"trough, beyond the {BURST_PATH_MAX_DEPTH} that could be explained "
            f"by decision geometry alone. At this depth the amount response "
            f"drives decisions by itself.\nmeasured: {_format(sweep)}"
        )

    def test_burst_path_ends_above_its_trough(self, sweeps):
        """The top of the range must not be the lowest point on the path.

        This is the specific shape of the original defect: the maximum-value
        transfer was the *safest* transaction on the path. It does not require
        strict monotonicity, which would be false here, only that the largest
        amount is not the cheapest to let through.
        """
        sweep = sweeps["burst"]
        scores = [s for _, s in sweep]
        assert scores[-1] >= min(scores) - NON_MONOTONICITY_TOLERANCE, (
            f"the largest amount on the burst path scores {scores[-1]:.2f}, "
            f"below the path minimum {min(scores):.2f}. The highest-value "
            f"transfer is being ranked the safest transaction of the set.\n"
            f"measured: {_format(sweep)}"
        )

    def test_burst_path_is_live(self, sweeps):
        """The burst path must still respond to amount at all.

        At saturation the model treats velocity as decisive and amount as
        noise, which is legitimate — but then this contract says nothing about
        the burst regime, and that should be visible rather than assumed.
        """
        sweep = sweeps["burst"]
        scores = [s for _, s in sweep]
        span = max(scores) - min(scores)
        assert span >= MIN_LIVE_SPAN, (
            f"the burst path spans only {span:.2f} risk points across "
            f"${RISK_PATH_AMOUNTS[0]:,.0f}-${RISK_PATH_AMOUNTS[-1]:,.0f}: the "
            f"model has saturated on velocity and is not reading amount at all. "
            f"That is defensible for a genuine card-testing burst, but it means "
            f"no amount-based assertion can be made about this regime at all.\n"
            f"measured: {_format(sweep)}"
        )
