from __future__ import annotations

import math
from dataclasses import dataclass

from backend.services.geocoding import GeocodingService


@dataclass
class OfficeDecision:
    office_name: str
    ticket_coords: tuple[float, float] | None
    office_coords: tuple[float, float] | None
    strategy: str = "unknown"
    used_fallback: bool = False
    fallback_reason: str | None = None
    nearest_distance_km: float | None = None


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(x), math.sqrt(1 - x))


def split_astana_almaty(ticket_index: int) -> str:
    return "Астана" if ticket_index % 2 == 0 else "Алматы"


def choose_office(
    ticket: dict[str, str],
    offices: list[dict],
    geocoder: GeocodingService,
    ticket_index: int,
    compliance_mode: bool,
    enable_geocode: bool,
    geocode_raise_on_error: bool = False,
) -> OfficeDecision:
    country = (ticket.get("Страна") or "").strip()
    if geocoder.is_foreign(country) or not geocoder.has_enough_address(ticket):
        office_name = split_astana_almaty(ticket_index)
        office = next((o for o in offices if o["office"] == office_name), None)
        office_coords = (office["latitude"], office["longitude"]) if office and office["latitude"] and office["longitude"] else None
        reason = "foreign_country" if geocoder.is_foreign(country) else "missing_address"
        return OfficeDecision(
            office_name=office_name,
            ticket_coords=None,
            office_coords=office_coords,
            strategy="fallback_split",
            used_fallback=True,
            fallback_reason=reason,
        )

    if not compliance_mode and not enable_geocode:
        city = (ticket.get("Город") or "").strip()
        office = next((o for o in offices if o["office"] == city), None)
        if office:
            office_coords = (office["latitude"], office["longitude"]) if office["latitude"] and office["longitude"] else None
            return OfficeDecision(
                office_name=city,
                ticket_coords=None,
                office_coords=office_coords,
                strategy="city_match",
            )

    ticket_address = geocoder.build_address(ticket)
    ticket_coords = geocoder.geocode(ticket_address, raise_on_error=geocode_raise_on_error)
    if not ticket_coords:
        office_name = split_astana_almaty(ticket_index)
        office = next((o for o in offices if o["office"] == office_name), None)
        office_coords = (office["latitude"], office["longitude"]) if office and office["latitude"] and office["longitude"] else None
        return OfficeDecision(
            office_name=office_name,
            ticket_coords=None,
            office_coords=office_coords,
            strategy="fallback_split",
            used_fallback=True,
            fallback_reason="geocode_unavailable",
        )

    nearest_office: dict | None = None
    nearest_distance: float | None = None
    for office in offices:
        if office["latitude"] is None or office["longitude"] is None:
            continue
        distance = haversine_km(ticket_coords, (office["latitude"], office["longitude"]))
        if nearest_distance is None or distance < nearest_distance:
            nearest_office = office
            nearest_distance = distance

    if not nearest_office:
        office_name = split_astana_almaty(ticket_index)
        office = next((o for o in offices if o["office"] == office_name), None)
        office_coords = (office["latitude"], office["longitude"]) if office and office["latitude"] and office["longitude"] else None
        return OfficeDecision(
            office_name=office_name,
            ticket_coords=ticket_coords,
            office_coords=office_coords,
            strategy="fallback_split",
            used_fallback=True,
            fallback_reason="no_office_coordinates",
        )

    return OfficeDecision(
        office_name=nearest_office["office"],
        ticket_coords=ticket_coords,
        office_coords=(nearest_office["latitude"], nearest_office["longitude"]),
        strategy="nearest_geo",
        nearest_distance_km=nearest_distance,
    )


def normalize_position(position: str) -> str:
    return position.replace(".", "").strip().lower()


def filter_eligible_managers(
    segment: str,
    ticket_type: str,
    language: str,
    managers: list[dict],
) -> list[dict]:
    need_vip = segment in {"VIP", "Priority"}

    result: list[dict] = []
    for manager in managers:
        skills = {str(skill).strip().upper() for skill in (manager.get("skills") or []) if str(skill).strip()}
        if need_vip and "VIP" not in skills:
            continue

        position_norm = normalize_position(manager["position"])
        if ticket_type == "Смена данных" and position_norm not in {
            "глав спец",
            "главный спец",
            "главный специалист",
            "главныйспециалист",
        }:
            continue

        required_language = language.upper() if isinstance(language, str) else ""
        if required_language in {"KZ", "ENG"} and required_language not in skills:
            continue

        result.append(manager)

    return result


def pick_two_lowest_load(managers: list[dict]) -> list[dict]:
    ordered = sorted(managers, key=lambda item: (item["current_load"], item["full_name"]))
    return ordered[:2]
