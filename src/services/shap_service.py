"""SHAP feature attribution service.

Computes feature contributions over the joblib-serialized XGBoost model.
``shap`` is imported lazily (SHP-005): when shap or the model file is
unavailable, ``explain()`` raises ``ShapUnavailableError`` and callers skip
computation instead of crashing.

Two explainer shapes exist, and picking the wrong one is silent
-------------------------------------------------------------
The shipped artifact ``models/xgboost_paysim_v1.joblib`` is a **dict**
wrapping a ``CalibratedClassifierCV`` (see ``scripts/train_xgboost_aligned.py``),
and neither the dict nor the estimator it wraps is a tree shap can read:

    shap.TreeExplainer(artifact)              -> InvalidModelError: ...<class 'dict'>
    shap.TreeExplainer(artifact["model"])     -> InvalidModelError: ...CalibratedClassifierCV>

So ``TreeExplainer`` is attempted first (it is the right tool when the artifact
ever *is* a bare booster) and, when it refuses the model, the estimator's own
``predict_proba`` is wrapped with ``shap.Explainer`` instead. That fallback
explains the probability the scoring service actually served:

    base_value + sum(contributions) == estimator.predict_proba(row)[0, 1]

verified to 2.8e-17 against the real artifact — which is the whole reason the
fallback is correct rather than merely convenient. A per-fold log-odds margin
would not reconstruct the served score, so it could not be checked against the
``shap_attribution`` row sitting next to it.

The builder returns the mode alongside the explainer and ``explain()``
dispatches on it, rather than sniffing per call: the two entry points differ in
*both* input shape (1-D vs 2-D) and return shape (list/2-D vs ``Explanation``),
so a call-site guess would be a guess about two things at once.

Cost, measured on this machine (shap 0.46.0, xgboost 2.1.0, 10 features)
--------------------------------------------------------------------
- building the explainer: ~0.2 ms
- first ``explain()`` in a process: **4-7 s** (measured 3.9, 4.2, 5.2, 6.8)
- subsequent ``explain()`` calls: **~0.09 s** each

Two separate numbers, and conflating them is how this gets mis-costed. The cold
call is not per-row cost, it is first-touch warm-up of the calibrated ensemble:
the exact explainer sends all 2**10 = 1024 perturbed rows through
``predict_proba`` in a single batched call (measured: 1 batched call, not 1024),
and that batch is what takes the seconds. Steady state is ~11 rows/s.

Because the shap worker is a single-consumer BRPOP loop, that ceiling is the
worker's real throughput and the first message after a worker boot waits
seconds. Fine for an explanatory side-channel; not acceptable inside a scoring
request path. Do not move this call into the request lifecycle.

Background sample
-----------------
The masker background is a uniform ``RandomState(BACKGROUND_SEED).rand(50, n)``
sample, not a sample of the training corpus. Trade-off, stated plainly: against
a real corpus background the attribution *ranking* changes, because the expected
value differs, while additivity and plausibility survive both. A uniform sample
is reproducible across processes and needs no corpus at inference time; a
corpus-backed background would be more faithful but makes the output depend on
data the service does not ship. This is a deliberate choice, not an oversight.

The explainer is a process-wide singleton built lazily under a lock — the
worker is a single consumer, so ``asyncio.to_thread`` calls serialize anyway.
"""

import importlib
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np

logger = logging.getLogger(__name__)

TOP_K = 5
DEFAULT_MODEL_PATH = "models/xgboost_paysim_v1.joblib"

#: The explainer was built from the tree structure: call ``.shap_values(row)``.
MODE_TREE = "tree"
#: The explainer wraps ``predict_proba``: call ``explainer(row_2d)``.
MODE_CALLABLE = "callable"

#: ``algorithm="exact"`` evaluates 2**n perturbed rows in one batched call. At
#: n=10 that is 1024 rows (measured: 4-7 s first call, ~0.09 s warm); it doubles
#: per added feature, so past this cap the exponential stops being affordable
#: and the linear-cost ``"permutation"`` algorithm is selected instead
#: (measured at n=10: 23 model calls, 0.12 s, also additive).
EXACT_MAX_FEATURES = 12
#: Masker background size. 50 keeps the exact explainer's per-row marginal
#: averages stable without making the 2**n batch the dominant term.
BACKGROUND_ROWS = 50
#: Fixed so two processes explain the same transaction the same way. An
#: unseeded background would make stored attributions irreproducible.
BACKGROUND_SEED = 20240115


class ShapUnavailableError(RuntimeError):
    """Raised when shap or the ML model cannot be loaded (SHP-005).

    Callers treat this as a permanent, environmental failure: skip the
    message, do NOT retry, and keep the loop alive.
    """


@dataclass(frozen=True)
class ShapContribution:
    """A single feature contribution returned by ``explain()``."""

    feature: str
    contribution: float


@dataclass(frozen=True)
class BuiltExplainer:
    """An explainer plus the entry point that explains with it."""

    explainer: Any
    mode: str


class ShapService:
    """Lazy, thread-safe wrapper around a shap explainer.

    The service loads its own model file (same default path as
    MLModelService) instead of reusing ``MLModelService._model`` — the
    worker runs in a separate process and the private attribute is not
    a stable contract.
    """

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH) -> None:
        self._model_path = model_path
        self._explainer: Any = None
        #: Defaults to the tree path so an explainer injected directly (tests,
        #: and any future caller that builds its own) keeps the 1-D
        #: ``.shap_values`` contract without having to declare a mode.
        self._mode = MODE_TREE
        self._feature_names: list[str] | None = None
        self._lock = threading.Lock()

    def _ensure_ready(self) -> None:
        """Load shap + the model and build the explainer exactly once.

        Thread-safe: concurrent callers block on the lock and only the
        first one performs the (expensive) load.
        """
        with self._lock:
            if self._explainer is not None:
                return

            try:
                shap = importlib.import_module("shap")
            except ImportError as exc:
                logger.warning(
                    "shap is not installed — SHAP attribution disabled: %s",
                    exc,
                )
                raise ShapUnavailableError(
                    "shap is not installed"
                ) from exc

            path = Path(self._model_path)
            if not path.exists():
                logger.warning(
                    "ML model not found at %s — SHAP attribution disabled",
                    self._model_path,
                )
                raise ShapUnavailableError(
                    f"ML model not found at {self._model_path}"
                )

            try:
                artifact = joblib.load(path)
                estimator, feature_names = self._unwrap(artifact)
                built = self._build_explainer(shap, estimator)
            except ShapUnavailableError:
                raise
            except Exception as exc:
                logger.error(
                    "Failed to initialize SHAP explainer from %s: %s",
                    self._model_path,
                    exc,
                )
                raise ShapUnavailableError(
                    f"Failed to initialize SHAP explainer: {exc}"
                ) from exc

            self._explainer = built.explainer
            self._mode = built.mode
            self._feature_names = feature_names

    @staticmethod
    def _unwrap(artifact: Any) -> tuple[Any, list[str] | None]:
        """Split the artifact into ``(estimator, feature_names)``.

        The dict layout is what training writes; a bare estimator is the legacy
        layout. Reading the dict is the difference between an explainer and an
        ``InvalidModelError`` on ``<class 'dict'>``.
        """
        if isinstance(artifact, dict) and "model" in artifact:
            names = artifact.get("feature_names")
            return artifact["model"], list(names) if names else None
        return artifact, None

    @staticmethod
    def _algorithm_for(n_features: int) -> str:
        """``exact`` up to the feature cap, ``permutation`` beyond it."""
        return "exact" if n_features <= EXACT_MAX_FEATURES else "permutation"

    def _build_explainer(self, shap: Any, estimator: Any) -> BuiltExplainer:
        """Build the cheapest explainer that can explain ``estimator``.

        The callable fallback is guarded, not blanket: an estimator with no
        ``predict_proba`` or no usable ``n_features_in_`` cannot be explained
        this way, and pretending otherwise would convert a clear failure into an
        opaque one. In that case the tree failure is re-raised as the original
        cause.
        """
        try:
            return BuiltExplainer(shap.TreeExplainer(estimator), MODE_TREE)
        except Exception as tree_error:
            predict_proba = getattr(estimator, "predict_proba", None)
            if not callable(predict_proba):
                logger.error(
                    "TreeExplainer rejected %s and the estimator has no "
                    "predict_proba to fall back on: %s",
                    type(estimator).__name__,
                    tree_error,
                )
                raise ShapUnavailableError(
                    f"Cannot explain {type(estimator).__name__}: "
                    f"{tree_error}"
                ) from tree_error

            n_features = int(getattr(estimator, "n_features_in_", 0) or 0)
            if n_features <= 0:
                logger.error(
                    "Estimator reports n_features_in_=%d — shap needs at least "
                    "one feature to build a background",
                    n_features,
                )
                raise ShapUnavailableError(
                    f"Cannot explain {type(estimator).__name__}: "
                    f"n_features_in_ is {n_features}"
                ) from tree_error

            algorithm = self._algorithm_for(n_features)
            background = np.random.RandomState(BACKGROUND_SEED).rand(
                BACKGROUND_ROWS, n_features
            )
            explainer = shap.Explainer(
                predict_proba,
                shap.maskers.Independent(background),
                algorithm=algorithm,
            )
            logger.info(
                "Built shap %s explainer over %s.predict_proba "
                "(algorithm=%s, n_features=%d, background=%dx%d uniform seed=%d)",
                algorithm,
                type(estimator).__name__,
                algorithm,
                n_features,
                BACKGROUND_ROWS,
                n_features,
                BACKGROUND_SEED,
            )
            return BuiltExplainer(explainer, MODE_CALLABLE)

    def explain(
        self,
        features: list[float],
        feature_names: list[str] | None = None,
    ) -> list[ShapContribution]:
        """Compute the top-5 feature contributions for one feature vector.

        Args:
            features: The scored feature vector (queue snapshot).
            feature_names: Optional names aligned with the vector. When
                absent, the names stamped in the artifact are used; a
                length mismatch still degrades to ``feature_{i}``.

        Returns:
            Top-5 ``ShapContribution`` entries ordered by absolute
            contribution descending, values signed.

        Raises:
            ShapUnavailableError: when shap or the model file is missing, or
                the artifact cannot be explained at all (SHP-005 — callers
                skip, never retry).
        """
        self._ensure_ready()
        if self._mode == MODE_CALLABLE:
            # shap's tabular masker rejects a bare 1-D vector, so the callable
            # path hands over an explicit single-row matrix.
            row = np.asarray(features, dtype=float).reshape(1, -1)
            values = self._explainer(row)
        else:
            values = self._explainer.shap_values(features)
        vector = self._normalize_shap_values(values)
        names = feature_names if feature_names is not None else self._feature_names
        return self._top_k(vector, names)

    def _as_float_array(self, values: Any) -> np.ndarray:
        """Coerce an explainer's return value to a real float array.

        ``shap.Explainer`` returns an ``Explanation``, an ndarray subclass whose
        ``np.asarray()`` conversion is **object dtype** — every element is
        another ``Explanation``. Feeding that to ``float()`` raises
        ``TypeError: float() argument must be ... not 'Explanation'``. Its
        ``.values`` attribute is the actual float array, so prefer that
        whenever it is one.
        """
        real = getattr(values, "values", None)
        if isinstance(real, np.ndarray):
            return np.asarray(real)
        return np.asarray(values)

    def _normalize_shap_values(self, values: Any) -> list[float]:
        """Reduce an explanation to a flat (n_features,) fraud-margin vector.

        Binary output shape varies by explainer and shap version:
        - list of per-class arrays        -> fraud class index 1
        - 3D (samples, features, classes) -> sample 0, fraud class 1
        - 2D (samples, features)          -> sample 0
        - 1D                              -> already the fraud margin

        A 2D array holds one ROW PER SAMPLE, so it must not be flattened: rows
        after the first are other transactions, not more features.
        """
        if isinstance(values, list):
            vector = values[1] if len(values) > 1 else values[0]
        else:
            arr = self._as_float_array(values)
            if arr.ndim == 3:
                vector = arr[0, :, 1]
            elif arr.ndim == 2:
                vector = arr[0]
            else:
                vector = arr
        return [float(x) for x in np.asarray(vector).reshape(-1)]

    def _top_k(
        self,
        vector: list[float],
        feature_names: list[str] | None,
    ) -> list[ShapContribution]:
        if feature_names is not None and len(feature_names) != len(vector):
            logger.warning(
                "feature_names length %d does not match %d SHAP values — "
                "falling back to feature_i",
                len(feature_names),
                len(vector),
            )
            feature_names = None

        ranked = sorted(
            range(len(vector)),
            key=lambda i: abs(vector[i]),
            reverse=True,
        )[:TOP_K]

        return [
            ShapContribution(
                feature=(
                    feature_names[i]
                    if feature_names is not None
                    else f"feature_{i}"
                ),
                contribution=vector[i],
            )
            for i in ranked
        ]

    def model_fingerprint(self) -> str:
        """Return ``"<size>:<mtime>"`` of the model file (no shap import).

        Used to snapshot which model version an attribution refers to.
        Empty string when the file is missing.
        """
        path = Path(self._model_path)
        try:
            stat = path.stat()
        except OSError:
            return ""
        return f"{stat.st_size}:{int(stat.st_mtime)}"
