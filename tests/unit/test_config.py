"""Tests for application configuration."""

import pytest
from pydantic import ValidationError

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


# --- ml_floor domain ------------------------------------------------------
#
# `ml_floor` is compared against an `ml_score`, which the whole pipeline
# reports on a 0-100 scale (`rule_score`/`ml_score` columns are documented as
# 0-100, `EnsembleScorer.combine` clamps to [0, 100]). Its domain is therefore
# exactly that scale, and the field shipped with no constraint on it.
#
# Both ends outside that domain fail silently rather than loudly, which is why
# this is a boot-time validation concern and not a scoring-time one:
#
#   * `ML_FLOOR <= 0` makes `ml_score >= floor` true for EVERY transaction,
#     including one whose model is actively reporting it as ordinary. That is
#     the pre-floor rule-only blocking the floor exists to prevent (measured:
#     `acme`/`retail` at 50,001 EUR, rule 48.59 vs threshold 40, ml 0.13), and
#     it comes back with no log and no signal.
#   * `ML_FLOOR > 100` (or `inf`) makes the agreement gate unreachable, so the
#     amount-policy branch of the rule branch is switched off for good.
#
# Either one is an operator-typed env value, so it must fail at validation/boot
# where the mistake is visible, not silently at the first scored transaction.


@pytest.mark.parametrize("bad_value", [-1.0, -0.01, 100.01, 1000.0])
def test_ml_floor_rejects_values_outside_the_score_scale(bad_value: float):
    """Out-of-domain floors must be rejected, and name the offending field."""
    with pytest.raises(ValidationError, match="ml_floor"):
        Settings(ml_floor=bad_value)


@pytest.mark.parametrize("bad_value", [-1.0, 100.01])
def test_ml_floor_rejects_a_bad_env_override_at_boot(
    bad_value: float, monkeypatch: pytest.MonkeyPatch
):
    """The deployment path is the env var, so validation must fire there too.

    Boot-time rejection is the whole point: an operator who exports a nonsense
    `ML_FLOOR` gets a refused start, not a service that quietly scores with it.
    """
    monkeypatch.setenv("ML_FLOOR", str(bad_value))
    with pytest.raises(ValidationError, match="ml_floor"):
        Settings()


@pytest.mark.parametrize("good_value", [0.0, 5.0, 100.0])
def test_ml_floor_accepts_the_score_scale_boundaries(good_value: float):
    """The bounds are inclusive and the default sits inside the domain.

    0.0 and 100.0 are legitimate configurations, not edge cases to reject:
    0.0 means "the model only has to have run", 100.0 means "only a maximal
    score counts as agreement". Closing either end would be inventing a policy
    the operator did not ask for.
    """
    assert Settings(ml_floor=good_value).ml_floor == good_value


def test_ml_floor_default_is_inside_the_validated_domain():
    """The shipped default must survive its own constraint (it did not, before)."""
    assert Settings().ml_floor == 5.0
