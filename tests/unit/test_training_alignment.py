"""Unit tests for training-pipeline velocity alignment (FD-VEL-004).

Verifies that both synthetic generators persist velocity columns, the CSV
save/load round-trip keeps them (with a "0" fallback for legacy column-less
CSVs), and synthetic histories propagate real velocity values into the
production FeatureEngine so train/serve stay aligned.
"""

import csv
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from scripts.generate_synthetic_data import FIELDNAMES, generate_transaction
from scripts.train_xgboost_aligned import (
    _load_synthetic_csv,
    _save_synthetic_csv,
    build_feature_vectors,
    build_synthetic_history,
    generate_synthetic_data,
)

# Velocity windows used by the standalone demo generator. The training
# generator no longer uses fixed class windows — see TestTrainerGenerator.
FRAUD_5MIN = (3, 15)
FRAUD_1H = (10, 60)
LEGIT_5MIN = (0, 2)
LEGIT_1H = (0, 5)

# Position of the velocity features in the production FeatureEngine vector
FEATURE_IDX_5MIN = 3  # FEATURE_NAMES[3] = tx_count_last_5min
FEATURE_IDX_1H = 4    # FEATURE_NAMES[4] = tx_count_last_1h


class TestStandaloneGenerator:
    """scripts/generate_synthetic_data.py emits velocity columns (FD-VEL-004)."""

    def test_fieldnames_include_velocity_columns(self):
        assert "velocity_5min" in FIELDNAMES
        assert "velocity_1h" in FIELDNAMES

    def test_every_transaction_carries_class_valid_velocity(self):
        random.seed(42)
        base = datetime.now(tz=timezone.utc)
        seen = {"fraud": 0, "legit": 0}

        for i in range(300):
            tx = generate_transaction(i, base)
            assert "velocity_5min" in tx
            assert "velocity_1h" in tx
            v5, v1 = tx["velocity_5min"], tx["velocity_1h"]
            if tx["is_fraud"]:
                seen["fraud"] += 1
                assert FRAUD_5MIN[0] <= v5 <= FRAUD_5MIN[1]
                assert FRAUD_1H[0] <= v1 <= FRAUD_1H[1]
            else:
                seen["legit"] += 1
                assert LEGIT_5MIN[0] <= v5 <= LEGIT_5MIN[1]
                assert LEGIT_1H[0] <= v1 <= LEGIT_1H[1]

        # Both branches must actually execute, not pass vacuously
        assert seen["fraud"] > 0 and seen["legit"] > 0


class TestTrainerGenerator:
    """train_xgboost_aligned.generate_synthetic_data keeps velocity in the dict
    and does not make velocity a sufficient statistic for the label.

    The previous version of this test asserted that fraud velocity always
    landed in ``(3, 15)`` and legitimate velocity always in ``(0, 2)`` — a
    hard, disjoint partition. That assertion is the degeneracy, written down:
    it forbade exactly the overlap real fraud has, and because velocity
    separated the classes perfectly, ``tx_count_last_5min`` scored ROC-AUC
    1.0000 on its own. The model then had no reason to combine any signal.
    The class-conditional window assertions are replaced below by the
    property that actually matters.
    """

    def test_generated_tx_keeps_velocity_in_dict(self):
        transactions, labels = generate_synthetic_data(n_samples=500, fraud_rate=0.2)
        assert len(transactions) == 500

        for tx in transactions:
            assert "velocity_5min" in tx and "velocity_1h" in tx
            assert isinstance(tx["velocity_5min"], int)
            assert isinstance(tx["velocity_1h"], int)
            assert tx["velocity_5min"] >= 0 and tx["velocity_1h"] >= 0

    def test_velocity_distributions_overlap(self):
        """Fraud and legitimate velocity must not be separable by threshold.

        A single wire transfer is not a burst, and a Saturday sale is. Both
        directions of overlap are required: fraud with legitimate-looking
        velocity, and legitimate with fraud-looking velocity.
        """
        transactions, labels = generate_synthetic_data(n_samples=6000, fraud_rate=0.05)
        fraud_v5 = [t["velocity_5min"] for t, y in zip(transactions, labels) if y == 1]
        legit_v5 = [t["velocity_5min"] for t, y in zip(transactions, labels) if y == 0]
        assert fraud_v5 and legit_v5

        # Fraud that looks legitimate on velocity...
        assert min(fraud_v5) <= LEGIT_5MIN[1], (
            f"no fraud transaction has velocity_5min <= {LEGIT_5MIN[1]}; "
            f"lowest is {min(fraud_v5)} — a single wire is not a burst"
        )
        # ...and legitimate that looks fraudulent.
        assert max(legit_v5) > LEGIT_5MIN[1], (
            f"no legitimate transaction exceeds velocity_5min "
            f"{LEGIT_5MIN[1]}; highest is {max(legit_v5)} — shoppers burst too"
        )
        # The rate must still differ, otherwise the feature is pure noise.
        assert np.mean(fraud_v5) > np.mean(legit_v5), (
            "velocity carries no directional signal at all"
        )

    def test_user_statistics_are_populated(self):
        """user_avg_amount / user_std_amount must be positive and varying.

        They were absent from the generator and from the CSV, so
        ``amount_vs_user_avg`` and ``amount_vs_user_std`` were constant zero
        and the deployed model weighted a dead column at 19%.
        """
        transactions, _ = generate_synthetic_data(n_samples=3000, fraud_rate=0.05)
        avgs = [t["user_avg_amount"] for t in transactions]
        stds = [t["user_std_amount"] for t in transactions]
        assert min(avgs) > 0, "a user_avg_amount of 0 makes the ratio feature dead"
        assert min(stds) > 0, "a user_std_amount of 0 makes the z-score feature dead"
        assert np.std(avgs) > 0, "user_avg_amount is constant across the corpus"
        assert np.std(stds) > 0, "user_std_amount is constant across the corpus"


class TestSyntheticDataIsNotDegenerate:
    """The corpus must not hand the model a single sufficient statistic."""

    @pytest.fixture(scope="class")
    def matrix(self):
        from src.services.feature_engine import FEATURE_NAMES, FeatureEngine
        from scripts.train_xgboost_aligned import (
            FRAUD_NOISE_INTENSITY, add_realistic_noise, build_synthetic_history,
        )

        transactions, labels = generate_synthetic_data(n_samples=6000, fraud_rate=0.05)
        transactions, labels = add_realistic_noise(
            transactions, labels, fraud_noise_intensity=FRAUD_NOISE_INTENSITY
        )
        histories = [build_synthetic_history(t) for t in transactions]
        X = build_feature_vectors(transactions, histories)
        return X, labels, FEATURE_NAMES

    def test_every_feature_varies(self, matrix):
        """A constant column cannot be learned, and the artifact weights it anyway."""
        X, _, names = matrix
        dead = [n for i, n in enumerate(names) if X[:, i].std() == 0.0]
        assert not dead, f"constant features in the generated corpus: {dead}"

    def test_no_single_feature_separates_the_classes(self, matrix):
        """No feature may be a sufficient statistic for the label.

        This is the regression guard for the original defect, where four
        features each scored ROC-AUC 1.0000 and the trained model used
        whichever one the tree found first.
        """
        from sklearn.metrics import roc_auc_score

        X, y, names = matrix
        aucs = {}
        for i, name in enumerate(names):
            if X[:, i].std() == 0.0:
                continue
            score = roc_auc_score(y, X[:, i])
            aucs[name] = max(score, 1.0 - score)
        assert aucs, "no feature has variance"
        worst = max(aucs.items(), key=lambda kv: kv[1])
        assert worst[1] < 0.95, (
            f"{worst[0]} alone reaches AUC {worst[1]:.4f} — the classes are "
            f"separable by one field, which is what the model then relied on. "
            f"All single-feature AUCs: "
            f"{ {k: round(v, 4) for k, v in sorted(aucs.items())} }"
        )


class TestSyntheticCsvRoundTrip:
    """CSV save/load round-trips the velocity columns."""

    def test_save_writes_velocity_columns(self, tmp_path):
        txs = [{
            "amount": 10.0,
            "merchant_name": "Store_A",
            "merchant_category": "groceries",
            "timestamp": "2024-01-01T10:00:00",
            "velocity_5min": 4,
            "velocity_1h": 12,
        }]
        path = str(tmp_path / "synth.csv")
        _save_synthetic_csv(txs, np.array([1]), path)

        with open(path, "r", newline="") as f:
            rows = list(csv.DictReader(f))
        assert "velocity_5min" in rows[0] and "velocity_1h" in rows[0]
        assert rows[0]["velocity_5min"] == "4"
        assert rows[0]["velocity_1h"] == "12"

    def test_load_reads_velocity_columns(self, tmp_path):
        path = str(tmp_path / "with_vel.csv")
        Path(path).write_text(
            "amount,merchant_name,merchant_category,timestamp,is_fraud,"
            "user_avg_amount,user_std_amount,velocity_5min,velocity_1h\n"
            "50.0,Store_1,groceries,2024-01-01T12:00:00,0,100.0,20.0,1,4\n",
            encoding="utf-8",
        )
        txs, labels = _load_synthetic_csv(path)
        assert labels[0] == 0
        assert txs[0]["velocity_5min"] == 1
        assert txs[0]["velocity_1h"] == 4
        assert txs[0]["user_avg_amount"] == 100.0
        assert txs[0]["user_std_amount"] == 20.0

    def test_load_falls_back_to_zero_for_legacy_csv(self, tmp_path):
        # Old format: no velocity / user-stat columns at all
        path = str(tmp_path / "legacy.csv")
        Path(path).write_text(
            "amount,merchant_name,merchant_category,timestamp,is_fraud\n"
            "50.0,Store_1,groceries,2024-01-01T12:00:00,0\n",
            encoding="utf-8",
        )
        txs, _ = _load_synthetic_csv(path)
        assert txs[0]["velocity_5min"] == 0
        assert txs[0]["velocity_1h"] == 0
        assert txs[0]["user_avg_amount"] == 0.0


class TestSyntheticHistory:
    """Synthetic histories propagate CSV velocity into FeatureEngine."""

    def test_build_synthetic_history_maps_csv_values(self):
        tx = {
            "user_avg_amount": "120.5",
            "user_std_amount": "30.25",
            "velocity_5min": "7",
            "velocity_1h": "25",
        }
        hist = build_synthetic_history(tx)
        assert hist == {
            "avg_amount": 120.5,
            "std_amount": 30.25,
            "tx_count_last_5min": 7,
            "tx_count_last_1h": 25,
        }

    def test_build_synthetic_history_defaults_to_zero(self):
        hist = build_synthetic_history({})
        assert hist == {
            "avg_amount": 0.0,
            "std_amount": 0.0,
            "tx_count_last_5min": 0,
            "tx_count_last_1h": 0,
        }

    def test_velocity_propagates_into_feature_engine(self):
        txs = [
            {
                "amount": 100.0,
                "merchant_category": "groceries",
                "timestamp": "2024-01-01T10:00:00",
                "velocity_5min": 6,
                "velocity_1h": 30,
            },
            {
                "amount": 50.0,
                "merchant_category": "groceries",
                "timestamp": "2024-01-01T12:00:00",
                "velocity_5min": 0,
                "velocity_1h": 2,
            },
        ]
        histories = [build_synthetic_history(tx) for tx in txs]
        X = build_feature_vectors(txs, histories)

        assert X.shape == (2, 10)
        # The velocity values written to the CSV must reach the model features
        assert list(X[:, FEATURE_IDX_5MIN]) == [6.0, 0.0]
        assert list(X[:, FEATURE_IDX_1H]) == [30.0, 2.0]
