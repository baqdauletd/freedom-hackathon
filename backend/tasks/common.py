from __future__ import annotations

from typing import Any

from backend.schemas.ai import AIResult
from backend.services.routing import OfficeDecision


def ticket_record_to_row(ticket: Any) -> dict[str, str]:
    return {
        "ID": ticket.external_id or str(ticket.id),
        "Пол клиента": ticket.gender or "",
        "Дата рождения": ticket.birth_date or "",
        "Сегмент клиента": ticket.segment or "Mass",
        "Описание": ticket.description or "",
        "Вложения": ticket.attachments or "",
        "Страна": ticket.country or "",
        "Регион": ticket.region or "",
        "Город": ticket.city or "",
        "Улица": ticket.street or "",
        "Дом": ticket.house or "",
    }


def office_decision_to_payload(decision: OfficeDecision) -> dict[str, Any]:
    return {
        "office_name": decision.office_name,
        "ticket_coords": list(decision.ticket_coords) if decision.ticket_coords else None,
        "office_coords": list(decision.office_coords) if decision.office_coords else None,
        "strategy": decision.strategy,
        "used_fallback": decision.used_fallback,
        "fallback_reason": decision.fallback_reason,
        "nearest_distance_km": decision.nearest_distance_km,
    }


def office_decision_from_payload(payload: dict[str, Any]) -> OfficeDecision:
    ticket_coords = payload.get("ticket_coords")
    office_coords = payload.get("office_coords")
    return OfficeDecision(
        office_name=str(payload.get("office_name") or ""),
        ticket_coords=tuple(ticket_coords) if isinstance(ticket_coords, list) and len(ticket_coords) == 2 else None,
        office_coords=tuple(office_coords) if isinstance(office_coords, list) and len(office_coords) == 2 else None,
        strategy=str(payload.get("strategy") or "unknown"),
        used_fallback=bool(payload.get("used_fallback")),
        fallback_reason=str(payload.get("fallback_reason")) if payload.get("fallback_reason") else None,
        nearest_distance_km=(
            float(payload["nearest_distance_km"]) if payload.get("nearest_distance_km") is not None else None
        ),
    )


def ai_result_to_payload(result: AIResult) -> dict[str, Any]:
    return result.model_dump()


def ai_result_from_payload(payload: dict[str, Any]) -> AIResult:
    return AIResult.model_validate(payload)

