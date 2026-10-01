"""Tests for drift monitoring persistence.

Verifies that:
- Drift reference data persists to the database (not just in-memory singleton).
- A scoring call leaves the persisted drift reference untouched, and returns
  a result that records which ensemble layers contributed (ML4/A15).

WHAT CHANGED HERE ON 2026-10-01, AND WHY THE SECOND CLASS IS STILL HERE
---------------------------------------------------------------------
This module used to carry a `TestTrackModelRunAfterScoring` class whose two
tests proved that `ScoringService.compute_scores` called
`monitoring_service.track_model_run`, with `model_version="v1"` and
`drift_detected=False` hardcoded.

That capability was DELETED, not unwired — `MonitoringService`, this hook, and
the `monitoring_service` parameter were all removed
(`docs/plans/2026-10-01-monitoring-desenmascarar.md`, decision A). Wiring it
would have written one `ml_model_runs` row per scored transaction, into a table
documented as a record of a model *training run*, with three of its columns
constant.

So the tests that guarded the hook are gone, and these two remain. They were
rewritten rather than deleted because they guard something that is live and
still unguarded anywhere else: `DataDriftService` persistence — the one drift
service the API actually calls — has to survive a scoring call, and the score
that scoring returns has to say which layers produced it.

They are NOT a thinner restatement of the old tests. Before, they asserted a
callback fired. Now they assert a durable artefact survives and that an
observable field is populated.
"""

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from src.services.scoring_service import ScoringService


def _reference_rows() -> MagicMock:
    """A `DriftReferenceData`-shaped row as `load_reference_from_db` reads it."""
    record = MagicMock()
    record.columns = ["rule_score", "ml_score"]
    record.data = [[10.0, 20.0], [30.0, 40.0]]
    return record


class TestDriftPersistence:
    """Drift reference data should persist to the database, not just in-memory."""

    @pytest.mark.asyncio
    async def test_drift_service_loads_from_db(self):
        """DataDriftService should load reference data from DB when available."""

        from src.services.drift_service import DataDriftService

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _reference_rows()
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


class TestScoringLeavesDriftStateAlone:
    """A scoring call must not disturb the drift reference it shares a process with.

    `DataDriftService` is a module-level singleton in api/v1/monitoring.py and
    `ScoringService` is a module-level singleton in api/v1/transactions.py. They
    are different modules with different lifetimes-as-written, but they share a
    process, and the drift reference is the one artefact there that must stay
    valid across every other thing the process does. A baseline that a scoring
    call can silently replace is not a baseline.
    """

    @staticmethod
    def _scoring_service(ml_available: bool = True) -> ScoringService:
        rule_engine = MagicMock()
        rule_engine.evaluate.return_value = (35.0, ["high_amount"])

        feature_engine = MagicMock()
        feature_engine.transform.return_value = np.zeros(10)

        ml_service = MagicMock()
        ml_service.predict.return_value = 50.0
        ml_service.n_features = 10
        ml_service.is_available = ml_available

        ensemble = MagicMock()
        ensemble.get_threshold.return_value = 70.0
        ensemble.combine.return_value = 40.0
        ensemble.classify.return_value = "review"

        return ScoringService(
            rule_engine=rule_engine,
            feature_engine=feature_engine,
            ml_service=ml_service,
            ensemble_scorer=ensemble,
        )

    @pytest.mark.asyncio
    async def test_a_persisted_reference_survives_a_scoring_call(self):
        """Load a reference from the database, score a transaction, and assert
        the reference is byte-for-byte what it was.

        The negative space is the point. Scoring does not touch the drift
        service at all — there is no collaborator to touch it with, since the
        `monitoring_service` parameter was removed — so this can only pass by
        accident of ordering today. It is here to fail loudly if someone
        reintroduces a coupling between the two.
        """
        from src.services.drift_service import DataDriftService

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _reference_rows()
        mock_db.execute = AsyncMock(return_value=mock_result)

        drift = DataDriftService(db=mock_db)
        assert await drift.load_reference_from_db() is True
        assert drift.is_initialized is True
        reference_before = drift.reference_data
        rows_before = len(reference_before)
        # The load is the only DB read this test is allowed; scoring must not
        # add another.
        reads_before = mock_db.execute.await_count

        result = await self._scoring_service().compute_scores(
            tx_data={"amount": 5000, "merchant_category": "retail"},
            context={"recent_transactions": 2},
            user_history={},
        )

        assert result.ensemble_score == 40.0
        assert drift.is_initialized is True, "scoring cleared the drift baseline"
        assert drift.reference_data is not None
        assert len(drift.reference_data) == rows_before
        assert drift.reference_data.equals(reference_before)
        assert mock_db.execute.await_count == reads_before, (
            "scoring reached the database; ScoringService takes no session"
        )

    @pytest.mark.asyncio
    async def test_scoring_completes_with_no_database_and_records_its_layers(self):
        """Nothing optional blocks a score, and the score says what it was made of.

        This is the honest residue of the deleted `test_track_model_run_does_not_
        block_scoring`, which asserted that a *failing monitoring callback* could
        not stop a score from being returned. The callback is gone, so the
        property that still matters is the one underneath it: with no session and
        no collaborator there is nothing left to fail, and scoring must return a
        complete result — including `layers_used`, the field that records a layer
        which produced nothing (A15).

        `layers_used` is now on the wire (`ScoreResponse`), so this is the guard
        on the value a client actually reads: an absent ML layer must show up as
        a missing name in that tuple, never as a nulled score.
        """
        degraded = await self._scoring_service(ml_available=False).compute_scores(
            tx_data={"amount": 5000, "merchant_category": "retail"},
            context={"recent_transactions": 2},
            user_history={},
        )

        assert degraded.ensemble_score == 40.0
        assert degraded.classification == "review"
        assert "ml" not in degraded.layers_used, (
            "a layer that never ran must not be listed as one that contributed"
        )
        assert set(degraded.layers_used) == {"rule", "context"}

        complete = await self._scoring_service().compute_scores(
            tx_data={"amount": 5000, "merchant_category": "retail"},
            context={"recent_transactions": 2},
            user_history={},
        )

        assert set(complete.layers_used) == {"rule", "ml", "context"}
        assert complete.layers_used != degraded.layers_used, (
            "a degraded score and a complete one must be distinguishable on the "
            "wire; that is the whole reason layers_used exists"
        )