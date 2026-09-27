"""Report endpoints — retrieve LLM-generated fraud analysis reports."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.rate_limit import check_rate_limit
from src.core.dependencies import get_current_user, get_db
from src.models.llm_report import LLMReport, LLMReportStatus
from src.models.transaction import Transaction
from src.schemas.report import ReportResponse

router = APIRouter(
    prefix="/transactions",
    tags=["reports"],
    # A4: this route had no limiter. The /api/v1/transactions prefix in
    # RATE_LIMITS already matches this path, so adding the dependency is enough.
    dependencies=[Depends(check_rate_limit)],
)


@router.get("/{transaction_id}/report", response_model=ReportResponse)
async def get_transaction_report(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ReportResponse:
    """Retrieve the LLM report for a transaction.

    Returns:
        - 200 with report details if the report exists (completed or failed).
        - 202 if the report is still pending (in queue).
        - 404 if no report is found for the transaction.
    """
    # --- Ownership check (R1-003 / F1): only the transaction owner or
    # an admin may view the report. Transaction not found → 404;
    # found but owned by another user → 403. ---
    txn_result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    txn = txn_result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No report found for this transaction",
        )

    is_admin = current_user.get("role") == "admin"
    user_id = str(txn.user_id)
    if not is_admin and user_id != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    query = select(LLMReport).where(
        LLMReport.transaction_id == transaction_id
    )
    result = await db.execute(query)
    report = result.scalar_one_or_none()

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No report found for this transaction",
        )

    response = ReportResponse(
        transaction_id=report.transaction_id,
        report_text=report.report_text,
        model_name=report.model_name,
        status=report.status,
        generation_time_ms=report.generation_time_ms,
        created_at=report.created_at,
    )

    if report.status == LLMReportStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail="Report generation in progress",
        )

    if report.status == LLMReportStatus.FAILED:
        response.error_detail = (
            "Report generation failed. "
            "The LLM service may be unavailable."
        )

    return response
