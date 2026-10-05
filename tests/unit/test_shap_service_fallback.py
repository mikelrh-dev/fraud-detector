"""Fallback-explainer tests for :mod:`src.services.shap_service`.

The bug these tests exist for
---------------------------
``models/xgboost_paysim_v1.joblib`` is a **dict** with keys
``model``/``feature_names``/``calibration_prior``/... wrapping a
``CalibratedClassifierCV`` (``scripts/train_xgboost_aligned.py``). The service
fed that whole dict to ``shap.TreeExplainer``, which raises
``InvalidModelError: Model type not yet supported``. The worker caught
``ShapUnavailableError``, ACKed the message and wrote **zero**
``shap_attribution`` rows, while ``/health/workers`` still said "ok" because its
only signal is consumer-group pending depth — which that path drains. SHAP had
never produced a single attribution and nothing could contradict that.

The integration test at the bottom of this file is the one that makes the bug
class unreintroducible: it builds a real explainer over the real artifact and
asserts additivity, so "the explainer built, therefore the contributions
decompose the served probability" is checked, never assumed.

What is pinned here
-------------------
* the dict artifact is unwrapped, and a bare artifact passes through
* ``feature_names`` is captured from the artifact and used when the caller
  sends none
* the **tree** path calls ``.shap_values(...)`` and never ``__call__``; only
  the callable fallback uses ``__call__``. The mode is returned by the builder
  and dispatched in ``explain()`` — not sniffed per call, because the tree and
  callable explainers take different input shapes too (1-D vs 2-D).
* the fallback is NOT a blanket ``except``: no ``predict_proba`` or a zero
  ``n_features_in_`` re-raises the original failure as ``ShapUnavailableError``
* exact-vs-permutation algorithm choice, asserted without paying for an
  explanation
* output-shape normalization: 3-D class index 1, 2-D row 0, list index 1

The lazy ``importlib`` shap import is exercised through a fake shap module, so
these unit tests run without shap installed.
"""

import importlib
import logging
from pathlib import Path
from unittest.mock import patch

import joblib  # type: ignore[import-untyped]
import numpy as np
import pytest

from src.services.shap_service import (
    MODE_CALLABLE,
    MODE_TREE,
    ShapService,
    ShapUnavailableError,
)

FEATURE_NAMES = [
    "amount",
    "amount_vs_user_avg",
    "amount_vs_user_std",
    "tx_count_last_5min",
    "tx_count_last_1h",
    "hour_of_day",
    "is_weekend",
    "merchant_risk_level",
    "is_crypto",
    "amount_round_number",
]

N_FEATURES = len(FEATURE_NAMES)

REAL_MODEL_PATH = Path("models/xgboost_paysim_v1.joblib")


# ---------------------------------------------------------------------------
# Picklable model doubles. Module-level because joblib round-trips them.
# ---------------------------------------------------------------------------


class TreeCapableModel:
    """What a real XGBoost artifact looks like to the tree path.

    ``marker`` survives the joblib round-trip and identifies *which* instance
    reached the explainer — ``joblib.load`` returns a fresh object, so identity
    comparison against the in-memory instance cannot work.
    """

    n_features_in_ = N_FEATURES

    def __init__(self, marker: str = "tree-capable") -> None:
        self.marker = marker

    def predict_proba(self, X):  # pragma: no cover - never called on tree path
        return np.tile([0.5, 0.5], (len(X), 1))


class NoProbaModel:
    """An estimator the callable fallback cannot wrap: no ``predict_proba``."""

    n_features_in_ = N_FEATURES

    def __init__(self, marker: str = "no-proba") -> None:
        self.marker = marker


class ZeroFeatureModel:
    """``n_features_in_ == 0`` means shap cannot build a background matrix."""

    n_features_in_ = 0

    def __init__(self, marker: str = "zero-features") -> None:
        self.marker = marker

    def predict_proba(self, X):  # pragma: no cover - never reached
        return np.tile([0.5, 0.5], (len(X), 1))


# ---------------------------------------------------------------------------
# Explainer doubles — each asserts which entry point explain() is allowed to use
# ---------------------------------------------------------------------------


class TreeExplainerDouble:
    """Tree-path double: ``.shap_values`` works, ``__call__`` is forbidden."""

    def __init__(self, values) -> None:
        self._values = values
        self.shap_values_calls = 0

    def shap_values(self, features):
        self.shap_values_calls += 1
        self.last_features = features
        return self._values

    def __call__(self, *args, **kwargs):
        raise AssertionError(
            "the tree path must use .shap_values(); __call__ is the callable "
            "fallback's entry point only"
        )


class CallableExplainerDouble:
    """Callable-fallback double: ``__call__`` works, ``.shap_values`` forbidden."""

    def __init__(self, values) -> None:
        self._values = values
        self.call_calls = 0

    def __call__(self, row):
        self.call_calls += 1
        self.last_row = row
        return self._values

    def shap_values(self, features):  # pragma: no cover - must never be reached
        raise AssertionError(
            "the callable fallback must use __call__(); .shap_values() is the "
            "tree path's entry point only"
        )


class ExplanationLike:
    """Duck-typed ``shap.Explanation``: real numbers live behind ``.values``.

    shap 0.46 returns an ``Explanation`` (an ndarray subclass) whose
    ``np.asarray()`` conversion is **object dtype** — every element is an
    ``Explanation`` again. Handing that straight to ``float()`` raises
    ``TypeError``. This double reproduces the shape of that trap so the
    normalization contract is tested without shap installed; the integration
    test proves it against real shap.
    """

    def __init__(self, values, base_values=None) -> None:
        self.values = np.asarray(values, dtype=float)
        self.base_values = base_values


# ---------------------------------------------------------------------------
# Fake shap module
# ---------------------------------------------------------------------------


class FakeShap:
    """Stands in for the ``shap`` module inside the lazy ``importlib`` import.

    ``tree_explainer`` is either an instance to hand back or an exception to
    raise, which is how the real ``InvalidModelError`` is reproduced.
    """

    class maskers:  # noqa: N801 - mirrors the real shap namespace
        Independent = staticmethod(lambda background: ("independent", background))

    def __init__(self, tree_explainer=None, callable_values=None) -> None:
        self.tree_explainer = tree_explainer
        self.callable_values = (
            np.zeros((1, N_FEATURES, 2)) if callable_values is None else callable_values
        )
        self.tree_models = []
        self.explainer_calls = []

    def TreeExplainer(self, model):  # noqa: N802 - mirrors the real shap API
        self.tree_models.append(model)
        # NOTE: deliberately no "callable means factory" branch here. Both
        # doubles define ``__call__`` as a guard, so a factory branch would
        # invoke the double instead of returning it.
        if isinstance(self.tree_explainer, BaseException):
            raise self.tree_explainer
        return self.tree_explainer

    def Explainer(self, fn, masker, algorithm=None):  # noqa: N802 - real shap API
        self.explainer_calls.append(
            {"fn": fn, "masker": masker, "algorithm": algorithm}
        )
        return CallableExplainerDouble(self.callable_values)


def _patch_shap(fake_shap):
    """Yield a context where ``importlib.import_module("shap")`` returns the fake.

    Delegates to the real importlib for every other name so joblib can still
    unpickle the model inside the patch.
    """
    original = importlib.import_module

    def _import(name, *args, **kwargs):
        if name == "shap":
            return fake_shap
        return original(name, *args, **kwargs)

    return patch("importlib.import_module", side_effect=_import)


def _service_for(tmp_path, model, fake_shap, filename="model.joblib"):
    """A service whose artifact on disk is ``model`` and whose shap is the fake."""
    path = tmp_path / filename
    joblib.dump(model, path)
    return ShapService(model_path=str(path)), path


def _artifact(model, feature_names=FEATURE_NAMES):
    """The shipped artifact layout: a dict wrapping the estimator."""
    return {
        "model": model,
        "feature_names": list(feature_names) if feature_names else None,
        "calibration_prior": 0.0021,
        "calibration_method": "sigmoid",
        "calibration_cv": 5,
    }


# ---------------------------------------------------------------------------
# Artifact unwrapping
# ---------------------------------------------------------------------------


class TestArtifactUnwrapping:
    """The dict artifact is what production loads; TreeExplainer cannot read it."""

    def test_dict_artifact_is_unwrapped_to_the_model_key(self, tmp_path):
        model = TreeCapableModel(marker="from-dict")
        artifact = _artifact(model)
        double = TreeExplainerDouble(np.zeros((1, N_FEATURES)))
        fake_shap = FakeShap(tree_explainer=double)
        service, path = _service_for(tmp_path, artifact, fake_shap)

        with _patch_shap(fake_shap):
            service.explain([0.5] * N_FEATURES)

        assert len(fake_shap.tree_models) == 1
        received = fake_shap.tree_models[0]
        assert not isinstance(received, dict), (
            "TreeExplainer received the artifact dict itself — this IS the "
            "production bug (InvalidModelError: model type not supported: dict)"
        )
        assert isinstance(received, TreeCapableModel)
        assert received.marker == "from-dict", (
            "the unwrapped estimator is not the one inside the artifact"
        )
        assert received is not artifact, "sanity: joblib.load returns a new object"
        assert path.exists()

    def test_bare_artifact_passes_through(self, tmp_path):
        double = TreeExplainerDouble(np.zeros((1, N_FEATURES)))
        fake_shap = FakeShap(tree_explainer=double)
        service, _ = _service_for(tmp_path, TreeCapableModel(marker="bare"), fake_shap)

        with _patch_shap(fake_shap):
            service.explain([0.5] * N_FEATURES)

        received = fake_shap.tree_models[0]
        assert isinstance(received, TreeCapableModel)
        assert received.marker == "bare", (
            "a bare (legacy) artifact must be handed over untouched, not "
            "searched for a 'model' key"
        )

    def test_feature_names_are_captured_from_the_artifact(self, tmp_path):
        model = TreeCapableModel()
        double = TreeExplainerDouble(np.array([[9.0] + [0.0] * (N_FEATURES - 1)]))
        fake_shap = FakeShap(tree_explainer=double)
        service, _ = _service_for(tmp_path, _artifact(model), fake_shap)

        with _patch_shap(fake_shap):
            result = service.explain([0.5] * N_FEATURES)

        assert result[0].feature == "amount"

    def test_artifact_feature_names_used_when_caller_passes_none(self, tmp_path):
        """The queue message may carry no names; the artifact knows them."""
        model = TreeCapableModel()
        vector = np.zeros(N_FEATURES)
        vector[7] = 5.0  # merchant_risk_level
        double = TreeExplainerDouble(np.array([vector]))
        fake_shap = FakeShap(tree_explainer=double)
        service, _ = _service_for(tmp_path, _artifact(model), fake_shap)

        with _patch_shap(fake_shap):
            result = service.explain([0.5] * N_FEATURES)

        assert result[0].feature == "merchant_risk_level"

    def test_caller_feature_names_win_over_the_artifact(self, tmp_path):
        model = TreeCapableModel()
        double = TreeExplainerDouble(np.array([[9.0] + [0.0] * (N_FEATURES - 1)]))
        fake_shap = FakeShap(tree_explainer=double)
        service, _ = _service_for(tmp_path, _artifact(model), fake_shap)

        caller_names = ["caller_%d" % i for i in range(N_FEATURES)]
        with _patch_shap(fake_shap):
            result = service.explain([0.5] * N_FEATURES, feature_names=caller_names)

        assert result[0].feature == "caller_0"

    def test_length_mismatch_with_the_artifact_still_falls_back(self, tmp_path):
        """An explicit wrong-length list must degrade to feature_i, not silently
        borrow the artifact's names — the existing mismatch contract stands."""
        model = TreeCapableModel()
        double = TreeExplainerDouble(np.array([[9.0] + [0.0] * (N_FEATURES - 1)]))
        fake_shap = FakeShap(tree_explainer=double)
        service, _ = _service_for(tmp_path, _artifact(model), fake_shap)

        with _patch_shap(fake_shap):
            result = service.explain([0.5] * N_FEATURES, feature_names=["only_one"])

        assert result[0].feature == "feature_0"


# ---------------------------------------------------------------------------
# Mode dispatch
# ---------------------------------------------------------------------------


class TestTreePathUsesShapValues:
    """The tree path must keep its existing call signature and semantics."""

    def test_shap_values_is_called_and_dunder_call_is_not(self, tmp_path):
        model = TreeCapableModel()
        double = TreeExplainerDouble(np.array([[9.0] + [0.0] * (N_FEATURES - 1)]))
        fake_shap = FakeShap(tree_explainer=double)
        service, _ = _service_for(tmp_path, _artifact(model), fake_shap)

        with _patch_shap(fake_shap):
            service.explain([0.5] * N_FEATURES)

        assert double.shap_values_calls == 1

    def test_tree_mode_is_recorded(self, tmp_path):
        model = TreeCapableModel()
        fake_shap = FakeShap(
            tree_explainer=TreeExplainerDouble(np.zeros((1, N_FEATURES)))
        )
        service, _ = _service_for(tmp_path, _artifact(model), fake_shap)

        with _patch_shap(fake_shap):
            service.explain([0.5] * N_FEATURES)

        assert service._mode == MODE_TREE


class TestCallableFallback:
    """TreeExplainer cannot read a CalibratedClassifierCV — wrap predict_proba."""

    @staticmethod
    def _callable_values(material=3.0):
        """(1, n_features, 2) with the fraud column carrying the signal."""
        values = np.zeros((1, N_FEATURES, 2))
        values[0, 3, 1] = material
        values[0, :, 0] = -values[0, :, 1]
        return values

    def test_fallback_taken_when_tree_explainer_rejects_the_model(self, tmp_path):
        model = TreeCapableModel(marker="from-dict")
        fake_shap = FakeShap(
            tree_explainer=RuntimeError(
                "InvalidModelError: Model type not yet supported"
            ),
            callable_values=self._callable_values(),
        )
        service, _ = _service_for(tmp_path, _artifact(model), fake_shap)

        with _patch_shap(fake_shap):
            result = service.explain([0.5] * N_FEATURES)

        assert len(fake_shap.explainer_calls) == 1, "fallback was not built"
        wrapped = fake_shap.explainer_calls[0]["fn"]
        # joblib.load hands back a fresh estimator, so compare what the wrapper
        # actually closes over rather than the in-memory bound method.
        assert wrapped.__func__ is TreeCapableModel.predict_proba
        assert wrapped.__self__.marker == "from-dict"
        assert service._mode == MODE_CALLABLE
        assert result[0].feature == "tx_count_last_5min"
        assert result[0].contribution == pytest.approx(3.0)

    def test_the_callable_is_invoked_and_shap_values_is_not(self, tmp_path):
        model = TreeCapableModel()
        double = CallableExplainerDouble(self._callable_values())
        fake_shap = FakeShap(tree_explainer=RuntimeError("nope"), callable_values=None)
        fake_shap.Explainer = lambda fn, masker, algorithm=None: double
        service, _ = _service_for(tmp_path, _artifact(model), fake_shap)

        with _patch_shap(fake_shap):
            service.explain([0.5] * N_FEATURES)

        assert double.call_calls == 1

    def test_the_callable_receives_a_two_dimensional_row(self, tmp_path):
        """shap's tabular masker rejects a bare 1-D vector.

        Measured: ``explain(row)`` with ``row.shape == (10,)`` raises
        ``DimensionError: ... data of shape () was passed while the masker
        expected data of shape (10,)``. The tree path takes 1-D input, so the
        two modes genuinely differ in input shape.
        """
        model = TreeCapableModel()
        double = CallableExplainerDouble(self._callable_values())
        fake_shap = FakeShap(tree_explainer=RuntimeError("nope"))
        fake_shap.Explainer = lambda fn, masker, algorithm=None: double
        service, _ = _service_for(tmp_path, _artifact(model), fake_shap)

        with _patch_shap(fake_shap):
            service.explain([0.5] * N_FEATURES)

        assert np.asarray(double.last_row).shape == (1, N_FEATURES)

    def test_background_is_reproducible_for_a_given_seed(self, tmp_path):
        model = TreeCapableModel()
        backgrounds = []

        def _capture(fn, masker, algorithm=None):
            backgrounds.append(np.array(masker[1]))
            return CallableExplainerDouble(self._callable_values())

        for _ in range(2):
            fake_shap = FakeShap(tree_explainer=RuntimeError("nope"))
            fake_shap.Explainer = _capture
            service, _ = _service_for(
                tmp_path, _artifact(model), fake_shap, filename="m.joblib"
            )
            with _patch_shap(fake_shap):
                service.explain([0.5] * N_FEATURES)

        assert np.array_equal(backgrounds[0], backgrounds[1]), (
            "the background sample must be reproducible across processes"
        )
        assert backgrounds[0].shape[1] == N_FEATURES


class TestFallbackIsNotABlanketExcept:
    """A fallback that swallows everything is how a silent failure gets shipped."""

    def test_no_predict_proba_reraises_as_unavailable(self, tmp_path):
        fake_shap = FakeShap(tree_explainer=RuntimeError("tree unsupported"))
        service, _ = _service_for(tmp_path, NoProbaModel(), fake_shap)

        with _patch_shap(fake_shap):
            with pytest.raises(ShapUnavailableError):
                service.explain([0.5] * N_FEATURES)

        assert fake_shap.explainer_calls == [], (
            "no callable fallback may be attempted for an estimator without "
            "predict_proba"
        )

    def test_zero_n_features_reraises_as_unavailable(self, tmp_path):
        fake_shap = FakeShap(tree_explainer=RuntimeError("tree unsupported"))
        service, _ = _service_for(tmp_path, ZeroFeatureModel(), fake_shap)

        with _patch_shap(fake_shap):
            with pytest.raises(ShapUnavailableError):
                service.explain([0.5] * N_FEATURES)

        assert fake_shap.explainer_calls == [], (
            "n_features_in_ == 0 yields an empty background; that is not "
            "something to paper over with an explanation"
        )

    def test_original_failure_is_chained_as_the_cause(self, tmp_path):
        fake_shap = FakeShap(tree_explainer=RuntimeError("original boom"))
        service, _ = _service_for(tmp_path, NoProbaModel(), fake_shap)

        with _patch_shap(fake_shap):
            with pytest.raises(ShapUnavailableError) as excinfo:
                service.explain([0.5] * N_FEATURES)

        assert "original boom" in str(excinfo.value.__cause__)


# ---------------------------------------------------------------------------
# Algorithm selection
# ---------------------------------------------------------------------------


class TestAlgorithmSelection:
    """``exact`` costs 2**n model rows; past the cap that stops being sane."""

    def test_exact_at_the_cap(self):
        from src.services.shap_service import EXACT_MAX_FEATURES

        assert ShapService._algorithm_for(EXACT_MAX_FEATURES) == "exact"

    def test_exact_below_the_cap(self):
        assert ShapService._algorithm_for(N_FEATURES) == "exact"

    def test_permutation_past_the_cap(self):
        from src.services.shap_service import EXACT_MAX_FEATURES

        assert ShapService._algorithm_for(EXACT_MAX_FEATURES + 1) == "permutation"

    def test_permutation_algorithm_reaches_the_explainer(self, tmp_path):
        """Assert the choice without paying for it: fake shap records the kwarg."""
        from src.services.shap_service import EXACT_MAX_FEATURES

        wide = TreeCapableModel()
        wide.n_features_in_ = EXACT_MAX_FEATURES + 5
        fake_shap = FakeShap(tree_explainer=RuntimeError("tree unsupported"))
        service, _ = _service_for(tmp_path, _artifact(wide), fake_shap)

        with _patch_shap(fake_shap):
            service.explain([0.5] * (EXACT_MAX_FEATURES + 5))

        assert fake_shap.explainer_calls[0]["algorithm"] == "permutation"

    def test_exact_algorithm_reaches_the_explainer(self, tmp_path):
        fake_shap = FakeShap(tree_explainer=RuntimeError("tree unsupported"))
        service, _ = _service_for(tmp_path, _artifact(TreeCapableModel()), fake_shap)

        with _patch_shap(fake_shap):
            service.explain([0.5] * N_FEATURES)

        assert fake_shap.explainer_calls[0]["algorithm"] == "exact"


# ---------------------------------------------------------------------------
# Output-shape normalization
# ---------------------------------------------------------------------------


def _service_returning(values, mode=MODE_TREE):
    """Bypass lazy init by injecting an explainer, the way the worker tests do."""
    service = ShapService()
    service._explainer = (
        TreeExplainerDouble(values) if mode == MODE_TREE else CallableExplainerDouble(values)
    )
    service._mode = mode
    return service


class TestNormalization:
    def test_3d_uses_sample_zero_and_fraud_class_index_one(self):
        values = np.zeros((1, N_FEATURES, 2))
        values[0, 2, 1] = 0.7
        values[0, 2, 0] = -0.7  # the non-fraud column must be ignored
        service = _service_returning(values)

        result = service.explain([0.5] * N_FEATURES)

        assert result[0].contribution == pytest.approx(0.7)

    def test_explanation_object_is_unwrapped_to_its_values(self):
        """shap 0.46 returns an Explanation; np.asarray() on it is object dtype."""
        values = np.zeros((1, N_FEATURES, 2))
        values[0, 5, 1] = -0.42
        service = _service_returning(
            ExplanationLike(values), mode=MODE_CALLABLE
        )

        result = service.explain([0.5] * N_FEATURES, feature_names=FEATURE_NAMES)

        assert result[0].contribution == pytest.approx(-0.42)
        assert result[0].feature == "hour_of_day"

    def test_explanation_object_without_values_attribute_is_not_rejected(self):
        """Duck-typing guard: a non-ndarray ``.values`` must not be trusted."""
        class Weird:
            values = "not an array"

        service = _service_returning(Weird(), mode=MODE_CALLABLE)

        with pytest.raises(TypeError):
            service.explain([0.5] * N_FEATURES)

    def test_2d_uses_row_zero_only(self):
        """A 2-D array must not be flattened: rows after the first are other
        samples, not more features."""
        values = np.zeros((3, N_FEATURES))
        values[0, 1] = -0.9
        values[1, 4] = 99.0
        values[2, 6] = 98.0
        service = _service_returning(values)

        result = service.explain([0.5] * N_FEATURES)

        assert [c.contribution for c in result] == pytest.approx([-0.9, 0.0, 0.0, 0.0, 0.0])

    def test_list_uses_index_one_when_longer_than_one(self):
        class_0 = np.array([0.5] * N_FEATURES)
        class_1 = np.array([0.1 * i for i in range(N_FEATURES)])
        service = _service_returning([class_0, class_1])

        result = service.explain([0.5] * N_FEATURES)

        assert result[0].contribution == pytest.approx(0.9)
        assert result[0].feature == "feature_9"

    def test_single_element_list_uses_index_zero(self):
        only = np.array([0.25] * N_FEATURES)
        service = _service_returning([only])

        result = service.explain([0.5] * N_FEATURES)

        assert result[0].contribution == pytest.approx(0.25)

    def test_top_k_is_bounded_and_ranked_by_absolute_value(self):
        values = np.array([[5.0, -4.0, 3.0, -2.0, 1.0, 0.5, 0.4, 0.3, 0.2, 0.1]])
        service = _service_returning(values)

        result = service.explain([0.5] * N_FEATURES)

        assert len(result) == 5
        assert [c.contribution for c in result] == pytest.approx([5.0, -4.0, 3.0, -2.0, 1.0])


# ---------------------------------------------------------------------------
# Lazy import contract (must survive the fallback work)
# ---------------------------------------------------------------------------


class TestLazyImportUnchanged:
    def test_missing_shap_still_raises_unavailable(self, tmp_path):
        service, _ = _service_for(tmp_path, TreeCapableModel(), FakeShap())
        with patch("importlib.import_module", side_effect=ImportError("no shap")):
            with pytest.raises(ShapUnavailableError, match="shap is not installed"):
                service.explain([0.5] * N_FEATURES)

    def test_explainer_is_built_once_under_the_singleton(self, tmp_path):
        double = TreeExplainerDouble(np.zeros((1, N_FEATURES)))
        fake_shap = FakeShap(tree_explainer=double)
        service, _ = _service_for(tmp_path, _artifact(TreeCapableModel()), fake_shap)

        with _patch_shap(fake_shap):
            service.explain([0.5] * N_FEATURES)
            service.explain([0.5] * N_FEATURES)

        assert double.shap_values_calls == 2
        assert len(fake_shap.tree_models) == 1, "explainer was rebuilt"

    def test_model_fingerprint_is_unchanged(self, tmp_path):
        path = tmp_path / "model.joblib"
        path.write_bytes(b"x" * 321)
        service = ShapService(model_path=str(path))
        stat = path.stat()
        assert service.model_fingerprint() == "%d:%d" % (stat.st_size, int(stat.st_mtime))

    def test_missing_model_file_still_raises_unavailable(self, tmp_path, caplog):
        service = ShapService(model_path=str(tmp_path / "absent.joblib"))
        fake_shap = FakeShap()
        with _patch_shap(fake_shap):
            with caplog.at_level(logging.WARNING, logger="src.services.shap_service"):
                with pytest.raises(ShapUnavailableError, match="not found"):
                    service.explain([0.5] * N_FEATURES)


# ---------------------------------------------------------------------------
# Integration: the real shipped artifact
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_artifact():
    """The shipped artifact, or a clean skip — CI has xgboost, laptop may not."""
    pytest.importorskip(
        "xgboost", reason="xgboost is required to unpickle the shipped artifact"
    )
    pytest.importorskip("shap", reason="shap is required for this integration check")
    if not REAL_MODEL_PATH.exists():
        pytest.skip("shipped artifact %s is absent" % REAL_MODEL_PATH)
    artifact = joblib.load(REAL_MODEL_PATH)
    assert isinstance(artifact, dict) and "model" in artifact, (
        "the artifact layout changed — re-check ShapService._unwrap_artifact"
    )
    return artifact


@pytest.fixture(scope="module")
def real_vector():
    """A realistic vector from the production FeatureEngine, not a hand-written one."""
    from src.services.feature_engine import FeatureEngine

    transaction = {
        "id": "shap-integration-fixture",
        "amount": 50000.0,
        "merchant_category": "cryptocurrency",
        "merchant_name": "binance",
        "timestamp": "2024-01-15T03:00:00+00:00",
    }
    return FeatureEngine().transform(transaction)


class TestRealArtifactIntegration:
    """The regression that would have caught the production bug on day one.

    Module-scoped fixtures so the ~4 s cold explanation is paid **once** for the
    whole class. Budget for this class: ~6 s.
    """

    @pytest.fixture(scope="class")
    def real_service(self):
        return ShapService(model_path=str(REAL_MODEL_PATH))

    @pytest.fixture(scope="class")
    def explained(self, real_service, real_vector):
        """One public-API explain() call, reused by every assertion below."""
        return real_service.explain(list(real_vector))

    def test_the_shipped_artifact_needs_the_callable_fallback(self, real_artifact, real_service):
        """Neither the artifact nor its unwrapped estimator is tree-readable.

        Asserted with ``_ensure_ready()`` rather than ``explain()`` on purpose:
        this is about which builder ran, and building is cheap next to the cold
        explanation the fixture above already paid for.
        """
        import shap

        with pytest.raises(Exception):
            shap.TreeExplainer(real_artifact)
        with pytest.raises(Exception):
            shap.TreeExplainer(real_artifact["model"])

        real_service._ensure_ready()

        assert real_service._mode == MODE_CALLABLE

    def test_contributions_decompose_the_served_probability(
        self, real_artifact, real_service, real_vector, explained
    ):
        """base_value + sum(contributions) == predict_proba[:, 1].

        This is the invariant that makes the fallback legitimate rather than a
        guess: the contributions add up to the probability the scoring service
        actually served, so a stored attribution cannot disagree with the score
        stored beside it.
        """
        explanation = real_service._explainer(real_vector.reshape(1, -1))
        values = np.asarray(explanation.values)
        base_values = np.asarray(explanation.base_values)

        assert values.shape == (1, N_FEATURES, 2), (
            "expected (samples, features, classes) from shap.Explainer"
        )
        assert base_values.shape[1] == 2, "fraud class must be index 1"

        served = float(real_artifact["model"].predict_proba([real_vector])[0, 1])
        decomposed = float(base_values[0, 1]) + float(values[0, :, 1].sum())

        assert decomposed == pytest.approx(served, abs=1e-6), (
            "contributions do not reconstruct the served probability — the "
            "attribution would describe a different number than the score"
        )

    def test_top_five_is_non_degenerate(self, real_service, real_vector, explained):
        """Guards the silent-zero failure: five named, materially non-zero rows."""
        assert len(explained) == 5
        assert all(
            c.feature in FEATURE_NAMES for c in explained
        ), "artifact feature_names were not applied — rows are unnamed"

        magnitudes = [abs(c.contribution) for c in explained]
        assert magnitudes == sorted(magnitudes, reverse=True), (
            "top-5 is not ranked by |contribution| descending"
        )
        assert magnitudes[0] > 1e-6, (
            "all contributions are zero: the explainer 'succeeded' while "
            "explaining nothing (the silent-failure shape of this bug)"
        )

        # Non-zero is necessary but not sufficient: the values the service
        # returns must be the raw shap fraud column, feature name and all. An
        # explainer pointing at a different quantity still passes a
        # non-degeneracy check, so compare against the raw explanation.
        explanation = real_service._explainer(real_vector.reshape(1, -1))
        raw = np.asarray(explanation.values)[0, :, 1]
        expected = sorted(
            zip(FEATURE_NAMES, raw), key=lambda pair: abs(pair[1]), reverse=True
        )[:5]

        assert [c.feature for c in explained] == [f for f, _ in expected]
        assert [c.contribution for c in explained] == pytest.approx(
            [v for _, v in expected]
        )