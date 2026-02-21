from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import AIAnalysis, Assignment, BusinessUnit, Manager, RRState, Ticket
from backend.schemas.ai import AIResult
from backend.services.geocoding import GeocodingService
from backend.services.ingestion import split_skills
from backend.services.routing import OfficeDecision, pick_two_lowest_load


def upsert_business_units(db: Session, rows: list[dict[str, str]], geocoder: GeocodingService) -> list[BusinessUnit]:
    offices: list[BusinessUnit] = []
    for row in rows:
        office_name = row["Офис"]
        existing = db.execute(select(BusinessUnit).where(BusinessUnit.office == office_name)).scalar_one_or_none()

        lat = None
        lon = None
        if row.get("Широта") and row.get("Долгота"):
            try:
                lat = float(row["Широта"])
                lon = float(row["Долгота"])
            except ValueError:
                lat = None
                lon = None

        if lat is None or lon is None:
            coords = geocoder.geocode((row.get("Адрес") or "").strip())
            if coords:
                lat, lon = coords

        if existing:
            existing.address = row.get("Адрес") or existing.address
            existing.latitude = lat
            existing.longitude = lon
            office = existing
        else:
            office = BusinessUnit(
                office=office_name,
                address=row.get("Адрес") or "",
                latitude=lat,
                longitude=lon,
            )
            db.add(office)
            db.flush()

        offices.append(office)

    return offices


def upsert_managers(db: Session, rows: list[dict[str, str]], offices_by_name: dict[str, BusinessUnit]) -> list[Manager]:
    managers: list[Manager] = []
    for row in rows:
        office = offices_by_name.get(row.get("Офис") or "")
        if office is None:
            continue

        existing = db.execute(
            select(Manager).where(Manager.office_id == office.id, Manager.full_name == row["ФИО"])
        ).scalar_one_or_none()

        try:
            current_load = int(row.get("Количество обращений в работе") or "0")
        except ValueError:
            current_load = 0

        if existing:
            existing.position = row.get("Должность") or existing.position
            existing.skills = split_skills(row.get("Навыки") or "")
            existing.current_load = max(0, current_load)
            manager = existing
        else:
            manager = Manager(
                full_name=row["ФИО"],
                position=row.get("Должность") or "",
                skills=split_skills(row.get("Навыки") or ""),
                current_load=max(0, current_load),
                office_id=office.id,
            )
            db.add(manager)
            db.flush()

        managers.append(manager)

    return managers


def _pair_hash(manager_ids: list[int]) -> str:
    ordered = ":".join(str(identifier) for identifier in sorted(manager_ids))
    return hashlib.sha256(ordered.encode("utf-8")).hexdigest()


def create_ticket_record(db: Session, ticket: dict[str, str], run_id: str | None = None) -> Ticket:
    normalized_address = ", ".join(
        part
        for part in [
            ticket.get("Страна", "").strip(),
            ticket.get("Регион", "").strip(),
            ticket.get("Город", "").strip(),
            ticket.get("Улица", "").strip(),
            ticket.get("Дом", "").strip(),
        ]
        if part
    )

    record = Ticket(
        run_id=run_id,
        external_id=ticket.get("ID") or "",
        gender=ticket.get("Пол клиента") or None,
        birth_date=ticket.get("Дата рождения") or None,
        segment=ticket.get("Сегмент клиента") or "Mass",
        description=ticket.get("Описание") or "",
        attachments=ticket.get("Вложения") or None,
        country=ticket.get("Страна") or None,
        region=ticket.get("Регион") or None,
        city=ticket.get("Город") or None,
        street=ticket.get("Улица") or None,
        house=ticket.get("Дом") or None,
        normalized_address=normalized_address or None,
    )
    db.add(record)
    db.flush()
    return record


def assign_ticket(
    db: Session,
    ticket_record: Ticket,
    ai_result: AIResult,
    office_decision: OfficeDecision,
    ticket_index: int,
    processing_ms: int,
) -> dict:
    office = db.execute(
        select(BusinessUnit).where(BusinessUnit.office == office_decision.office_name).with_for_update()
    ).scalar_one_or_none()
    if office is None:
        office = BusinessUnit(office=office_decision.office_name, address="", latitude=None, longitude=None)
        db.add(office)
        db.flush()

    manager_rows = db.execute(select(Manager).where(Manager.office_id == office.id).with_for_update()).scalars().all()
    managers_payload = [
        {
            "id": manager.id,
            "full_name": manager.full_name,
            "position": manager.position,
            "skills": manager.skills or [],
            "current_load": manager.current_load,
        }
        for manager in manager_rows
    ]

    need_vip = ticket_record.segment in {"VIP", "Priority"}
    requires_glav_spec = ai_result.ticket_type == "Смена данных"
    required_language = ai_result.language if ai_result.language in {"KZ", "ENG"} else None

    glav_positions = {
        "глав спец",
        "главный спец",
        "главный специалист",
        "главныйспециалист",
    }

    eligibility_details: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for manager in managers_payload:
        position_norm = manager["position"].replace(".", "").strip().lower()
        vip_ok = (not need_vip) or ("VIP" in manager["skills"])
        position_ok = (not requires_glav_spec) or (position_norm in glav_positions)
        language_ok = (required_language is None) or (required_language in manager["skills"])
        is_eligible = vip_ok and position_ok and language_ok

        checks = {
            "vip": vip_ok,
            "position": position_ok,
            "language": language_ok,
        }
        detail_row = {
            "manager_id": manager["id"],
            "manager_name": manager["full_name"],
            "position": manager["position"],
            "skills": manager["skills"],
            "current_load": manager["current_load"],
            "checks": checks,
            "eligible": is_eligible,
        }
        eligibility_details.append(detail_row)

        if is_eligible:
            eligible.append(manager)

    two = pick_two_lowest_load(eligible)

    selected_manager_id: int | None = None
    selected_manager_name: str | None = None
    rr_turn = 0
    pair_hash: str | None = None

    if len(two) == 1:
        selected_manager_id = two[0]["id"]
        selected_manager_name = two[0]["full_name"]
    elif len(two) == 2:
        manager_ids = [two[0]["id"], two[1]["id"]]
        pair_hash = _pair_hash(manager_ids)

        state = db.execute(
            select(RRState)
            .where(RRState.office_id == office.id, RRState.eligible_pair_hash == pair_hash)
            .with_for_update()
        ).scalar_one_or_none()

        if state is None:
            state = RRState(office_id=office.id, eligible_pair_hash=pair_hash, next_turn=1)
            db.add(state)
            rr_turn = 0
        else:
            rr_turn = state.next_turn % 2
            state.next_turn = (state.next_turn + 1) % 2

        selected_manager_id = two[rr_turn]["id"]
        selected_manager_name = two[rr_turn]["full_name"]

    if selected_manager_id is not None:
        selected_manager = next((m for m in manager_rows if m.id == selected_manager_id), None)
        if selected_manager:
            selected_manager.current_load += 1

    decision_trace = {
        "geo": {
            "strategy": office_decision.strategy,
            "chosen_office": office_decision.office_name,
            "ticket_coords": list(office_decision.ticket_coords) if office_decision.ticket_coords else None,
            "office_coords": list(office_decision.office_coords) if office_decision.office_coords else None,
            "nearest_distance_km": office_decision.nearest_distance_km,
            "used_fallback": office_decision.used_fallback,
            "fallback_reason": office_decision.fallback_reason,
        },
        "rules": {
            "requires_vip": need_vip,
            "requires_glav_spec": requires_glav_spec,
            "required_language": required_language,
        },
        "eligibility": eligibility_details,
        "selected_top_two": [
            {
                "manager_id": manager["id"],
                "manager_name": manager["full_name"],
                "current_load": manager["current_load"],
            }
            for manager in two
        ],
        "round_robin": {
            "pair_hash": pair_hash,
            "turn_used": rr_turn,
            "assigned_manager_id": selected_manager_id,
            "assigned_manager_name": selected_manager_name,
        },
    }

    analysis = AIAnalysis(
        ticket_id=ticket_record.id,
        ticket_type=ai_result.ticket_type,
        tone=ai_result.tone,
        priority=ai_result.priority,
        language=ai_result.language,
        summary=ai_result.summary,
        recommendation=ai_result.recommendation,
        ticket_lat=office_decision.ticket_coords[0] if office_decision.ticket_coords else None,
        ticket_lon=office_decision.ticket_coords[1] if office_decision.ticket_coords else None,
        processing_ms=processing_ms,
    )
    db.add(analysis)

    assignment = Assignment(
        ticket_id=ticket_record.id,
        office_id=office.id,
        manager_id=selected_manager_id,
        selected_pair_snapshot=[manager["full_name"] for manager in two],
        rr_turn=rr_turn,
        decision_trace=decision_trace,
    )
    db.add(assignment)

    db.flush()

    return {
        "id": ticket_record.id,
        "run_id": ticket_record.run_id,
        "ticket_id": ticket_record.external_id or ticket_record.id,
        "ticket_index": ticket_index,
        "ticket_type": ai_result.ticket_type,
        "sentiment": ai_result.tone,
        "priority": ai_result.priority,
        "language": ai_result.language,
        "summary": ai_result.summary,
        "recommendation": ai_result.recommendation,
        "office": office.office,
        "selected_managers": [manager["full_name"] for manager in two],
        "assigned_manager": selected_manager_name,
        "ticket_lat": office_decision.ticket_coords[0] if office_decision.ticket_coords else None,
        "ticket_lon": office_decision.ticket_coords[1] if office_decision.ticket_coords else None,
        "office_lat": office.latitude,
        "office_lon": office.longitude,
        "processing_ms": processing_ms,
        "segment": ticket_record.segment,
        "city": ticket_record.city,
        "description": ticket_record.description,
        "created_at": ticket_record.created_at.isoformat() if ticket_record.created_at else None,
        "rr_turn": rr_turn,
        "decision_trace": decision_trace,
    }
