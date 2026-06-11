"""Tests for application configuration."""

from src.core.config import Settings, settings


def test_fraud_detection_enabled_by_default():
    """FRAUD_DETECTION_ENABLED should default to True for development."""
    assert settings.fraud_detection_enabled is True


def test_jwt_defaults():
    """JWT settings should have sensible defaults."""
    s = Settings()
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_exp_minutes == 15


def test_ensemble_weights_sum_to_one():
    """Ensemble weights should sum to 1.0."""
    total = (
        settings.ensemble_rule_weight
        + settings.ensemble_ml_weight
        + settings.ensemble_context_weight
    )
    assert abs(total - 1.0) < 0.001


def test_threshold_tiers_has_four_entries():
    """Threshold tiers should cover low, medium, high, critical."""
    tiers = settings.threshold_tiers
    assert len(tiers) == 4
    labels = [t["label"] for t in tiers]
    assert labels == ["low", "medium", "high", "critical"]


def test_threshold_tiers_strictly_increasing():
    """Each tier's min_amount should match the previous tier's max_amount + 1."""
    tiers = settings.threshold_tiers
    for i in range(len(tiers) - 1):
        assert tiers[i + 1]["min_amount"] == tiers[i]["max_amount"] + 1


def test_ollama_timeout_default():
    """Ollama timeout should default to 30 seconds."""
    assert settings.ollama_timeout == 30
