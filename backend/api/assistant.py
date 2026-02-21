from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.session import get_db
from backend.schemas.ai import AssistantQueryRequest, AssistantQueryResponse
from backend.services.analytics import AnalyticsService

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/query", response_model=AssistantQueryResponse)
def assistant_query(payload: AssistantQueryRequest, db: Session = Depends(get_db)) -> dict:
    query = (payload.query or payload.prompt or "").strip()
    if not query:
        query = "Show ticket distribution by city"
    service = AnalyticsService(get_settings())
    return service.assistant_query(db, query)
