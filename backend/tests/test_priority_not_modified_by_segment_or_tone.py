from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import AIAnalysis, Base, BusinessUnit, Manager
from backend.schemas.ai import AIResult
from backend.services.assignment import assign_ticket, create_ticket_record
from backend.services.routing import OfficeDecision


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    return SessionLocal()


def _ticket_payload(ticket_id: str, segment: str) -> dict[str, str]:
    return {
        "ID": ticket_id,
        "Пол клиента": "М",
        "Дата рождения": "2000-01-01",
        "Сегмент клиента": segment,
        "Описание": "test",
        "Вложения": "",
        "Страна": "Казахстан",
        "Регион": "",
        "Город": "Астана",
        "Улица": "Туран",
        "Дом": "1",
    }


def test_priority_is_not_modified_by_segment_or_tone() -> None:
    db = _session()
    try:
        office = BusinessUnit(office="Астана", address="addr", latitude=51.1, longitude=71.4)
        db.add(office)
        db.flush()
        db.add_all(
            [
                Manager(full_name="M1", position="Главный специалист", skills=["VIP", "RU"], current_load=0, office_id=office.id),
                Manager(full_name="M2", position="Главный специалист", skills=["VIP", "RU"], current_load=0, office_id=office.id),
            ]
        )
        db.commit()

        decision = OfficeDecision(office_name="Астана", ticket_coords=(51.1, 71.4), office_coords=(51.1, 71.4))

        with db.begin():
            vip_ticket = create_ticket_record(db, _ticket_payload("vip-1", "VIP"))
            vip_result = assign_ticket(
                db,
                vip_ticket,
                AIResult(
                    ticket_type="Консультация",
                    tone="Позитивный",
                    priority=2,
                    language="RU",
                    summary="ok.",
                    recommendation="next.",
                ),
                decision,
                ticket_index=0,
                processing_ms=1,
            )

        with db.begin():
            mass_ticket = create_ticket_record(db, _ticket_payload("mass-1", "Mass"))
            mass_result = assign_ticket(
                db,
                mass_ticket,
                AIResult(
                    ticket_type="Консультация",
                    tone="Негативный",
                    priority=7,
                    language="RU",
                    summary="ok.",
                    recommendation="next.",
                ),
                decision,
                ticket_index=1,
                processing_ms=1,
            )

        vip_analysis = db.execute(select(AIAnalysis).where(AIAnalysis.ticket_id == vip_ticket.id)).scalar_one()
        mass_analysis = db.execute(select(AIAnalysis).where(AIAnalysis.ticket_id == mass_ticket.id)).scalar_one()

        assert vip_result["priority"] == 2
        assert mass_result["priority"] == 7
        assert vip_analysis.priority == 2
        assert mass_analysis.priority == 7
    finally:
        db.close()
