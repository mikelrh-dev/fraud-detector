"""Report endpoints — retrieve LLM-generated fraud analysis reports."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db
from src.models.llm_report import LLMReport, LLMReportStatus
from src.schemas.report import ReportResponse

router = APIRouter(prefix="/transactions", tags=["reports"])


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
        status=report.status.value,
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
