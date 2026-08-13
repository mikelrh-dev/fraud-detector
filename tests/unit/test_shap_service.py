"""ShapService tests — lazy defensive shap import (SHP-005), shap_values
shape normalization (SHP-002), top-5 selection by |contribution|, feature
name fallback, and model fingerprint.

These tests MUST pass without shap installed: the service imports shap
lazily via importlib, and the fake-explainer paths inject the explainer
directly to bypass the lazy init.
"""

import importlib
import logging
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.services.shap_service import (
    ShapContribution,
    ShapService,
    ShapUnavailableError,
)


class FakeExplainer:
    """Minimal stand-in for shap.TreeExplainer."""

    def __init__(self, shap_values) -> None:
        self._values = shap_values

    def shap_values(self, features):
        return self._values


def _service_with_explainer(shap_values) -> ShapService:
    """Build a service whose lazy init is bypassed with a fake explainer."""
    service = ShapService()
    service._explainer = FakeExplainer(shap_values)
    return service


class TestShapUnavailable:
    """SHP-005 — missing shap must surface as ShapUnavailableError + warning."""

    def test_import_error_raises_unavailable_with_warning(self, caplog):
        service = ShapService()
        with patch(
            "importlib.import_module",
            side_effect=ImportError("No module named 'shap'"),
        ):
            with caplog.at_level(
                logging.WARNING, logger="src.services.shap_service"
            ):
                with pytest.raises(ShapUnavailableError):
                    service.explain([0.5] * 10)
        assert "shap is not installed" in caplog.text

    def test_model_missing_raises_unavailable(self, tmp_path):
        fake_shap = MagicMock()
        original_import = importlib.import_module

        def _import(name, *args, **kwargs):
            if name == "shap":
                return fake_shap
            return original_import(name, *args, **kwargs)

        service = ShapService(model_path=str(tmp_path / "missing.joblib"))
        with patch("importlib.import_module", side_effect=_import):
            with pytest.raises(ShapUnavailableError):
                service.explain([0.5] * 10)


class TestExplainNormalization:
    """SHP-002 — shap_values shape handling (binary classifier, fraud idx 1)."""

    def test_list_uses_fraud_class_index_1(self):
        class_0 = np.array([0.01 * i for i in range(10)])
        class_1 = np.array([0.1 * i for i in range(10)])
        service = _service_with_explainer([class_0, class_1])

        result = service.explain([0.5] * 10)

        # Top-5 by |class_1| descending → indexes 9,8,7,6,5
        assert [c.feature for c in result] == [
            "feature_9",
            "feature_8",
            "feature_7",
            "feature_6",
            "feature_5",
        ]
        assert [c.contribution for c in result] == pytest.approx(
            [0.9, 0.8, 0.7, 0.6, 0.5]
        )

    def test_2d_values_used_as_is(self):
        values = np.array(
            [[0.1, -0.9, 0.2, -0.8, 0.3, -0.7, 0.4, -0.6, 0.5, -0.5]]
        )
        service = _service_with_explainer(values)

        result = service.explain([0.5] * 10)

        # |contributions|: 0.9, 0.8, 0.7, 0.6, then 0.5 (index 8 wins the tie)
        assert [c.feature for c in result] == [
            "feature_1",
            "feature_3",
            "feature_5",
            "feature_7",
            "feature_8",
        ]
        assert [c.contribution for c in result] == [-0.9, -0.8, -0.7, -0.6, 0.5]

    def test_3d_uses_fraud_class_index_1(self):
        values = np.zeros((1, 10, 2))
        values[0, :, 1] = np.array(
            [0.0, -0.9, 0.0, -0.8, 0.0, -0.7, 0.0, -0.6, 0.0, -0.5]
        )
        service = _service_with_explainer(values)

        result = service.explain([0.5] * 10)

        assert [c.contribution for c in result] == [-0.9, -0.8, -0.7, -0.6, -0.5]
        assert [c.feature for c in result] == [
            "feature_1",
            "feature_3",
            "feature_5",
            "feature_7",
            "feature_9",
        ]


class TestFeatureNames:
    """Feature name resolution and fallback."""

    def test_feature_names_used_when_length_matches(self):
        service = _service_with_explainer(
            np.array([[0.9, 0.8, 0.7, 0.6, 0.5]])
        )
        names = ["amount", "velocity_1h", "velocity_24h", "merchant_category", "hour"]

        result = service.explain([0.5] * 5, feature_names=names)

        assert [c.feature for c in result] == names

    def test_name_mismatch_falls_back_to_feature_i(self, caplog):
        service = _service_with_explainer(
            np.array([[0.9, 0.8, 0.7, 0.6, 0.5]])
        )

        with caplog.at_level(
            logging.WARNING, logger="src.services.shap_service"
        ):
            result = service.explain([0.5] * 5, feature_names=["only_one"])

        assert [c.feature for c in result] == [
            "feature_0",
            "feature_1",
            "feature_2",
            "feature_3",
            "feature_4",
        ]
        assert "does not match" in caplog.text


class TestModelFingerprint:
    """model_fingerprint() reads file stat — no shap import needed."""

    def test_fingerprint_is_size_and_mtime(self, tmp_path):
        model_file = tmp_path / "model.joblib"
        model_file.write_bytes(b"x" * 1234)
        service = ShapService(model_path=str(model_file))

        stat = model_file.stat()
        assert service.model_fingerprint() == f"{stat.st_size}:{int(stat.st_mtime)}"

    def test_fingerprint_empty_when_model_missing(self, tmp_path):
        service = ShapService(model_path=str(tmp_path / "nope.joblib"))

        assert service.model_fingerprint() == ""


class TestExplainContract:
    """Shape of explain() output — always 5 entries, ShapContribution."""

    def test_returns_top5_shap_contributions(self):
        values = np.arange(12, dtype=float).reshape(1, 12)
        service = _service_with_explainer(values)

        result = service.explain([0.5] * 12)

        assert len(result) == 5
        assert all(isinstance(c, ShapContribution) for c in result)
        # arange(12): top-5 by |v| → 11, 10, 9, 8, 7
        assert [c.contribution for c in result] == [11.0, 10.0, 9.0, 8.0, 7.0]
