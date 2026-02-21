from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import Base, BusinessUnit, Manager
from backend.schemas.ai import AIResult
from backend.services.assignment import assign_ticket, create_ticket_record
from backend.services.routing import OfficeDecision


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    return SessionLocal()


def _ticket_payload(ticket_id: str) -> dict[str, str]:
    return {
        "ID": ticket_id,
        "Пол клиента": "М",
        "Дата рождения": "2000-01-01",
        "Сегмент клиента": "Mass",
        "Описание": "test",
        "Вложения": "",
        "Страна": "Казахстан",
        "Регион": "",
        "Город": "Астана",
        "Улица": "Туран",
        "Дом": "1",
    }


def test_dynamic_two_lowest_is_recomputed_each_ticket_with_rr() -> None:
    db = _session()
    try:
        office = BusinessUnit(office="Астана", address="addr", latitude=51.1, longitude=71.4)
        db.add(office)
        db.flush()
        db.add_all(
            [
                Manager(full_name="A", position="Главный специалист", skills=["RU"], current_load=1, office_id=office.id),
                Manager(full_name="B", position="Главный специалист", skills=["RU"], current_load=3, office_id=office.id),
                Manager(full_name="C", position="Главный специалист", skills=["RU"], current_load=3, office_id=office.id),
                Manager(full_name="D", position="Главный специалист", skills=["RU"], current_load=7, office_id=office.id),
            ]
        )
        db.commit()

        decision = OfficeDecision(office_name="Астана", ticket_coords=(51.1, 71.4), office_coords=(51.1, 71.4))
        ai = AIResult(
            ticket_type="Консультация",
            tone="Нейтральный",
            priority=5,
            language="RU",
            summary="ok.",
            recommendation="next.",
        )

        assigned: list[str] = []
        pairs: list[list[str]] = []
        for idx in range(4):
            with db.begin():
                ticket = create_ticket_record(db, _ticket_payload(f"t-{idx}"))
                result = assign_ticket(db, ticket, ai, decision, ticket_index=idx, processing_ms=1)
                assigned.append(result["assigned_manager"])
                pairs.append(result["selected_managers"])

        assert pairs == [["A", "B"], ["A", "B"], ["A", "C"], ["A", "C"]]
        assert assigned == ["A", "B", "A", "C"]
    finally:
        db.close()
