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

from scripts.generate_synthetic_data import FIELDNAMES, generate_transaction
from scripts.train_xgboost_aligned import (
    _load_synthetic_csv,
    _save_synthetic_csv,
    build_feature_vectors,
    build_synthetic_history,
    generate_synthetic_data,
)

# Velocity windows shared by both generators (mirror the module constants)
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
    """train_xgboost_aligned.generate_synthetic_data keeps velocity in the dict."""

    def test_generated_tx_keeps_velocity_in_dict(self):
        transactions, labels = generate_synthetic_data(n_samples=500, fraud_rate=0.2)
        assert len(transactions) == 500

        seen = {"fraud": 0, "legit": 0}
        for tx, label in zip(transactions, labels):
            assert "velocity_5min" in tx and "velocity_1h" in tx
            v5, v1 = tx["velocity_5min"], tx["velocity_1h"]
            if label == 1:
                seen["fraud"] += 1
                assert FRAUD_5MIN[0] <= v5 <= FRAUD_5MIN[1]
                assert FRAUD_1H[0] <= v1 <= FRAUD_1H[1]
            else:
                seen["legit"] += 1
                assert LEGIT_5MIN[0] <= v5 <= LEGIT_5MIN[1]
                assert LEGIT_1H[0] <= v1 <= LEGIT_1H[1]

        assert seen["fraud"] > 0 and seen["legit"] > 0


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
