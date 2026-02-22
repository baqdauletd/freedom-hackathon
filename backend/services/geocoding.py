from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from backend.core.config import Settings

LOGGER = logging.getLogger("fire.geo")

KZ_COUNTRY_TOKENS = {"казахстан", "kazakhstan", "kz", "қазақстан"}


@dataclass
class GeocodingService:
    settings: Settings
    cache: dict[str, Optional[tuple[float, float]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.client = httpx.Client(
            timeout=self.settings.geocode_timeout_seconds,
            headers={"User-Agent": "FIRE-Hackathon/1.0"},
        )
        self.last_call = 0.0
        self.failure_streak = 0

    def is_foreign(self, country: str | None) -> bool:
        value = (country or "").strip().lower()
        return bool(value) and value not in KZ_COUNTRY_TOKENS

    def has_enough_address(self, row: dict[str, str]) -> bool:
        if (row.get("Адрес") or "").strip():
            return True
        return all((row.get(field) or "").strip() for field in ["Страна", "Город", "Улица", "Дом"])

    def build_address(self, row: dict[str, str]) -> str:
        address = (row.get("Адрес") or "").strip()
        if address:
            return address
        parts = [
            (row.get("Страна") or "").strip(),
            (row.get("Регион") or "").strip(),
            (row.get("Город") or "").strip(),
            (row.get("Улица") or "").strip(),
            (row.get("Дом") or "").strip(),
        ]
        return ", ".join(part for part in parts if part)

    def geocode(self, address: str, *, raise_on_error: bool = False) -> Optional[tuple[float, float]]:
        address = address.strip()
        if not address:
            return None

        if address in self.cache:
            return self.cache[address]

        if self.failure_streak >= self.settings.geocode_fail_streak_limit:
            LOGGER.warning("geocode_temporarily_disabled_due_to_failures")
            return None

        elapsed = time.monotonic() - self.last_call
        if elapsed < self.settings.geocode_rate_limit_seconds:
            time.sleep(self.settings.geocode_rate_limit_seconds - elapsed)

        started = time.perf_counter()
        try:
            response = self.client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": address, "format": "json", "limit": 1},
            )
            response.raise_for_status()
            payload = response.json()
            if payload:
                coords = (float(payload[0]["lat"]), float(payload[0]["lon"]))
                self.cache[address] = coords
                self.failure_streak = 0
                LOGGER.info("geocode_resolved", extra={"duration_ms": round((time.perf_counter() - started) * 1000, 2)})
            else:
                self.cache[address] = None
                LOGGER.info("geocode_not_found", extra={"duration_ms": round((time.perf_counter() - started) * 1000, 2)})
        except Exception as exc:  # pragma: no cover - network behavior
            LOGGER.warning(
                "geocode_failed",
                extra={"error": str(exc), "duration_ms": round((time.perf_counter() - started) * 1000, 2)},
            )
            if raise_on_error:
                raise
            self.cache[address] = None
            self.failure_streak += 1

        self.last_call = time.monotonic()
        return self.cache[address]
