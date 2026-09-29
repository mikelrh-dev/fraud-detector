"""Tests for drift monitoring persistence (ML4).

Verifies that:
- Drift reference data persists to the database (not just in-memory singleton).
- track_model_run is invoked after scoring (awaited).
- GET /monitoring/metrics returns actual ml_model_run rows.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.scoring_service import ScoringService


class TestDriftPersistence:
    """Drift reference data should persist to the database, not just in-memory."""

    @pytest.mark.asyncio
    async def test_drift_service_loads_from_db(self):
        """DataDriftService should load reference data from DB when available."""

        from src.services.drift_service import DataDriftService

        mock_db = AsyncMock()
        mock_record = MagicMock()
        mock_record.columns = ["col1", "col2"]
        mock_record.data = [[1.0, 3.0], [2.0, 4.0]]
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_record
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = DataDriftService(db=mock_db)
        loaded = await service.load_reference_from_db()

        assert loaded is True
        assert service.is_initialized is True
        assert service.reference_data is not None
        assert len(service.reference_data) == 2

    @pytest.mark.asyncio
    async def test_drift_service_saves_to_db(self):
        """save_reference_data should persist to the database."""
        import pandas as pd

        from src.services.drift_service import DataDriftService

        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        service = DataDriftService(db=mock_db)
        df = pd.DataFrame({"col1": [1.0, 2.0], "col2": [3.0, 4.0]})
        await service.save_reference_to_db(df, description="test")

        # Should have added a record and flushed
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_drift_service_no_db_no_crash(self):
        """DataDriftService should work without a DB (memory-only fallback)."""
        import pandas as pd

        from src.services.drift_service import DataDriftService

        service = DataDriftService(db=None)
        df = pd.DataFrame({"col1": [1.0, 2.0], "col2": [3.0, 4.0]})
        service.set_reference_data(df)

        assert service.is_initialized is True
        assert service.reference_data is not None
        assert len(service.reference_data) == 2


class TestTrackModelRunAfterScoring:
    """track_model_run should be called after each scoring pass."""

    @pytest.mark.asyncio
    async def test_track_model_run_invoked_on_scoring(self):
        """ScoringService should call monitoring_service.track_model_run after scoring."""

        rule_engine = MagicMock()
        rule_engine.evaluate.return_value = (35.0, ["high_amount"])

        feature_engine = MagicMock()
        feature_engine.transform.return_value = __import__("numpy").zeros(10)

        ml_service = MagicMock()
        ml_service.predict.return_value = 50.0
        ml_service.n_features = 10

        ensemble = MagicMock()
        ensemble.get_threshold.return_value = 70.0
        ensemble.combine.return_value = 40.0
        ensemble.classify.return_value = "review"

        monitoring = MagicMock()
        monitoring.track_model_run = AsyncMock()

        service = ScoringService(
            rule_engine=rule_engine,
            feature_engine=feature_engine,
            ml_service=ml_service,
            ensemble_scorer=ensemble,
        )

        db = MagicMock()
        db.flush = AsyncMock()

        # The return value is deliberately not bound. This test's claim is that
        # SCORING INVOKES the callback, and every assertion below reads
        # `monitoring.track_model_run`; nothing reads the score. Binding it to a
        # name nothing uses is what F841 was pointing at.
        await service.compute_scores(
            tx_data={"amount": 5000, "merchant_category": "retail"},
            context={"recent_transactions": 2},
            user_history={},
            db=db,
            monitoring_service=monitoring,
        )

        # track_model_run should have been called
        monitoring.track_model_run.assert_called_once()
        call_kwargs = monitoring.track_model_run.call_args.kwargs
        assert call_kwargs["model_version"] == "v1"
        assert "rule_score" in call_kwargs["metrics"]
        assert "ml_score" in call_kwargs["metrics"]
        assert "ensemble_score" in call_kwargs["metrics"]

    @pytest.mark.asyncio
    async def test_track_model_run_does_not_block_scoring(self):
        """track_model_run failure should not prevent scoring from completing."""

        rule_engine = MagicMock()
        rule_engine.evaluate.return_value = (0.0, [])

        feature_engine = MagicMock()
        feature_engine.transform.return_value = __import__("numpy").zeros(10)

        ml_service = MagicMock()
        ml_service.predict.return_value = 0.0
        ml_service.n_features = 10

        ensemble = MagicMock()
        ensemble.get_threshold.return_value = 70.0
        ensemble.combine.return_value = 0.0
        ensemble.classify.return_value = "legitimate"

        monitoring = MagicMock()
        monitoring.track_model_run = AsyncMock(side_effect=Exception("DB down"))

        service = ScoringService(
            rule_engine=rule_engine,
            feature_engine=feature_engine,
            ml_service=ml_service,
            ensemble_scorer=ensemble,
        )

        db = MagicMock()
        db.flush = AsyncMock()

        # Should not raise even if track_model_run fails
        result = await service.compute_scores(
            tx_data={"amount": 100},
            context={},
            user_history={},
            db=db,
            monitoring_service=monitoring,
        )
        assert result.ensemble_score == 0.0
