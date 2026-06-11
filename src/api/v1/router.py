"""API v1 router aggregation — wires all endpoint modules."""

from fastapi import APIRouter

from src.api.v1.alerts import router as alerts_router
from src.api.v1.audit import router as audit_router
from src.api.v1.auth import router as auth_router
from src.api.v1.monitoring import router as monitoring_router
from src.api.v1.reports import router as reports_router
from src.api.v1.transactions import router as transactions_router

router = APIRouter(prefix="/api/v1")

# Active endpoint modules
router.include_router(auth_router)
router.include_router(transactions_router)
router.include_router(alerts_router)
router.include_router(reports_router)
router.include_router(monitoring_router)
router.include_router(audit_router)


@router.get("/health", tags=["health"])
async def v1_health() -> dict[str, str]:
    """V1 health check."""
    return {"status": "ok", "version": "v1"}
