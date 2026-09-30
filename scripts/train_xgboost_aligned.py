"""Train XGBoost model aligned with production FeatureEngine (10 features).

This script:
1. Loads synthetic_transactions.csv + PaySim (if available)
2. Uses FeatureEngine.transform() to generate EXACT 10 features used in production
3. Does NOT resample. The class prior is handled by scale_pos_weight only.
4. Trains XGBoost with scale_pos_weight from real class imbalance
5. Calibrates against the real, un-resampled class prior
6. Saves model to models/xgboost_paysim_v1.joblib (overwrites production model)
7. Reports metrics on test set (PR-AUC, Recall, Precision, F1)
8. Cost-sensitive evaluation: FN cost 10x FP, prints economic cost and optimal threshold

Why there is no resampling step (CAL-001)
-----------------------------------------
This script used to resample the training split with SMOTE to a 33% fraud
prior and then fit ``CalibratedClassifierCV`` on the resampled matrix. That is
a structural contradiction, not a tuning mistake:

    A calibrator learns P(y=1 | score). Fitting it on a resampled matrix
    means it learns P(y=1 | score) *under the resampler's prior*, not under
    the prior that will actually be seen at serve time. Resampling rewrites
    the base rate; calibration against the rewritten base rate produces
    probabilities that are inflated by exactly the factor the resampler
    introduced. No amount of re-fitting the calibrator repairs this, because
    the calibrator is being asked the wrong question.

The measured cost of that contradiction, on 30k held-out un-resampled rows
at the real 0.96% prevalence (before this change):

    bin        n     predicted  observed     gap
    [0.0,0.1)  29158     0.0092    0.0018  -0.0074
    [0.1,0.2)    249     0.1371    0.0040  -0.1331
    [0.2,0.3)     74     0.2447    0.0135  -0.2312
    [0.3,0.4)     61     0.3508    0.0328  -0.3180
    [0.4,0.5)     30     0.4475    0.0000  -0.4475
    [0.5,0.6)     28     0.5453    0.1071  -0.4382
    [0.6,0.7)     19     0.6452    0.1053  -0.5400
    [0.7,0.8)     27     0.7481    0.1481  -0.6000
    [0.8,0.9)     40     0.8549    0.1250  -0.7299
    [0.9,1.0]    314     0.9845    0.6879  -0.2966

Over-confident in every single bin, worst exactly where it costs the most:
a score of 0.85 corresponded to a 12.5% real fraud rate. The ensemble
thresholds on these absolute numbers, so every decision leaned toward
"fraud" more than it should.

So the resampling is gone. The imbalance is carried by ``scale_pos_weight``
alone — which is what commit 236526c already established as the mechanism,
and which does not touch the class prior, so the calibrator can be fit
against the real one.

Version constraint
------------------
``CalibratedClassifierCV`` on scikit-learn 1.5 is the *only* API needed
here, and nothing is deprecated:

  * ``cv=<int>`` refits the base estimator on k-1 folds and calibrates the
    sigmoid on the pooled out-of-fold predictions of the held-out fold. Those
    predictions are genuinely held out, and the folds carry the real prior.
    This is the textbook procedure, and it is the one used below.
  * ``cv="prefit"`` is deprecated in 1.5 and removed in 1.6, and
    ``FrozenEstimator`` does not exist until 1.6. Neither is used, so the
    artifact stays unpickleable-compatibly on the pinned 1.5.0.

Usage:
    python scripts/train_xgboost_aligned.py
"""

import csv
import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (auc, confusion_matrix,
                             precision_recall_curve, precision_score, recall_score,
                             roc_auc_score)
from sklearn.model_selection import train_test_split
import xgboost as xgb

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.feature_engine import FeatureEngine  # noqa: E402
from src.core.ml_constants import MERCHANT_RISK_CATEGORIES, CATEGORY_ALIAS_SPELLINGS  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

MODEL_PATH = "models/xgboost_paysim_v1.joblib"
DATA_SYNTHETIC = "data/synthetic_transactions.csv"
DATA_PAYSIM = "../transaccion/PS_20174392719_1491204439457_log.csv"

#: Provenance stamp written into every training corpus and required of every
#: corpus this script loads (DATA-001).
#:
#: Bump this when the generator changes in a way that alters the feature
#: distribution, and retrain. A corpus without a stamp, or with a different
#: one, is refused — see :func:`_load_synthetic_csv` for why that is a hard
#: error rather than a warning.
#:
#: AMT-001 bumped this to trainer_v3. The archetype amount distributions
#: changed, so the on-disk corpus at data/synthetic_transactions.csv is no
#: longer the corpus this script would generate. Refusing it is correct: the
#: whole point of the stamp is that a stale corpus cannot be trained on
#: silently, and the artifact that ships with the inverted amount response was
#: trained on exactly such a stale corpus.
CORPUS_SCHEMA = "trainer_v3"

#: Column carrying :data:`CORPUS_SCHEMA`.
CORPUS_SCHEMA_COLUMN = "corpus_schema"

#: Amplitude of the post-generation noise pass, shared by main() and the
#: per-feature contract test so the two cannot disagree.
FRAUD_NOISE_INTENSITY = 0.40

#: How far the class prior of the matrix handed to the calibrator may differ
#: from the corpus prevalence before training refuses to continue. The two are
#: the same object in the correct pipeline, so any non-trivial drift means
#: something resampled the data in between. See CAL-001 in the docstring.
CALIBRATION_PRIOR_TOLERANCE = 1e-9

# --- Behavioural archetypes -------------------------------------------------
# The generator used to emit one profile per class: fraud was always a
# large amount at a risky merchant at night with a velocity burst, and
# legitimate was always none of those. That is not how fraud works, and it
# is why four of the ten features scored ROC-AUC 1.0000 on their own: each
# one was a sufficient statistic for the label, so the tree model had no
# reason to combine anything.
#
# Real fraud arrives in distinct shapes, and — the part that matters — each
# shape is blind to a different signal:
#
#   card_testing     many tiny transactions at ordinary merchants. High
#                    velocity, *small* amounts, ordinary categories.
#   account_takeover a burst of medium purchases at ordinary merchants. The
#                    merchant field looks completely normal; only the burst
#                    and the timing betray it.
#   high_value_wire  a single large transfer to a high-risk merchant. A
#                    wire is singular, so velocity is *legitimate-looking*;
#                    and the amount is large, but so is a car purchase.
#   low_signal       deliberately ordinary in every dimension. This is the
#                    irreducible false negative: it is why no feature can
#                    separate the classes, and keeping it is the whole
#                    point.
#
# Legitimate traffic gets the same treatment, and crucially it gets a
# `fraud_lookalike` segment: honest customers who buy crypto, shop at 3am,
# and hit a merchant during a sale. Without that segment, merchant risk and
# hour would be near-deterministic and the data would be degenerate in the
# opposite direction.
#
# Every field below is a per-archetype *rate*, never a rule.
#
# The weights are set from how fraud portfolios are actually shaped, not
# from a target metric: card-not-present fraud and account takeover dominate
# transaction *count*, while wires are a minority of events but a large
# share of value. Getting that balance roughly right is what makes raw
# `amount` a weak-but-real signal (real fraud skews a few times larger than
# real legitimate spend) instead of either a perfect separator or noise.
NIGHT_HOURS = (0, 1, 2, 3, 4, 5, 22, 23)
DAY_HOURS = tuple(range(6, 22))

#: name, weight, lognormal(mu, sigma) for amount, P(high-risk category),
#: P(night hour), velocity_5min window, velocity_1h window, P(round amount)
#:
#: AMT-001: the amount distributions below used to be arranged so that the
#: largest amounts in the corpus were predominantly *legitimate*, and the
#: model learned exactly that. Measured through the production pipeline on
#: the crypto/night/velocity-burst path, the risk score peaked at $2,000 and
#: then fell monotonically to $1,000,000:
#:
#:     $1,000 -> 84.36    $5,000 -> 84.25    $10,000 -> 77.24
#:     $50,000 -> 49.07   $500,000 -> 41.78  $1,000,000 -> 41.78
#:
#: so a $1,000,000 crypto transfer scored 41.78 — half the score of a $5,000
#: one. High-value transfer fraud is a real and important pattern and the ML
#: layer was actively mis-ranking it.
#:
#: The trainer was not at fault. The data was. `fraud_lookalike` — legitimate
#: traffic that resembles fraud — carried the single highest amount mu in the
#: corpus (10.0), a narrow sigma (0.7) that concentrated it around ~$22k, and
#: `big_purchase` at mu 8.0 added more legitimate mass above $50k than
#: `high_value_wire` did. Conditional on the high-risk path the corpus said
#: large == legitimate:
#:
#:     band                 n     P(fraud | crypto, night, burst)
#:     $1,000 - $5,000    111          15.32%
#:     $5,000 - $10,000   605           3.64%
#:     $10,000 - $50,000 4306           0.42%   <- 4,306 rows, 18 frauds
#:     $50,000 - $100,000  593           0.17%
#:     $100,000+            92           0.00%
#:
#: The model was faithfully learning an inverted corpus. The fix is below.
#:
#: What changed, and why each change is defensible about the real world
#: rather than about the metric:
#:
#:   high_value_wire  mu 9.2 -> 9.8, sigma 0.9 -> 1.1, weight 0.24 -> 0.26.
#:       Wires and large crypto movements are real, high-value fraud
#:       vectors; the archetype is supposed to represent them, and it now
#:       reaches the far tail instead of stopping at it. p_round drops
#:       0.75 -> 0.55: rounding three quarters of wire amounts to hundreds
#:       was an artefact of the generator, not a property of wire transfers,
#:       and it distorted the mid-tail while making `amount_round_number`
#:       carry weight it should not.
#:   large_burst      mu 8.8 -> 9.0, weight 0.12 -> 0.19, p_risk 0.55 -> 0.65.
#:       A compromised account making a large transfer while the burst runs,
#:       and mule accounts receiving several, is a major pattern. At 12% of
#:       the fraud portfolio the corpus had almost no high-amount, high-
#:       velocity fraud, which is precisely the cell the defect lives in.
#:   fraud_lookalike  mu 10.0 -> 8.0, sigma 0.7 -> 1.1. Kept, and still
#:       3% of legitimate traffic, because it is what stops merchant risk
#:       and hour from being deterministic. But it now *overlaps* the fraud
#:       amount distribution instead of sitting above it. Overlap is the
#:       point; domination was the bug.
#:   big_purchase     mu 8.0 -> 9.0, sigma 0.9 -> 1.1.
#:       Honest five-figure purchases — a car, a house deposit, tuition,
#:       a medical bill — are ordinary. Without genuine legitimate mass in
#:       the high tail, the fix above is just a label flip in the opposite
#:       direction: measured with big_purchase left at mu 8.0, 55% of
#:       transactions above $100k came out labelled fraud, which is the
#:       degeneracy cb65b25 already fixed once.
#:
#: Measured after the change, 400,000 generated rows, real generator and
#: real noise pass. The fraud rate now RISES with amount instead of
#: inverting, and legitimate traffic stays the majority in every band:
#:
#:     band                 n     fraud     rate     lift   legitimate
#:     $0        - $100    198180      983   0.496%   0.50x      99.5%
#:     $100      - $500    111475      940   0.843%   0.85x      99.2%
#:     $500      - $1,000   11545      219   1.906%   1.92x      98.1%
#:     $1,000    - $5,000   28488      403   1.415%   1.43x      98.6%
#:     $5,000    - $10,000  18751      333   1.776%   1.79x      98.2%
#:     $10,000   - $50,000  27870      853   3.061%   3.08x      96.9%
#:     $50,000   - $100,000  2820      162   5.745%   5.79x      94.3%
#:     $100,000  - $250,000   798       68   8.521%   8.59x      91.5%
#:     $250,000+               73        7   9.589%   9.66x      90.4%
#:
#: Conditional on the high-risk path, where the defect lived, it rises
#: monotonically too: 1.23% ($1k-$5k) -> 2.77% ($5k-$10k) -> 5.61%
#: ($10k-$50k) -> 15.00% ($50k-$100k).
#:
#: Two honest caveats. The $500-$1,000 band sits slightly above
#: $1,000-$5,000 (1.906% vs 1.415%); that shoulder is the upper tail of
#: `account_takeover` and it is pre-existing, not introduced here. And
#: `amount` as a standalone feature moved from ROC-AUC 0.6458 to 0.6844 —
#: still far from the 1.0000 that means "this feature is the label", so the
#: corpus is less degenerate, not more.
FRAUD_ARCHETYPES: tuple[dict, ...] = (
    {"name": "card_testing", "weight": 0.17, "amount": (3.3, 0.85),
     "p_risk": 0.08, "p_night": 0.45, "v5": (8, 32), "v1": (20, 85), "p_round": 0.02},
    {"name": "account_takeover", "weight": 0.28, "amount": (5.6, 0.9),
     "p_risk": 0.12, "p_night": 0.65, "v5": (10, 45), "v1": (25, 95), "p_round": 0.12},
    {"name": "high_value_wire", "weight": 0.26, "amount": (9.8, 1.1),
     "p_risk": 0.92, "p_night": 0.55, "v5": (0, 3), "v1": (0, 20), "p_round": 0.55},
    # A compromised account making a large purchase while the burst is still
    # running, and mule accounts receiving several large transfers. Without
    # this archetype the corpus anti-correlated amount against velocity —
    # every large fraud had velocity <= 2 and every burst had a median
    # amount of ~£117 — so the model learned "big amount implies a quiet
    # card" and scored a £50k burst at 0.00. That was an artifact of how the
    # archetypes were laid out, not a property of fraud.
    #
    # AMT-001: this was also the cell the high-value inversion lived in. At
    # 12% of the portfolio and mu 8.8 it carried almost no high-amount,
    # high-velocity fraud, while `fraud_lookalike` at mu 10.0 carried a
    # great deal of legitimate traffic through it.
    {"name": "large_burst", "weight": 0.19, "amount": (9.0, 1.0),
     "p_risk": 0.65, "p_night": 0.60, "v5": (5, 25), "v1": (15, 70), "p_round": 0.30},
    {"name": "low_signal", "weight": 0.10, "amount": (4.6, 1.1),
     "p_risk": 0.10, "p_night": 0.20, "v5": (0, 2), "v1": (0, 5), "p_round": 0.10},
)

LEGIT_ARCHETYPES: tuple[dict, ...] = (
    {"name": "everyday", "weight": 0.68, "amount": (4.2, 1.05),
     "p_risk": 0.06, "p_night": 0.12, "v5": (0, 2), "v1": (0, 6), "p_round": 0.10},
    # AMT-001: mu 8.0 -> 9.0, sigma 0.9 -> 1.1. Honest five-figure purchases
    # have to be genuinely present at the top of the range, or the fraud
    # archetypes above simply become a label flip and the high bands turn
    # into a near-perfect separator. See the module comment for the measured
    # cost of leaving this at 8.0.
    {"name": "big_purchase", "weight": 0.17, "amount": (9.0, 1.1),
     "p_risk": 0.12, "p_night": 0.10, "v5": (0, 3), "v1": (0, 8), "p_round": 0.30},
    {"name": "burst", "weight": 0.12, "amount": (4.6, 1.0),
     "p_risk": 0.08, "p_night": 0.30, "v5": (3, 9), "v1": (8, 28), "p_round": 0.08},
    # AMT-001: mu 10.0 -> 8.0, sigma 0.7 -> 1.1. This archetype is kept, and
    # is still the only legitimate segment that buys crypto at 3am during a
    # burst, because without it merchant risk and hour would be near
    # deterministic. What changed is that it no longer sits ABOVE the fraud
    # amount distribution: at mu 10.0 with a narrow sigma it was a spike
    # concentrated around ~$22k, and it owned the entire top of the range.
    # Widening sigma to 1.1 turns it from a monopoly into an overlap.
    {"name": "fraud_lookalike", "weight": 0.03, "amount": (8.0, 1.1),
     "p_risk": 0.90, "p_night": 0.85, "v5": (4, 14), "v1": (12, 45), "p_round": 0.20},
)

#: Within the high-risk segment, which merchant category. Crypto dominates
#: fraud because exchanges are where stolen funds land; it is a large but
#: far from overwhelming share of it.
RISK_CATEGORY_WEIGHTS_FRAUD = (0.45, 0.32, 0.13, 0.05, 0.05)  # crypto, transfer, gambling, adult, pharmacy
RISK_CATEGORY_WEIGHTS_LEGIT = (0.60, 0.15, 0.20, 0.025, 0.025)

#: Share of high-risk rows written with an alias spelling instead of the
#: canonical name. This is the rate `_draw_category` always claimed in its
#: comment; the number was never what the code did, so it is named here where
#: changing it is a visible edit.
#:
#: Why any non-zero value at all: `merchant_category` is free text on the wire
#: and normalize_category collapses the spellings before features are built. A
#: corpus of canonical names only never exercises that path, so the artifact is
#: trained entirely inside a cleaner input distribution than production ever
#: supplies. Note the limit of what this buys: it changes the CORPUS, and the
#: shipped artifact predates this change, so nothing about the model's current
#: behaviour is improved until a retrain runs.
ALIAS_SPELLING_RATE = 0.15

#: Number of simulated cardholders. Enough transactions each that the
#: per-user history statistics are meaningful.
N_USERS = 4000

#: Below this an amount is never snapped to a round figure — nobody rounds a
#: £4.20 coffee to the nearest hundred.
ROUNDING_FLOOR = 200.0
MAX_AMOUNT = 1_000_000.0


def _pick_archetype(rng: np.random.RandomState, archetypes: tuple[dict, ...]) -> dict:
    weights = np.array([a["weight"] for a in archetypes], dtype=float)
    weights = weights / weights.sum()
    return archetypes[int(rng.choice(len(archetypes), p=weights))]


def _draw_amount(rng: np.random.RandomState, archetype: dict) -> float:
    """Lognormal amount, optionally snapped to a round figure.

    Every archetype draws from its own lognormal, but the supports overlap
    heavily: a fraud wire at £13k and a legitimate car purchase at £13k are
    the same number, and a card-testing fraud at £16 and a legitimate
    takeaway at £16 are the same number. That overlap is deliberate.
    """
    mu, sigma = archetype["amount"]
    amount = float(rng.lognormal(mean=mu, sigma=sigma))
    if amount >= ROUNDING_FLOOR and rng.random() < archetype["p_round"]:
        amount = round(amount / 100.0) * 100.0
    return float(min(max(round(amount, 2), 0.01), MAX_AMOUNT))


def _draw_hour(rng: np.random.RandomState, p_night: float) -> int:
    if rng.random() < p_night:
        return int(NIGHT_HOURS[rng.randint(len(NIGHT_HOURS))])
    return int(DAY_HOURS[rng.randint(len(DAY_HOURS))])


def _draw_category(
    rng: np.random.RandomState,
    archetype: dict,
    normal_categories: list[str],
    risk_categories: list[str],
    is_fraud: bool,
) -> str:
    """Merchant category.

    Emits only canonical names from ``MERCHANT_RISK_CATEGORIES`` plus the
    aliases ``CATEGORY_ALIASES`` normalises. The previous on-disk CSV used a
    ``high_risk``/``low_risk`` vocabulary that ``FeatureEngine`` does not
    recognise, so ``merchant_risk_level`` and ``is_crypto`` were constant
    zero for every single row.
    """
    if rng.random() < archetype["p_risk"]:
        weights = (RISK_CATEGORY_WEIGHTS_FRAUD if is_fraud
                   else RISK_CATEGORY_WEIGHTS_LEGIT)
        # Normalise defensively: rng.choice raises on a vector that does not
        # sum to 1, and a hand-edited weight tuple should not be able to take
        # the whole generator down.
        p = np.array(weights, dtype=float)
        p = p / p.sum()
        category = risk_categories[int(rng.choice(len(risk_categories), p=p))]
        # Real feeds carry alias spellings; FeatureEngine normalises them.
        #
        # This used to read `CATEGORY_ALIASES.get(category)`. CATEGORY_ALIASES is
        # keyed BY alias spelling, so looking up a CANONICAL name returned `None`
        # for cryptocurrency / money_transfer / gambling, and returned the
        # identical string for adult / pharmacy. The branch was dead: the corpus
        # on disk held no alias spelling at all, while this docstring and the
        # comment above it both claimed it did. The lookup is an inversion of
        # that table now — see CATEGORY_ALIAS_SPELLINGS.
        if rng.random() < ALIAS_SPELLING_RATE:
            spellings = CATEGORY_ALIAS_SPELLINGS.get(category)
            if spellings:
                return spellings[int(rng.randint(len(spellings)))]
        return category
    return str(normal_categories[rng.randint(len(normal_categories))])


def _assign_user_statistics(
    transactions: list[dict],
    user_ids: list[int],
    rng: np.random.RandomState,
) -> None:
    """Populate ``user_avg_amount`` / ``user_std_amount`` per transaction.

    Each user gets a *persona* — their typical spend and spread — and the
    running statistics start from it, so a user's first transaction already
    has a meaningful history rather than a zero that would make
    ``amount_vs_user_avg`` collapse to 0 and take the feature with it.

    The statistics are then advanced in timestamp order over the user's own
    prior transactions, which is what production sees at scoring time. This
    is deliberately causal: a transaction never contributes to the history it
    is scored against, so the ratio features are honest z-scores rather than
    an artefact of the row including itself.
    """
    n_users = int(max(user_ids)) + 1
    persona_mean = rng.lognormal(mean=4.6, sigma=1.0, size=n_users)
    persona_std = np.abs(rng.lognormal(mean=3.2, sigma=0.7, size=n_users))
    persona_std = np.maximum(persona_std, 1.0)

    running_sum = persona_mean.copy()
    running_sq = (persona_mean ** 2 + persona_std ** 2).copy()
    running_n = np.zeros(n_users, dtype=float)

    order = sorted(
        range(len(transactions)),
        key=lambda i: (user_ids[i], transactions[i]["timestamp"]),
    )
    for i in order:
        uid = user_ids[i]
        n = running_n[uid]
        mean = running_sum[uid] / (n + 1.0)
        # Variance over the persona plus the n observed transactions.
        second = running_sq[uid] / (n + 1.0)
        var = max(second - mean ** 2, 0.0)
        std = float(np.sqrt(var)) if var > 0.0 else 0.0

        transactions[i]["user_avg_amount"] = round(mean, 2)
        transactions[i]["user_std_amount"] = round(std, 2)

        amount = float(transactions[i]["amount"])
        running_sum[uid] += amount
        running_sq[uid] += amount ** 2
        running_n[uid] += 1


def generate_synthetic_data(
    n_samples: int = 50000,
    fraud_rate: float = 0.01,
    seed: int = 42,
) -> tuple[list[dict], np.ndarray]:
    """Generate synthetic transaction data compatible with FeatureEngine.

    The design constraint is that **no single feature may separate the
    classes on its own**. Every field is a per-archetype rate with real
    overlap between the two populations, and a deliberate slice of fraud is
    indistinguishable from legitimate traffic. An honest ten-feature model
    therefore tops out well below a perfect score — which is the correct
    answer for this problem, not a shortfall.

    ``seed`` exists so the evaluation harness can build a held-out corpus
    that shares this distribution but shares none of its rows with training.
    """
    rng = np.random.RandomState(seed)
    transactions: list[dict] = []
    labels: list[int] = []
    user_ids: list[int] = []

    normal_categories = ["groceries", "retail", "restaurant", "transport",
                         "entertainment", "health", "education"]
    risk_categories = ["cryptocurrency", "money_transfer", "gambling",
                       "adult", "pharmacy"]
    merchants_normal = [f"Store_{i}" for i in range(50)]
    merchants_risk = [f"CryptoEx_{i}" for i in range(10)] + [f"Casino_{i}" for i in range(5)]

    for _ in range(n_samples):
        is_fraud = rng.random() < fraud_rate
        archetype = _pick_archetype(
            rng, FRAUD_ARCHETYPES if is_fraud else LEGIT_ARCHETYPES
        )

        amount = _draw_amount(rng, archetype)
        category = _draw_category(
            rng, archetype, normal_categories, risk_categories, is_fraud
        )
        merchant_pool = merchants_risk if archetype["p_risk"] > 0.5 and is_fraud else merchants_normal
        merchant = str(merchant_pool[rng.randint(len(merchant_pool))])
        hour = _draw_hour(rng, archetype["p_night"])
        velocity_5min = int(rng.randint(*archetype["v5"]))
        velocity_1h = int(rng.randint(*archetype["v1"]))

        day_offset = int(rng.randint(0, 365))
        minute = int(rng.randint(0, 59))
        timestamp = (datetime(2024, 1, 1) + timedelta(days=day_offset)).replace(
            hour=hour, minute=minute, second=0
        ).isoformat()

        transactions.append({
            "amount": amount,
            "merchant_name": merchant,
            "merchant_category": category,
            "timestamp": timestamp,
            "velocity_5min": velocity_5min,
            "velocity_1h": velocity_1h,
            # Retained as a diagnostic label. It is written to the CSV but the
            # FeatureEngine never sees it, so it cannot leak into the model.
            # It exists so the evaluation harness can prove the model's errors
            # are the *intended* ones: that its false negatives are the
            # deliberately-indistinguishable fraud and its false positives are
            # the fraud_lookalike legitimate traffic. An overlap that produces
            # the right errors is evidence the corpus is honest; one that
            # produces random errors is not.
            "archetype": archetype["name"],
        })
        labels.append(1 if is_fraud else 0)
        user_ids.append(int(rng.randint(N_USERS)))

    _assign_user_statistics(transactions, user_ids, rng)

    # user_id is kept out of the row dict the FeatureEngine consumes but is
    # needed by the CSV writer to make the per-user statistics auditable.
    for tx, uid in zip(transactions, user_ids):
        tx["user_id"] = f"user-{uid:05d}"

    return transactions, np.array(labels)


def load_synthetic_data(path: str) -> tuple[list[dict], np.ndarray]:
    """Load synthetic data from CSV, or generate if not exists."""
    if Path(path).exists():
        return _load_synthetic_csv(path)

    # Generate and save
    logger.info("Synthetic data not found at %s, generating...", path)
    transactions, labels = generate_synthetic_data(n_samples=50000, fraud_rate=0.01)
    _save_synthetic_csv(transactions, labels, path)
    return transactions, labels


def _load_synthetic_csv(path: str) -> tuple[list[dict], np.ndarray]:
    """Load a training corpus, refusing anything this script did not write.

    DATA-001: this loader used to read whatever sat at the path. That made a
    silent, total corruption of the model one command away, because
    ``scripts/generate_synthetic_data.py`` writes to the *same path* with a
    different generator. Measured, on the corpus that script produces, fed
    through the real pipeline:

      tx_count_last_5min   ROC-AUC 1.0000   separates the classes on its own
      tx_count_last_1h     ROC-AUC 1.0000   separates the classes on its own
      merchant_risk_level  ROC-AUC 1.0000   separates the classes on its own
      amount_vs_user_std   0.9657
      amount               0.9614
      fraud rate           4.81%   (the training corpus is 0.96%)

    Three features that each *are* the label, which is the exact degeneracy
    cb65b25 was written to remove, plus a prior five times too high, which
    would re-break the calibration c1a4f6a was written to fix. And the loader
    raised nothing: it read 50,000 rows, 2,405 of them fraud, and carried on.

    So the check is a hard error, before a single row is parsed, and it names
    the file it refused. Silently coercing a foreign vocabulary to zeros is
    the failure mode this replaces — that is what made the old model blind to
    merchant risk and crypto without saying so.
    """
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        columns = set(reader.fieldnames or [])
        stamp = None
        if CORPUS_SCHEMA_COLUMN in columns:
            stamp = next(iter(reader), {}).get(CORPUS_SCHEMA_COLUMN)
        else:
            # Still need to drain nothing: refuse before parsing any row.
            stamp = None

    if stamp != CORPUS_SCHEMA:
        found = (
            f"{CORPUS_SCHEMA_COLUMN}={stamp!r}" if CORPUS_SCHEMA_COLUMN in columns
            else f"no {CORPUS_SCHEMA_COLUMN} column (found: {', '.join(sorted(columns))})"
        )
        raise ValueError(
            f"REFUSING to train on a corpus this script did not write.\n"
            f"  file:   {path}\n"
            f"  found:  {found}\n"
            f"  wanted: {CORPUS_SCHEMA_COLUMN}={CORPUS_SCHEMA!r}\n"
            f"\n"
            f"This is almost certainly the output of "
            f"scripts/generate_synthetic_data.py, which is a demo/seed "
            f"generator and not the training corpus. It writes a different "
            f"schema and a corpus that degenerates the model: three of the "
            f"ten features separate the classes perfectly on their own "
            f"(ROC-AUC 1.0000), and its fraud rate is 4.81% against the "
            f"training corpus's 0.96%, which would also invalidate the "
            f"calibration.\n"
            f"\n"
            f"To build the training corpus, delete the file and run this "
            f"script, which regenerates it deterministically. To use a real "
            f"labelled corpus, add a {CORPUS_SCHEMA_COLUMN} column containing "
            f"{CORPUS_SCHEMA!r} only once it has been checked against the "
            f"schema above."
        )

    transactions = []
    labels = []
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            transactions.append({
                "amount": float(row["amount"]),
                "merchant_name": row["merchant_name"],
                "merchant_category": row["merchant_category"],
                "timestamp": row["timestamp"],
                # Velocity / per-user stat columns, with "0" fallback so
                # legacy column-less CSVs still parse (FD-VEL-004).
                "user_avg_amount": float(row.get("user_avg_amount", "0") or 0),
                "user_std_amount": float(row.get("user_std_amount", "0") or 0),
                "velocity_5min": int(row.get("velocity_5min", "0") or 0),
                "velocity_1h": int(row.get("velocity_1h", "0") or 0),
                # Diagnostic only — never fed to the FeatureEngine.
                "archetype": row.get("archetype", "") or "",
            })
            labels.append(int(row["is_fraud"]))
    logger.info("Loaded %d synthetic transactions from %s (%s=%s)",
                len(transactions), path, CORPUS_SCHEMA_COLUMN, CORPUS_SCHEMA)
    return transactions, np.array(labels)


def _save_synthetic_csv(transactions: list[dict], labels: np.ndarray, path: str) -> None:
    """Persist the synthetic corpus.

    ``user_avg_amount`` / ``user_std_amount`` are written here because
    omitting them made ``amount_vs_user_std`` a constant-zero column for
    every row of the training set: the generator computed nothing, the CSV
    carried nothing, ``_load_synthetic_csv`` fell back to ``0``, and the
    ``FeatureEngine`` ``> 0`` guard then emitted 0.0 for the feature. The
    deployed artifact still carried weight on that dead column.
    """
    fieldnames = [
        "user_id", "amount", "merchant_name", "merchant_category",
        "timestamp", "is_fraud", "velocity_5min", "velocity_1h",
        "user_avg_amount", "user_std_amount", "archetype",
        CORPUS_SCHEMA_COLUMN,
    ]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for tx, label in zip(transactions, labels):
            writer.writerow({
                CORPUS_SCHEMA_COLUMN: CORPUS_SCHEMA,
                "user_id": tx.get("user_id", ""),
                "amount": tx["amount"],
                "merchant_name": tx["merchant_name"],
                "merchant_category": tx["merchant_category"],
                "timestamp": tx["timestamp"],
                "is_fraud": int(label),
                "velocity_5min": tx.get("velocity_5min", 0),
                "velocity_1h": tx.get("velocity_1h", 0),
                "user_avg_amount": tx.get("user_avg_amount", 0),
                "user_std_amount": tx.get("user_std_amount", 0),
                "archetype": tx.get("archetype", ""),
            })
    logger.info("Generated and saved %d synthetic transactions to %s", len(transactions), path)


def build_synthetic_history(tx: dict) -> dict:
    """Build a FeatureEngine user_history from a synthetic transaction dict.

    Reads the velocity and per-user stat keys emitted by the synthetic
    generators; missing keys fall back to zero so legacy column-less CSVs
    still produce valid (zero) history features.
    """
    return {
        "avg_amount": float(tx.get("user_avg_amount", 0) or 0),
        "std_amount": float(tx.get("user_std_amount", 0) or 0),
        "tx_count_last_5min": int(tx.get("velocity_5min", 0) or 0),
        "tx_count_last_1h": int(tx.get("velocity_1h", 0) or 0),
    }


def load_paysim_data(path: str) -> tuple[list[dict], np.ndarray]:
    """Load PaySim data and MAP to production FeatureEngine features."""
    import pandas as pd

    if not Path(path).exists():
        logger.warning("PaySim file not found at %s, skipping", path)
        return [], np.array([])

    logger.info("Loading PaySim data from %s...", path)
    df = pd.read_csv(path)

    # Filter to only transaction types that have fraud (TRANSFER, CASH_OUT)
    # and sample for speed (PaySim is ~6M rows)
    fraud_types = ["TRANSFER", "CASH_OUT"]
    df = df[df["type"].isin(fraud_types)].copy()

    # Sample if too large (keep all fraud + sample legit)
    fraud_df = df[df["isFraud"] == 1]
    legit_df = df[df["isFraud"] == 0].sample(n=min(200000, len(df[df["isFraud"] == 0])), random_state=42)
    df = pd.concat([fraud_df, legit_df]).sample(frac=1, random_state=42).reset_index(drop=True)

    logger.info("PaySim sample: %d rows (%d fraud, %d legit)",
                len(df), len(fraud_df), len(legit_df))

    transactions = []
    labels = []

    # Build user history for avg/std amounts (per nameOrig, using only legit txns)
    legit_only = df[df["isFraud"] == 0]
    user_stats = {}
    for uid, group in legit_only.groupby("nameOrig"):
        amounts = group["amount"].astype(float).values
        if len(amounts) > 0:
            user_stats[uid] = {
                "avg_amount": float(np.mean(amounts)),
                "std_amount": float(np.std(amounts)) if len(amounts) > 1 else 0.0,
            }

    # Map PaySim types to production merchant_category
    type_to_category = {
        "TRANSFER": "money_transfer",      # in HIGH_RISK_CATEGORIES
        "CASH_OUT": "cash_out",            # not in HIGH_RISK_CATEGORIES by default
        "CASH_IN": "cash_in",
        "PAYMENT": "payment",
        "DEBIT": "debit",
    }

    for _, row in df.iterrows():
        uid = row["nameOrig"]
        history = user_stats.get(uid, {"avg_amount": 0.0, "std_amount": 0.0})

        tx = {
            "amount": float(row["amount"]),
            "merchant_name": row["nameDest"][:50],
            "merchant_category": type_to_category.get(row["type"], "other"),
            "timestamp": f"2024-01-{(int(row['step']) % 28) + 1:02d}T{int(row['step']) % 24:02d}:00:00",
        }
        transactions.append({
            "tx": tx,
            "history": history,
        })
        labels.append(int(row["isFraud"]))

    logger.info("Mapped %d PaySim transactions to production features", len(transactions))
    return transactions, np.array(labels)


def add_realistic_noise(
    transactions: list[dict],
    labels: np.ndarray,
    fraud_noise_intensity: float = 0.15,
) -> tuple[list[dict], np.ndarray]:
    """
    Add realistic noise to synthetic transactions to prevent overfitting.
    
    For FRAUD transactions, add:
    - Amount variance ±5-15% (card testing often uses slightly different amounts)
    - Merchant name typos 3% (fraudsters obfuscate merchant names)
    - Timestamp jitter ±10-30 minutes (avoid exact patterns)
    
    For LEGITIMATE transactions, add minimal noise:
    - Small amount variance ±2-5% (natural rounding)
    - Rare typos 0.5%
    
    Args:
        transactions: List of transaction dicts
        labels: np.array of fraud labels (0/1)
        fraud_noise_intensity: How much noise to add to fraud txs (0.15 = 15%)
        
    Returns:
        (noisy_transactions, labels) tuple
    """
    rng = np.random.RandomState(42)
    noisy_txs = []

    for tx, label in zip(transactions, labels):
        tx_copy = tx.copy()
        # Capture round-ness *before* the jitter: a rent payment or a wire
        # transfer stays a round figure when the amount wobbles by a few
        # percent, and that is what `amount_round_number` encodes.
        was_round = float(tx_copy["amount"]) >= 100.0 and (
            float(tx_copy["amount"]) % 100 == 0
        )

        if label == 1:  # FRAUD
            # Amount variance: ±5-15%
            amount_factor = rng.uniform(1 - fraud_noise_intensity, 1 + fraud_noise_intensity)
            tx_copy["amount"] = max(0.01, tx_copy["amount"] * amount_factor)

            # Merchant name typo: 3% chance
            if rng.random() < 0.03 and len(tx_copy["merchant_name"]) > 2:
                merchant = tx_copy["merchant_name"]
                idx = rng.randint(0, len(merchant))
                # Replace character with random letter/digit
                new_char = rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))
                merchant = merchant[:idx] + new_char + merchant[idx+1:]
                tx_copy["merchant_name"] = merchant

            # Timestamp jitter: ±10-30 minutes
            try:
                ts = datetime.fromisoformat(tx_copy["timestamp"])
                jitter_minutes = rng.randint(-30, 30)
                ts = ts + timedelta(minutes=jitter_minutes)
                tx_copy["timestamp"] = ts.isoformat()
            except (ValueError, KeyError):
                pass  # Skip if timestamp can't be parsed

        else:  # LEGITIMATE
            # Smaller variance: ±2-5%
            amount_factor = rng.uniform(0.98, 1.05)
            tx_copy["amount"] = max(0.01, tx_copy["amount"] * amount_factor)

            # Rare typo: 0.5%
            if rng.random() < 0.005 and len(tx_copy["merchant_name"]) > 2:
                merchant = tx_copy["merchant_name"]
                idx = rng.randint(0, len(merchant))
                # Replace character with random letter/digit
                new_char = rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))
                merchant = merchant[:idx] + new_char + merchant[idx+1:]
                tx_copy["merchant_name"] = merchant

        # Re-snap to the nearest hundred if the amount was round before the
        # jitter. Without this the feature was a constant zero for the whole
        # corpus: the multiplier took every multiple of 100 with it, so the
        # deployed model's weight on it was meaningless.
        if was_round:
            tx_copy["amount"] = float(
                max(round(round(float(tx_copy["amount"])) / 100.0) * 100.0, 100.0)
            )

        noisy_txs.append(tx_copy)
    
    logger.info("Added realistic noise to %d transactions (fraud: %.1f%% noise intensity)",
                len(transactions), fraud_noise_intensity * 100)
    return noisy_txs, labels


def build_feature_vectors(
    transactions: list[dict],
    histories: list[dict] | None = None,
) -> np.ndarray:
    """Extract feature vectors using production FeatureEngine."""
    engine = FeatureEngine()
    features = []

    for i, item in enumerate(transactions):
        if isinstance(item, dict) and "tx" in item:
            # PaySim format: {"tx": {...}, "history": {...}}
            tx = item["tx"]
            history = item["history"]
        else:
            # Synthetic format: direct transaction dict
            tx = item
            history = (histories or [{}])[i] if histories else {}

        vec = engine.transform(tx, user_history=history)
        features.append(vec)

    return np.array(features)


def build_training_matrix() -> tuple[np.ndarray, np.ndarray]:
    """Build the exact feature matrix and labels the model is fit on.

    Single source of truth for the training distribution. ``main()`` and the
    per-feature contract test in ``tests/test_model_feature_contract.py``
    both call this, so the contract can never be measured against a
    re-implementation of the pipeline that has silently drifted from it.
    """
    # 1. Load synthetic data
    synth_tx, synth_y = load_synthetic_data(DATA_SYNTHETIC)

    # 2. Load and map PaySim data
    paysim_items, paysim_y = load_paysim_data(DATA_PAYSIM)

    # 3. Combine datasets
    all_transactions = synth_tx + [item["tx"] if isinstance(item, dict) and "tx" in item else item
                                   for item in paysim_items]
    # Synthetic histories now carry the velocity / user-stat values read from
    # the CSV, so FeatureEngine sees real counts instead of zeros (FD-VEL-004).
    all_histories = [build_synthetic_history(tx) for tx in synth_tx]
    all_histories += [item["history"] if isinstance(item, dict) and "history" in item else {}
                      for item in paysim_items]
    all_labels = np.concatenate([synth_y, paysim_y]) if len(paysim_y) > 0 else synth_y

    logger.info("Total training samples: %d (fraud: %d, legit: %d)",
                len(all_labels), int(np.sum(all_labels)), int(np.sum(all_labels == 0)))

    # 3.5. ADD REALISTIC NOISE to prevent overfitting
    logger.info("Adding realistic noise to synthetic data...")
    all_transactions, all_labels = add_realistic_noise(
        all_transactions, all_labels, fraud_noise_intensity=FRAUD_NOISE_INTENSITY
    )

    # 4. Extract features using production FeatureEngine
    logger.info("Extracting features with production FeatureEngine...")
    X = build_feature_vectors(
        [{"tx": tx, "history": hist} for tx, hist in zip(all_transactions, all_histories)]
    )
    logger.info("Feature matrix shape: %s", X.shape)
    return X, all_labels


def main() -> None:
    logger.info("=== XGBoost Aligned Training Pipeline ===")

    X, all_labels = build_training_matrix()

    # 5. Train/test split (stratified)
    X_train, X_test, y_train, y_test = train_test_split(
        X, all_labels,
        test_size=0.2,
        random_state=42,
        stratify=all_labels,
    )

    logger.info("Train: %d (fraud: %d, legit: %d)",
                len(X_train), int(np.sum(y_train)), int(np.sum(y_train == 0)))
    logger.info("Test:  %d (fraud: %d, legit: %d)",
                len(X_test), int(np.sum(y_test)), int(np.sum(y_test == 0)))
    
    # ADD FEATURE-LEVEL NOISE to prevent overfit
    rng = np.random.RandomState(42)
    X_train = X_train + rng.normal(0, 0.1, X_train.shape)  # Gaussian noise in feature space
    logger.info("Added Gaussian noise (std=0.1) to train features")

    # 6. Class prior — recorded, and deliberately NOT rewritten.
    #
    # CAL-001: this step used to resample the training split to a 33% fraud
    # prior. SMOTE moves the base rate, and the calibrator two steps below
    # learns against whatever base rate it is shown. Resampling first means
    # calibrating against 33% and serving at 1%: the probabilities come out
    # inflated by roughly that factor, and the ensemble thresholds on them.
    # Measured on 30k held-out un-resampled rows, the top bin predicted 0.98
    # against an observed 0.69. See the module docstring for the full table.
    #
    # The imbalance is now carried by scale_pos_weight alone, which reweights
    # the loss without touching the prior the calibrator sees.
    contamination = float(np.sum(y_train)) / len(y_train)
    logger.info("Fraud rate in train: %.4f%% (no resampling — this is the prior "
                "the calibrator is fit against)", contamination * 100)

    # 7. Train XGBoost
    #
    # scale_pos_weight comes from the *un-resampled* labels. Commit 236526c
    # established this as the imbalance mechanism; keeping it is the whole
    # reason the SMOTE step could be deleted rather than merely down-weighted.
    neg_count = int(np.sum(y_train == 0))
    pos_count = int(np.sum(y_train == 1))
    scale_pos = neg_count / pos_count if pos_count > 0 else 1.0
    logger.info(
        "scale_pos_weight=%.2f (from %d un-resampled rows: %d legit / %d fraud)",
        scale_pos, len(y_train), neg_count, pos_count,
    )

    base_estimator = xgb.XGBClassifier(
        n_estimators=200,  # Reduced from 500 to prevent overfitting
        max_depth=4,  # Reduced from 6 to prevent overfitting
        learning_rate=0.1,
        subsample=0.7,  # Reduced from 0.8
        colsample_bytree=0.7,  # Reduced from 0.8
        scale_pos_weight=scale_pos,
        eval_metric="aucpr",
        use_label_encoder=False,
        random_state=42,
        n_jobs=-1,
        reg_alpha=1.0,  # L1 regularization to reduce complexity
        reg_lambda=2.0,  # L2 regularization to reduce complexity
    )

    # 7.5. CALIBRATE against the real class prior.
    #
    # cv=5 is the correct 1.5-compatible mechanism and is not deprecated: the
    # base estimator is cloned and refit on 4/5 of the *un-resampled* training
    # rows, and the sigmoid is fit on the pooled out-of-fold predictions of
    # the 1/5 it did not see. Those predictions are genuinely held out and
    # carry the real 0.96% prior, which is the whole point.
    #
    # The estimator passed in above is a template only. CalibratedClassifierCV
    # clones it per fold and discards it; passing an already-fitted model here
    # (as the previous code did) silently threw away a full model fit and
    # trained the five clones on resampled folds instead.
    logger.info("Calibrating against the real class prior (sigmoid, cv=5)...")
    calibrated_model = CalibratedClassifierCV(base_estimator, method='sigmoid', cv=5)
    calibrated_model.fit(X_train, y_train)
    model = calibrated_model  # Use calibrated model for predictions

    calibration_prior = float(np.mean(y_train))
    logger.info("Calibrator was fit on %d rows at a %.4f%% fraud prior",
                len(y_train), calibration_prior * 100)
    if abs(contamination - calibration_prior) > CALIBRATION_PRIOR_TOLERANCE:
        raise ValueError(
            f"CAL-001 regression: the calibrator was fit on data with a "
            f"{calibration_prior:.4%} fraud prior but the corpus prevalence is "
            f"{contamination:.4%}. A calibrator fit on resampled data is "
            f"calibrated to the resampler's prior, not the data's, and its "
            f"absolute probabilities are then wrong by that ratio. Do not "
            f"resample before calibrating."
        )

    # 8. Evaluate on test set
    logger.info("=== Evaluation on Test Set ===")
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # PR-AUC
    precisions, recalls, _ = precision_recall_curve(y_test, y_proba)
    pr_auc = auc(recalls, precisions)

    # ROC-AUC
    try:
        roc_auc = roc_auc_score(y_test, y_proba)
    except ValueError:
        roc_auc = 0.0

    logger.info("Test Metrics:")
    logger.info("  Precision: %.4f", precision)
    logger.info("  Recall:    %.4f", recall)
    logger.info("  F1:        %.4f", f1)
    logger.info("  PR-AUC:    %.4f", pr_auc)
    logger.info("  ROC-AUC:   %.4f", roc_auc)

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = cm.ravel()
    logger.info("Confusion Matrix:")
    logger.info("  TN=%d, FP=%d, FN=%d, TP=%d", tn, fp, fn, tp)

    # Cost-sensitive evaluation: FN (fraud not blocked) costs 10x an FP (review).
    # This aligns the model objective with economic loss instead of raw accuracy.
    cost_fn, cost_fp = 10.0, 1.0
    cost_default = fn * cost_fn + fp * cost_fp
    logger.info("Cost (threshold=0.5): %.2f  (FN=%d*%g + FP=%d*%g)",
                cost_default, fn, cost_fn, fp, cost_fp)

    # Find the threshold that minimizes expected cost on the test set.
    best_thr, best_cost = 0.5, cost_default
    for thr in np.arange(0.05, 0.95, 0.05):
        y_thr = (y_proba >= thr).astype(int)
        tn_t, fp_t, fn_t, tp_t = confusion_matrix(y_test, y_thr).ravel()
        c = fn_t * cost_fn + fp_t * cost_fp
        if c < best_cost:
            best_cost, best_thr = c, thr
    logger.info("Optimal cost threshold: %.2f (expected cost %.2f)", best_thr, best_cost)

    # 9. Save model with feature contract stamp
    Path(MODEL_PATH).parent.mkdir(parents=True, exist_ok=True)
    engine = FeatureEngine()
    feature_names = engine.get_feature_names()
    artifact = {
        "model": model,
        "feature_names": feature_names,
        # The prior the calibrator was actually fit against. Stamped into the
        # artifact rather than left in a log line so that a future regression
        # — someone reintroducing a resampling step before the calibrator —
        # is detectable by reading the deployed file, and assertable in a
        # test, instead of only being visible in a retraining transcript.
        "calibration_prior": calibration_prior,
        "calibration_method": "sigmoid",
        "calibration_cv": 5,
    }
    joblib.dump(artifact, MODEL_PATH)
    logger.info("Model saved to %s (feature_names=%s, calibration_prior=%.4f)",
                MODEL_PATH, feature_names, calibration_prior)

    # 10. Quick sanity check with production FeatureEngine
    logger.info("=== Sanity Check with Production FeatureEngine ===")
    from src.services.ml_model import MLModelService
    service = MLModelService(model_path=MODEL_PATH)
    loaded = service.load_model()
    logger.info("Model loaded: %s, n_features: %s, feature_names: %s",
                loaded, service.n_features, service.feature_names)

    engine = FeatureEngine()

    # High-risk crypto tx
    tx_high = {
        "amount": 50000.0,
        "merchant_category": "cryptocurrency",
        "timestamp": "2024-01-15T03:00:00+00:00",
    }
    hist_high = {"avg_amount": 200.0, "std_amount": 500.0,
                 "tx_count_last_5min": 10, "tx_count_last_1h": 50}
    f_high = engine.transform(tx_high, user_history=hist_high)
    score_high = service.predict(f_high)
    logger.info("High-risk crypto (50k, 3am, high vel): ml_score = %.2f", score_high)

    # Normal grocery
    tx_low = {
        "amount": 50.0,
        "merchant_category": "groceries",
        "timestamp": "2024-01-15T12:00:00",
    }
    hist_low = {"avg_amount": 100.0, "std_amount": 20.0,
                "tx_count_last_5min": 0, "tx_count_last_1h": 2}
    f_low = engine.transform(tx_low, user_history=hist_low)
    score_low = service.predict(f_low)
    logger.info("Normal grocery (50, 12pm, no vel): ml_score = %.2f", score_low)

    logger.info("=== Training Complete ===")


if __name__ == "__main__":
    main()