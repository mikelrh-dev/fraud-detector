"""Per-feature model contract for the deployed fraud classifier.

The contract has two halves, and both must hold:

1. **Variance** — every one of the 10 features must actually vary in the
   distribution the model was fit on. A constant column cannot be learned
   no matter what the model does with it, so it is a *defect*, not a
   feature to be skipped.

2. **Sensitivity** — for every feature that does vary, sweeping it across
   its observed range must move the model's risk score by more than
   :data:`SENSITIVITY_FLOOR`, with every other feature held fixed.

Why a naive version of this test is worthless here: a test that only
asserts "the model responds to ``amount``" passes *today*, by accident,
because amount carries real signal — it just is not the signal the model
ended up using. The defect in this pipeline was never "amount is
unimportant", it was "the model is blind to features the data never
varied". So the assertions are per-feature and variance-aware, and they
are evaluated across several base rows rather than a single one: a single
base can land inside a saturated tree leaf where *no* feature moves the
output, which would read as "the model ignores everything".

``SENSITIVITY_FLOOR`` is grounded in the consumer, not in whatever the
current model happens to emit. ``ml_score`` carries weight 0.25 in
``EnsembleScorer`` and the narrowest review band is
``threshold * 0.75``, i.e. 10 points wide at the tightest tier. One
``ml_score`` point is therefore worth 0.25 ensemble points, and a feature
that can move ``ml_score`` by less than 0.5 points contributes under
0.125 ensemble points — two orders of magnitude below any decision
boundary, so it cannot participate in a decision at all.
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pytest
from sklearn.model_selection import train_test_split

from src.services.feature_engine import FEATURE_NAMES
from src.services.ml_model import MLModelService

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = REPO_ROOT / "models" / "xgboost_paysim_v1.joblib"
SYNTHETIC_CSV = REPO_ROOT / "data" / "synthetic_transactions.csv"

#: Minimum movement in risk-score points (0-100) a feature must be able to
#: produce somewhere in its observed range. See module docstring.
SENSITIVITY_FLOOR = 0.5

#: No live feature may be more than this much less sensitive than the
#: median live feature. Catches "the model uses nine of the ten".
RELATIVE_FLOOR = 0.05

#: How many real data rows to use as sweep bases.
N_BASES = 40

#: Split parameters used by ``train_xgboost_aligned.main()``. Duplicated from
#: ``scripts/evaluate_model.py`` on purpose: the calibration test has to name
#: the split the calibrator saw, and a shared constant imported from the
#: training script would make the test tautological — if training changed the
#: split, the test would follow and assert nothing. The duplication is the
#: assertion.
TEST_SIZE = 0.2
SPLIT_SEED = 42


def _load_training_module():
    """Import the training script so the contract is measured on the
    distribution the model was actually fit on, not on a re-implementation
    of it that could silently drift."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import train_xgboost_aligned  # noqa: PLC0415

    return train_xgboost_aligned


def _sweep_endpoints(column: np.ndarray) -> tuple[float, float]:
    """Low/high values to sweep a feature across.

    Binary-ish columns (merchant_risk_level, is_crypto, is_weekend,
    amount_round_number) collapse under percentiles, so sweep min->max for
    anything with a handful of distinct values.
    """
    distinct = np.unique(column)
    if distinct.size <= 3:
        return float(column.min()), float(column.max())
    return float(np.percentile(column, 5)), float(np.percentile(column, 95))


@pytest.fixture(scope="module")
def contract_env():
    """Model service, the training matrix, and the per-feature report."""
    if not MODEL_PATH.exists():
        pytest.skip(f"deployed model not present at {MODEL_PATH}")

    trainer = _load_training_module()
    service = MLModelService(model_path=str(MODEL_PATH))
    if not service.load_model():
        pytest.skip("deployed model failed to load")

    X, y = trainer.build_training_matrix()
    return trainer, service, X, y


def _measure(service, X, y) -> dict[str, dict[str, float]]:
    """Sweep every feature from several real base rows and report the
    largest score movement each one produced."""
    rng = np.random.RandomState(0)
    # Bases span the whole label mix, not just the median row, so a feature
    # that only matters in the high-risk region still gets found.
    fraud_idx = np.flatnonzero(y == 1)
    legit_idx = np.flatnonzero(y == 0)
    n_legit = max(1, N_BASES - N_BASES // 3)
    bases = np.concatenate([
        rng.choice(legit_idx, size=min(n_legit, legit_idx.size), replace=False),
        rng.choice(fraud_idx, size=min(N_BASES - n_legit, fraud_idx.size), replace=False),
    ])

    report: dict[str, dict[str, float]] = {}
    for i, name in enumerate(FEATURE_NAMES):
        column = X[:, i]
        if column.std() == 0.0:
            report[name] = {"variance": 0.0, "sensitivity": 0.0}
            continue
        lo, hi = _sweep_endpoints(column)
        best = 0.0
        for b in bases:
            low_vec = X[b].copy()
            high_vec = X[b].copy()
            low_vec[i] = lo
            high_vec[i] = hi
            movement = abs(service.predict(high_vec) - service.predict(low_vec))
            best = max(best, movement)
        report[name] = {"variance": float(column.std()), "sensitivity": float(best)}
    return report


class TestModelFeatureContract:
    """The deployed model must use every feature it is given."""

    def test_every_feature_varies_in_the_training_data(self, contract_env):
        """No feature may be a constant column.

        A constant column carries no information, so the model cannot have
        learned anything from it. It is reported as a defect with the
        measured std, not skipped.
        """
        _, _, X, _ = contract_env
        dead = {
            name: float(X[:, i].std())
            for i, name in enumerate(FEATURE_NAMES)
            if X[:, i].std() == 0.0
        }
        assert not dead, (
            "constant features in the training data — the model cannot have "
            f"learned these, and the artifact is weighting them anyway: {dead}"
        )

    def test_every_feature_moves_the_model_output(self, contract_env):
        """Sweeping each feature across its observed range must move the
        risk score by more than SENSITIVITY_FLOOR."""
        _, service, X, y = contract_env
        report = _measure(service, X, y)

        inert = {
            name: report[name]["sensitivity"]
            for name in FEATURE_NAMES
            if report[name]["sensitivity"] <= SENSITIVITY_FLOOR
        }
        live = sorted(
            report[n]["sensitivity"] for n in FEATURE_NAMES
            if report[n]["sensitivity"] > SENSITIVITY_FLOOR
        )
        measured = ", ".join(
            f"{n}={report[n]['sensitivity']:.4f}" for n in FEATURE_NAMES
        )
        spread = (
            f"live range: {live[0]:.4f}..{live[-1]:.4f}" if live
            else "NO feature is live — the model is inert on every feature"
        )
        assert not inert, (
            f"features that do not move the risk score (floor "
            f"{SENSITIVITY_FLOOR}): {inert}\n"
            f"measured across all 10 features: {measured}\n{spread}"
        )

    def test_no_feature_is_an_order_of_magnitude_below_the_others(
        self, contract_env
    ):
        """Catch the failure mode where nine features work and one is ignored.

        This is the specific regression that produced the original defect:
        a model that finds one perfectly-separating feature first and
        effectively ignores the rest.
        """
        _, service, X, y = contract_env
        report = _measure(service, X, y)
        live = {
            name: report[name]["sensitivity"]
            for name in FEATURE_NAMES
            if report[name]["variance"] > 0.0
        }
        assert live, "no feature has variance — cannot compare sensitivities"
        median = float(np.median(list(live.values())))
        floor = median * RELATIVE_FLOOR
        starved = {n: v for n, v in live.items() if v < floor}
        measured = ", ".join(f"{n}={v:.4f}" for n, v in live.items())
        assert not starved, (
            f"features starved relative to the median live sensitivity "
            f"({median:.4f}, floor {floor:.4f}): {starved}\n"
            f"measured: {measured}"
        )

    def test_reported_sensitivity_range_is_not_degenerate(self, contract_env):
        """Record the measured spread so a silent collapse to a single
        dominating feature is visible in the test log, not just in a
        dashboard nobody opens."""
        _, service, X, y = contract_env
        report = _measure(service, X, y)
        values = [report[n]["sensitivity"] for n in FEATURE_NAMES]
        live = sorted(v for v in values if v > 0.0)
        assert live, "every feature is inert"
        print(
            f"\nper-feature sensitivity (floor={SENSITIVITY_FLOOR}): "
            + ", ".join(
                f"{n}={report[n]['sensitivity']:.4f}" for n in FEATURE_NAMES
            )
            + f"\n  live range {live[0]:.4f} .. {live[-1]:.4f} "
              f"(spread {live[-1] / live[0]:.1f}x)"
        )
        assert live[-1] > SENSITIVITY_FLOOR


class TestModelCalibrationContract:
    """The deployed artifact's absolute probabilities must be calibrated (CAL-001).

    ``ml_score`` is a probability multiplied by 100, and ``EnsembleScorer``
    thresholds it as one. So the number is only usable if it is a *calibrated*
    probability against the prior that will actually be seen at serve time.

    A calibrator learns P(y=1 | score) from whatever matrix it is shown. The
    artifact that shipped before this contract existed had been calibrated on
    a SMOTE-resampled matrix at a 33% fraud prior, so every score was inflated
    by roughly the resampling ratio: the top bin predicted 0.98 against an
    observed 0.69 on held-out un-resampled data.

    Resampling before calibrating is invisible from the artifact itself, which
    is why it survived five training runs. The artifact now records the prior
    its calibrator was fit against, and these tests read it back.
    """

    def test_artifact_records_the_prior_its_calibrator_saw(self):
        """The stamp must exist. An artifact without it predates CAL-001.

        Falsifiable: the previous artifact, produced by
        ``train_xgboost_aligned.main()`` before the resampling step was
        removed, carries no ``calibration_prior`` key and fails here.
        """
        if not MODEL_PATH.exists():
            pytest.skip(f"deployed model not present at {MODEL_PATH}")

        artifact = joblib.load(MODEL_PATH)
        assert isinstance(artifact, dict), (
            "deployed artifact is a bare estimator with no provenance stamp; "
            "nothing in it says which class prior its probabilities are "
            "calibrated against"
        )
        assert "calibration_prior" in artifact, (
            "deployed artifact carries no calibration_prior stamp. A "
            "calibrator fit on resampled data is calibrated to the resampler's "
            "prior rather than the data's, and there is no way to detect that "
            "from an unstamped file."
        )
        assert 0.0 < float(artifact["calibration_prior"]) < 1.0

    def test_calibration_prior_matches_the_corpus_prevalence(self, contract_env):
        """The recorded prior must be the corpus's own, not a resampler's.

        The expected figure is the prior of the *training split of the real
        training matrix* — the same object the calibrator is handed — rather
        than the whole corpus. A stratified split puts 385 of the corpus's 481
        frauds in train, so the two priors differ by ~5e-6 for reasons that
        have nothing to do with calibration. What a resampler would move is
        the prior of the matrix the calibrator actually saw, and that is the
        number compared here.

        ``build_training_matrix()`` is used rather than a raw CSV read so the
        comparison stays exact if PaySim is present: the trainer concatenates
        it, and a comparison against the synthetic rows alone would then be
        asserting a coincidence.
        """
        artifact = joblib.load(MODEL_PATH)
        assert "calibration_prior" in artifact, "no calibration_prior stamp"

        _, _, X, y = contract_env
        X_train, _, y_train, _ = train_test_split(
            X, y, test_size=TEST_SIZE, random_state=SPLIT_SEED, stratify=y
        )
        assert len(X_train) > 0
        expected_prior = float(np.mean(y_train))
        stamp = float(artifact["calibration_prior"])

        assert abs(stamp - expected_prior) < 1e-9, (
            f"artifact calibration_prior {stamp:.9f} != training split prior "
            f"{expected_prior:.9f}. The calibrator was fit on a matrix whose "
            f"class prior differed from the data's, which means the absolute "
            f"probabilities are calibrated to a base rate that will not occur "
            f"at serve time (CAL-001)."
        )
        assert 0.005 < stamp < 0.05, (
            f"calibration_prior {stamp:.4f} is not a plausible card-not-present "
            f"prevalence; the training split's is {expected_prior:.4f}"
        )
