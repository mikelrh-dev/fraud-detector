"""Ensemble scorer tests — weighted math, threshold tiers, classification.

Tests for the ensemble scoring layer that combines rule and ML scores
into a single risk score with dynamic thresholds.
"""

import pytest

from src.services.ensemble import EnsembleScorer


class TestEnsembleCombine:
    """Weighted combination of rule and ML scores."""

    def test_default_weights(self):
        """Default weights (rule=0.45, ml=0.45, ctx=0.10) → 90 without context."""
        scorer = EnsembleScorer()
        score = scorer.combine(rule_score=100, ml_score=100)
        assert score == 90.0

    def test_custom_weights_exact_math(self):
        """rule_score=60, ml_score=80, weights={rules:0.4, ml:0.6} → 72."""
        scorer = EnsembleScorer()
        score = scorer.combine(
            rule_score=60,
            ml_score=80,
            weights={"rule": 0.4, "ml": 0.6},
        )
        assert score == 72.0

    def test_context_weight_included(self):
        """rule=60, ml=80, ctx=50, weights={rule:0.4, ml:0.4, ctx:0.2} → 66."""
        scorer = EnsembleScorer()
        score = scorer.combine(
            rule_score=60,
            ml_score=80,
            context_score=50,
            weights={"rule": 0.4, "ml": 0.4, "context": 0.2},
        )
        assert score == 66.0

    def test_zero_scores(self):
        """All scores zero should produce zero."""
        scorer = EnsembleScorer()
        score = scorer.combine(rule_score=0, ml_score=0)
        assert score == 0.0

    def test_scores_capped_at_100(self):
        """Scores above 100 should be capped."""
        scorer = EnsembleScorer()
        score = scorer.combine(
            rule_score=100,
            ml_score=100,
            weights={"rule": 0.6, "ml": 0.6},  # exceeds 100
        )
        assert score == 100.0

    def test_only_rule_score(self):
        """If only rule score is non-zero, ensemble equals weighted rule."""
        scorer = EnsembleScorer()
        score = scorer.combine(
            rule_score=80,
            ml_score=0,
            weights={"rule": 0.5, "ml": 0.5},
        )
        assert score == 40.0


class TestEnsembleThreshold:
    """Dynamic threshold lookup by amount tier."""

    def test_low_tier_threshold(self):
        """Amount $0-1000 → threshold 70."""
        scorer = EnsembleScorer()
        assert scorer.get_threshold(0) == 70
        assert scorer.get_threshold(500) == 70
        assert scorer.get_threshold(1000) == 70

    def test_medium_tier_threshold(self):
        """Amount $1001-10000 → threshold 60."""
        scorer = EnsembleScorer()
        assert scorer.get_threshold(1001) == 60
        assert scorer.get_threshold(5000) == 60
        assert scorer.get_threshold(10000) == 60

    def test_high_tier_threshold(self):
        """Amount $10001-50000 → threshold 50."""
        scorer = EnsembleScorer()
        assert scorer.get_threshold(10001) == 50
        assert scorer.get_threshold(25000) == 50
        assert scorer.get_threshold(50000) == 50

    def test_critical_tier_threshold(self):
        """Amount > $50000 → threshold 40."""
        scorer = EnsembleScorer()
        assert scorer.get_threshold(50001) == 40
        assert scorer.get_threshold(100000) == 40

    def test_negative_amount_uses_low_tier(self):
        """Negative amount should default to lowest tier."""
        scorer = EnsembleScorer()
        assert scorer.get_threshold(-100) == 70


class TestEnsembleClassification:
    """Classification logic based on score vs threshold."""

    def test_score_below_threshold_legitimate(self):
        """score (69) < threshold (70) → 'legitimate'."""
        scorer = EnsembleScorer()
        result = scorer.classify(69, 70)
        assert result == "legitimate"

    def test_score_at_threshold_review(self):
        """score (70) == threshold (70) → 'review'."""
        scorer = EnsembleScorer()
        result = scorer.classify(70, 70)
        assert result == "review"

    def test_score_above_threshold_fraud(self):
        """score (75) > threshold (70) → 'fraud'."""
        scorer = EnsembleScorer()
        result = scorer.classify(75, 70)
        assert result == "fraud"

    def test_score_zero_low_threshold_legitimate(self):
        """score (0) < threshold (40) → 'legitimate'."""
        scorer = EnsembleScorer()
        result = scorer.classify(0, 40)
        assert result == "legitimate"

    def test_score_way_above_threshold_fraud(self):
        """score (100) > threshold (40) → 'fraud'."""
        scorer = EnsembleScorer()
        result = scorer.classify(100, 40)
        assert result == "fraud"

    def test_integration_combine_classify(self):
        """End-to-end: combine scores then classify."""
        scorer = EnsembleScorer()
        amount = 500
        rule_score = 80
        ml_score = 60
        threshold = scorer.get_threshold(amount)
        ensemble_score = scorer.combine(rule_score=rule_score, ml_score=ml_score)
        classification = scorer.classify(ensemble_score, threshold)
        # rule=80*0.45=36, ml=60*0.45=27 → 63, threshold=70
        assert threshold == 70
        assert ensemble_score == pytest.approx(63.0)
        assert classification == "legitimate"
