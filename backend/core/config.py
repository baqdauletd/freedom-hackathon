from __future__ import annotations

import os
from functools import lru_cache
from typing import List


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class Settings:
    app_name: str = os.getenv("APP_NAME", "FIRE Backend")
    app_env: str = os.getenv("APP_ENV", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/fire",
    )
    auto_create_schema: bool = _get_bool("AUTO_CREATE_SCHEMA", False)

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_timeout_seconds: float = _get_float("OPENAI_TIMEOUT_SECONDS", 6.0)

    # FIRE hackathon mode should enforce mandatory geo routing rules.
    fire_compliance_mode: bool = _get_bool("FIRE_COMPLIANCE_MODE", True)
    enable_geocode: bool = _get_bool("ENABLE_GEOCODE", True)
    geocode_timeout_seconds: float = _get_float("GEOCODE_TIMEOUT_SECONDS", 3.0)
    geocode_rate_limit_seconds: float = _get_float("GEOCODE_RATE_LIMIT_SECONDS", 1.0)
    geocode_fail_streak_limit: int = _get_int("GEOCODE_FAIL_STREAK_LIMIT", 3)

    per_ticket_budget_ms: int = _get_int("PER_TICKET_BUDGET_MS", 10_000)

    tickets_csv_path: str = os.getenv("TICKETS_CSV", "tickets.csv")
    managers_csv_path: str = os.getenv("MANAGERS_CSV", "managers.csv")
    business_units_csv_path: str = os.getenv("BUSINESS_UNITS_CSV", "business_units.csv")

    cors_origins: List[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://localhost:3000",
        ).split(",")
        if origin.strip()
    ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
