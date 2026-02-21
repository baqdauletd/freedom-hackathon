from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.session import get_db
from backend.schemas.analytics import AnalyticsSummaryResponse
from backend.services.analytics import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def analytics_summary(
    run_id: str | None = None,
    office: str | None = None,
    office_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    service = AnalyticsService(get_settings())
    return service.get_summary(
        db,
        run_id=run_id,
        office=office,
        office_id=office_id,
        date_from=date_from,
        date_to=date_to,
    )
