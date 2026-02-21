from __future__ import annotations

from fastapi import APIRouter

from backend.core.runtime import APP_INSTANCE_ID, APP_STARTED_AT

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "app_instance_id": APP_INSTANCE_ID,
        "started_at": APP_STARTED_AT.isoformat(),
    }
