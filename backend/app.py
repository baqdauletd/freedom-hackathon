from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.analytics import router as analytics_router
from backend.api.assistant import router as assistant_router
from backend.api.health import router as health_router
from backend.api.route import router as route_router
from backend.core.config import get_settings
from backend.core.logging import RequestContextMiddleware, configure_logging
from backend.db.session import init_db

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(route_router)
app.include_router(analytics_router)
app.include_router(assistant_router)


@app.on_event("startup")
def startup() -> None:
    if settings.auto_create_schema:
        init_db()
