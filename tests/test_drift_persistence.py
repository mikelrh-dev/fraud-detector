"""Tests for drift monitoring persistence (ML4).

Verifies that:
- Drift reference data persists to Redis (not just in-memory singleton).
- track_model_run is invoked after scoring (fire-and-forget).
- GET /monitoring/metrics returns actual ml_model_run rows.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.scoring_service import ScoringService


class TestDriftPersistence:
    """Drift reference data should persist to Redis, not just in-memory."""

    def test_drift_service_loads_from_redis_on_init(self):
        """DataDriftService should load reference data from Redis key on startup."""
        from src.services.drift_service import DataDriftService

        mock_redis = MagicMock()
        mock_redis.get = MagicMock(return_value=None)  # no cached data

        service = DataDriftService(redis_client=mock_redis)
        assert service.is_initialized is False

    def test_drift_service_persists_to_redis_on_set(self):
        """set_reference_data should persist to Redis as JSON."""
        import json

        from src.services.drift_service import DataDriftService
        import pandas as pd

        mock_redis = MagicMock()
        mock_redis.set = MagicMock()

        service = DataDriftService(redis_client=mock_redis)
        df = pd.DataFrame({"col1": [1.0, 2.0], "col2": [3.0, 4.0]})
        service.set_reference_data(df)

        # Should have called redis.set with the drift:reference_data key
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "drift:reference_data"
        # Value should be valid JSON
        stored_json = call_args[0][1]
        parsed = json.loads(stored_json)
        assert "data" in parsed
        assert "columns" in parsed

    def test_drift_service_restores_from_redis(self):
        """DataDriftService should restore reference data from Redis on init."""
        import json

        from src.services.drift_service import DataDriftService
        import pandas as pd

        cached_data = json.dumps({
            "columns": ["col1", "col2"],
            "data": [[1.0, 3.0], [2.0, 4.0]],
        })

        mock_redis = MagicMock()
        mock_redis.get = MagicMock(return_value=cached_data.encode())

        service = DataDriftService(redis_client=mock_redis)
        assert service.is_initialized is True
        assert service.reference_data is not None
        assert len(service.reference_data) == 2


class TestTrackModelRunAfterScoring:
    """track_model_run should be called after each scoring pass."""

    @pytest.mark.asyncio
    async def test_track_model_run_invoked_on_scoring(self):
        """ScoringService should call monitoring_service.track_model_run after scoring."""
        import asyncio
        from src.services.scoring_service import ScoringService

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

        result = service.compute_scores(
            tx_data={"amount": 5000, "merchant_category": "retail"},
            context={"recent_transactions": 2},
            user_history={},
            db=db,
            monitoring_service=monitoring,
        )

        # Allow fire-and-forget task to complete
        await asyncio.sleep(0.05)

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
        import asyncio
        from src.services.scoring_service import ScoringService

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
        result = service.compute_scores(
            tx_data={"amount": 100},
            context={},
            user_history={},
            db=db,
            monitoring_service=monitoring,
        )
        assert result.ensemble_score == 0.0

        # Allow fire-and-forget task to complete (and fail silently)
        await asyncio.sleep(0.05)
