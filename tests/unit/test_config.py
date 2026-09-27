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


def test_threshold_tiers_are_contiguous_half_open_intervals():
    """Tiers must tile the amount axis with no gaps and no overlaps.

    Each tier is a half-open interval ``[min_amount, max_amount)``, so the
    next tier's ``min_amount`` must equal this tier's ``max_amount`` exactly.
    A ``+ 1`` step (the old expectation) left float amounts in between
    unmatched and silently fell through to the default threshold.
    """
    tiers = settings.threshold_tiers
    for i in range(len(tiers) - 1):
        assert tiers[i + 1]["min_amount"] == tiers[i]["max_amount"], (
            f"gap/overlap between {tiers[i]['label']} and {tiers[i + 1]['label']}"
        )


def test_threshold_tiers_cover_from_zero_to_infinity():
    """The first tier must start at 0 and the last must be unbounded above."""
    tiers = settings.threshold_tiers
    assert tiers[0]["min_amount"] == 0
    assert tiers[-1]["max_amount"] == float("inf")


def test_threshold_tiers_thresholds_decrease_with_amount():
    """Higher amounts must be classified against a lower threshold."""
    thresholds = [t["threshold"] for t in settings.threshold_tiers]
    assert thresholds == sorted(thresholds, reverse=True), (
        f"thresholds must decrease as amount grows, got {thresholds}"
    )


def test_ollama_timeout_default():
    """Ollama timeout should default to 30 seconds."""
    assert settings.ollama_timeout == 30
