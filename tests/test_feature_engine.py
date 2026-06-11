"""Feature engine tests — feature extraction consistency, fixed dimensionality,
deterministic output, and empty history fallback.

These tests verify the second layer of the fraud scoring pipeline:
converting raw transaction data into a fixed-dimension feature vector.
"""

import numpy as np
import pytest

from src.services.feature_engine import FEATURE_NAMES, FeatureEngine


class TestFeatureEngineDimensionality:
    """Feature vector must always have the same fixed dimensionality."""

    def test_feature_vector_has_10_dimensions(self):
        """Feature vector for a well-formed transaction should have exactly 10 features."""
        engine = FeatureEngine()
        tx = {
            "amount": 1500.0,
            "merchant_name": "Some Store",
            "merchant_category": "retail",
            "timestamp": "2024-06-15T14:30:00+00:00",
        }
        features = engine.transform(tx)
        assert len(features) == 10

    def test_feature_vector_dimensionality_consistent(self):
        """Multiple transactions should produce same-dimensionality vectors."""
        engine = FeatureEngine()
        tx1 = {"amount": 100.0, "timestamp": "2024-06-15T14:30:00+00:00"}
        tx2 = {"amount": 50000.0, "timestamp": "2024-06-15T03:00:00+00:00"}

        f1 = engine.transform(tx1)
        f2 = engine.transform(tx2)

        assert len(f1) == len(f2)
        assert len(f1) == 10


class TestFeatureEngineDeterminism:
    """Same input must produce same output every time."""

    def test_deterministic_output(self):
        """Same transaction should produce identical feature vectors."""
        engine = FeatureEngine()
        tx = {
            "amount": 2500.0,
            "merchant_name": "Test Store",
            "merchant_category": "electronics",
            "timestamp": "2024-06-15T14:30:00+00:00",
        }
        f1 = engine.transform(tx)
        f2 = engine.transform(tx)
        np.testing.assert_array_equal(f1, f2)

    def test_different_amounts_produce_different_vectors(self):
        """Transactions with different amounts should differ in at least amount feature."""
        engine = FeatureEngine()
        tx_low = {"amount": 10.0, "timestamp": "2024-06-15T14:30:00+00:00"}
        tx_high = {"amount": 50000.0, "timestamp": "2024-06-15T14:30:00+00:00"}

        f_low = engine.transform(tx_low)
        f_high = engine.transform(tx_high)

        # At least one feature should differ (the amount feature at index 0)
        assert not np.array_equal(f_low, f_high), (
            "Different amounts should produce different feature vectors"
        )


class TestFeatureEngineValues:
    """Feature values should reflect input data correctly."""

    def test_amount_feature_matches_input(self):
        """The first feature (amount) should match the transaction amount."""
        engine = FeatureEngine()
        tx = {"amount": 1234.56, "timestamp": "2024-06-15T14:30:00+00:00"}
        features = engine.transform(tx)
        assert features[0] == 1234.56

    def test_hour_of_day_extracted(self):
        """Hour of day feature should be extracted from timestamp."""
        engine = FeatureEngine()
        # 3 AM transaction
        tx = {"amount": 100.0, "timestamp": "2024-06-15T03:00:00+00:00"}
        features = engine.transform(tx)
        # hour_of_day is at index 5
        assert features[5] == 3

    def test_weekend_detection(self):
        """is_weekend feature should be 1 for Saturday/Sunday."""
        engine = FeatureEngine()
        # 2024-06-15 is a Saturday
        tx = {"amount": 100.0, "timestamp": "2024-06-15T14:30:00+00:00"}
        features = engine.transform(tx)
        # is_weekend is at index 6
        assert features[6] == 1.0

    def test_weekday_detection(self):
        """is_weekend feature should be 0 for weekdays."""
        engine = FeatureEngine()
        # 2024-06-17 is a Monday
        tx = {"amount": 100.0, "timestamp": "2024-06-17T14:30:00+00:00"}
        features = engine.transform(tx)
        assert features[6] == 0.0

    def test_round_number_detection(self):
        """amount_round_number should be 1 for round amounts like 1000."""
        engine = FeatureEngine()
        tx = {"amount": 1000.0, "timestamp": "2024-06-15T14:30:00+00:00"}
        features = engine.transform(tx)
        # amount_round_number is at index 9
        assert features[9] == 1.0

    def test_non_round_number(self):
        """amount_round_number should be 0 for non-round amounts like 1234.56."""
        engine = FeatureEngine()
        tx = {"amount": 1234.56, "timestamp": "2024-06-15T14:30:00+00:00"}
        features = engine.transform(tx)
        assert features[9] == 0.0


class TestFeatureEngineGetFeatureNames:
    """get_feature_names() should return the expected feature names list."""

    def test_get_feature_names_returns_list(self):
        """get_feature_names() should return a list of strings."""
        engine = FeatureEngine()
        names = engine.get_feature_names()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)

    def test_get_feature_names_length(self):
        """get_feature_names() should return exactly 10 names."""
        engine = FeatureEngine()
        names = engine.get_feature_names()
        assert len(names) == 10

    def test_feature_names_order_matches_vector(self):
        """Feature names should correspond to feature vector positions."""
        engine = FeatureEngine()
        names = engine.get_feature_names()
        assert names[0] == "amount"
        assert names[5] == "hour_of_day"
        assert names[6] == "is_weekend"
        assert names[9] == "amount_round_number"

    def test_feature_names_defined_in_module(self):
        """FEATURE_NAMES constant should match get_feature_names()."""
        engine = FeatureEngine()
        assert engine.get_feature_names() == FEATURE_NAMES


class TestFeatureEngineEmptyHistory:
    """Should handle missing user history gracefully with defaults."""

    def test_empty_history_defaults(self):
        """When user_history is None, features should use safe defaults."""
        engine = FeatureEngine()
        tx = {"amount": 100.0, "timestamp": "2024-06-15T14:30:00+00:00"}
        features = engine.transform(tx, user_history=None)
        # amount_vs_user_avg (index 1) defaults to 0 (same as average)
        assert features[1] == 0.0
        # amount_vs_user_std (index 2) defaults to 0
        assert features[2] == 0.0
        # tx_count_last_5min (index 3) defaults to 0
        assert features[3] == 0.0
        # tx_count_last_1h (index 4) defaults to 0
        assert features[4] == 0.0

    def test_empty_dict_history_defaults(self):
        """When user_history is an empty dict, features should use safe defaults."""
        engine = FeatureEngine()
        tx = {"amount": 100.0, "timestamp": "2024-06-15T14:30:00+00:00"}
        features = engine.transform(tx, user_history={})
        assert features[1] == 0.0
        assert features[2] == 0.0


class TestFeatureEngineMissingFields:
    """Should handle missing optional fields gracefully."""

    def test_missing_timestamp_defaults_hour(self):
        """When timestamp is missing, hour_of_day should default to 0."""
        engine = FeatureEngine()
        tx = {"amount": 100.0}
        features = engine.transform(tx)
        assert features[5] == 0

    def test_missing_merchant_default_risk(self):
        """When merchant info is missing, merchant_risk_level should default to 0."""
        engine = FeatureEngine()
        tx = {"amount": 100.0, "timestamp": "2024-06-15T14:30:00+00:00"}
        features = engine.transform(tx)
        # merchant_risk_level is at index 7
        assert features[7] == 0.0
