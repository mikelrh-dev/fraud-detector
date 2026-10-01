"""Service layer exports.

Two services used to live here for drift: ``monitoring.MonitoringService``
and ``drift_service.DataDriftService``. ``MonitoringService`` and its tests
were deleted on 2026-10-01 (plan
``docs/plans/2026-10-01-monitoring-desenmascarar.md``, decision A), so
``DataDriftService`` is now the only drift service in the project — one PSI
implementation, not two, and the one the API actually calls.

What was lost, and why nothing broke: the deleted class also owned
``compute_metrics`` and ``check_retraining_trigger``, both of which need real
labels the project does not have, and an unwired ``monitoring_service``
parameter on ``ScoringService.compute_scores``. Wiring that hook would have
written one ``ml_model_runs`` row per scored transaction, into a table
documented as a record of a model **training run**, with ``status=READY``,
``drift_detected=False`` and ``model_version="v1"`` all constant. The
parameter was the defect, not the missing wiring.

If you are looking for a second PSI implementation and cannot find one: that
is the point. One drift service, one calculation.
"""
