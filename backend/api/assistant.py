from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
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
        raise HTTPException(status_code=400, detail="Query is required")
    service = AnalyticsService(get_settings())
    return service.assistant_query(
        db,
        query,
        scope={
            "run_id": payload.run_id,
            "office": payload.office,
            "date_from": payload.date_from,
            "date_to": payload.date_to,
        },
    )
