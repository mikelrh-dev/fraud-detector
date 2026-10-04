"""RED-phase regression tests for the two Phase-2 manifest defects.

Lives OUTSIDE the repo on purpose: acceptance criterion 4 requires
`git status --short` to show only the three dirty files, so these cannot be
landed yet. They are the TDD red-green evidence for this fix.

Run from the repo root:
    .venv\Scripts\python.exe -m pytest <this file> -v
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from scripts import evaluate_model as E
from src.services.scoring_service import ScoringService

# ---------------------------------------------------------------- fixtures --

# A tiny labelled corpus. 4 legit rows (y == 0).sum() == 4, two of them frauds
# false positives by policy design:
#
#   row 1  legit, rule 90 > threshold 70, amount 200 well under the critical
#          floor -> REVIEW. Labelled legitimate, routed to an analyst.
#   row 4  fraud, ml 80 > threshold 50                  -> FRAUD.
#   row 5  fraud, rule 55 > threshold 50 but amount 6000 < floor,
#          ml 30 < 50                                   -> LEGITIMATE.
#
# So the label-zero count is 4 while the routed "legitimate" count is rows
# 0, 2, 3, 5 -> 4... which collides. Row 5 is therefore given a rule score that
# reaches review, making the routed legitimate count 3 and the two quantities
# genuinely different. Without that collision the defect is invisible here.
Y = np.array([0, 0, 0, 0, 1, 1])
AMOUNTS = np.array([100.0, 200.0, 300.0, 400.0, 5000.0, 6000.0])
RULE = np.array([10.0, 90.0, 10.0, 10.0, 55.0, 55.0])
ML = np.array([5.0, 5.0, 5.0, 5.0, 80.0, 95.0])
CTX = np.array([0.0, 0.0, 0.0, 0.0, 60.0, 10.0])


def _decision():
    return E.report_decision_blocks(
        "test", Y, AMOUNTS, RULE, ML, context_scores=CTX, archetypes=None
    )


def _tx(**over):
    tx = {
        "amount": 120.0,
        "merchant_name": "Supermercado Norte",
        "merchant_category": "grocery",
        "timestamp": "2026-01-15T14:00:00+00:00",
        "velocity_5min": 0,
        "velocity_1h": 0,
    }
    tx.update(over)
    return tx


# ==================================================== DEFECT 1 ============
# `legitimate_rows` meant two different things: (y == 0).sum() in the ML and
# ensemble blocks, and "rows the routed policy called legitimate" in the routed
# block. Same key, two denominators -- any rate compared across blocks is
# arithmetic on two different quantities.


@pytest.mark.parametrize("name", ["ensemble", "routed", "analyst_queue"])
def test_legitimate_rows_is_the_label_zero_denominator_everywhere(name: str) -> None:
    block = _decision()[name]
    assert block["legitimate_rows"] == int((Y == 0).sum()) == 4, (
        f"{name}.legitimate_rows = {block['legitimate_rows']}, expected 4. "
        "It must be (y == 0).sum() -- the denominator of false_positive_rate "
        "and of fp + tn -- in EVERY block."
    )


@pytest.mark.parametrize("name", ["ensemble", "routed", "analyst_queue"])
def test_legitimate_rows_stays_the_denominator_of_its_own_rates(name: str) -> None:
    """The internal-consistency identity the ML blocks already satisfy."""
    block = _decision()[name]
    assert block["fp"] + block["tn"] == block["legitimate_rows"]
    assert block["tp"] + block["fn"] == block["frauds"]
    assert block["flagged_rows"] == block["tp"] + block["fp"]


@pytest.mark.parametrize("name", ["routed", "analyst_queue"])
def test_verdict_counts_carry_their_own_explicit_keys(name: str) -> None:
    """Verdict distribution is real data and needs its own keys."""
    block = _decision()[name]
    for key in ("verdict_fraud", "verdict_review", "verdict_legitimate"):
        assert key in block, (
            f"{name} publishes no {key}. The routed verdict distribution is a "
            "different quantity from the label distribution and must not be "
            "smuggled in under legitimate_rows."
        )


@pytest.mark.parametrize("name", ["routed", "analyst_queue"])
def test_verdict_counts_sum_to_the_rows_they_partition(name: str) -> None:
    block = _decision()[name]
    total = block["verdict_fraud"] + block["verdict_review"] + block["verdict_legitimate"]
    assert total == block["rows"] == len(Y), (
        f"{name}: verdicts sum to {total}, rows = {block['rows']}"
    )


def test_the_verdict_distribution_is_not_the_label_distribution() -> None:
    """Guards against 'fixing' this by making both keys the same number.

    If verdict_legitimate ever equals legitimate_rows on this corpus the two
    quantities have been collapsed again, and the test that catches it is this
    one rather than a rate that happens to look plausible.
    """
    routed = _decision()["routed"]
    assert routed["verdict_legitimate"] != routed["legitimate_rows"], (
        "verdict_legitimate == legitimate_rows: the label-zero count and the "
        "routed 'legitimate' count have been collapsed into one number again"
    )


# ==================================================== DEFECT 2 ============
# The decision blocks were measured with recent_transactions=0 and
# graph_features={}, so a row the corpus marks as a velocity burst was scored
# as if the user had been quiet for five minutes. Production reads velocity
# before scoring (velocity_store.get_counts precedes compute_scores), so the
# manifest forked away from the shipped system.


def test_row_velocity_reaches_the_rule_layer() -> None:
    """A burst row must score differently from the same row at velocity 0."""
    quiet, burst = _tx(velocity_5min=0), _tx(velocity_5min=9)
    scores, _ = E.rule_and_context_scores([quiet, burst])
    assert scores[1] > scores[0], (
        "velocity_5min=9 scored the same as velocity_5min=0 "
        f"({scores[0]}). high_velocity fires above 3 recent transactions, so "
        "the rule layer cannot see a burst without recent_transactions."
    )


def test_row_velocity_reaches_the_context_layer() -> None:
    _, context = E.rule_and_context_scores([_tx(velocity_5min=9)])
    assert context[0] > 0.0, (
        f"context layer is {context[0]} for a row with velocity_5min=9. "
        "compute_scores derives it from recent_transactions, so a hard 0.0 "
        "makes the 0.15 context weight a constant handicap."
    )


def test_context_score_matches_the_production_formula() -> None:
    """The harness must not invent its own context arithmetic.

    Pinned against the real `compute_scores`. The ML layer is handed as absent,
    which makes `EnsembleScorer.combine` redistribute its 0.25 across the two
    layers that did produce a value -- so the expectation is
    (rule*rule_w + ctx*ctx_w) / (rule_w + ctx_w), not a plain sum.
    """
    weights = E.settings
    for recent in (0, 3, 7, 15):
        tx = _tx(velocity_5min=recent)
        context = E.offline_context(recent_transactions=recent)
        rule_score, _ = E._RULE_ENGINE.evaluate(tx, context)
        service = ScoringService(ml_service=_UnavailableML(), rule_engine=E._RULE_ENGINE)

        result = asyncio.run(
            service.compute_scores(
                dict(tx),
                context,
                {"avg_amount": 100.0, "std_amount": 10.0,
                 "tx_count_last_5min": recent, "tx_count_last_1h": recent},
            )
        )
        context_score = E.context_score_from_velocity(recent)
        rule_w, ctx_w = weights.ensemble_rule_weight, weights.ensemble_context_weight
        expected = (rule_score * rule_w + context_score * ctx_w) / (rule_w + ctx_w)
        assert result.ensemble_score == pytest.approx(expected, abs=1e-9), (
            f"recent={recent}: production ensemble {result.ensemble_score} != "
            f"{expected}. The harness mirrors this formula; if production "
            "changes, this test fails first."
        )
        assert context_score == min(recent / 10.0 * 100, 100.0)


def test_a_cold_start_row_is_still_scored() -> None:
    """The honest caveat is that graph is missing -- not that velocity is."""
    scores, context = E.rule_and_context_scores([_tx(velocity_5min=0)])
    assert scores[0] >= 0.0 and context[0] == 0.0


def test_offline_context_declares_the_graph_gap_explicitly() -> None:
    context = E.offline_context(recent_transactions=4)
    assert context["graph_features"] == {}, "no static corpus has a fraud graph"
    assert context["recent_transactions"] == 4
    assert context["merchant_blacklist"] == E.settings.merchant_blacklist


class _UnavailableML:
    """ML absent, so compute_scores keeps only the rule and context layers."""

    is_available = False

    def predict(self, features):  # pragma: no cover - never called
        raise AssertionError("compute_scores must not call an unavailable model")
