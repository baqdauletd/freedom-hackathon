from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, select
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


def test_round_robin_alternates_and_load_increments() -> None:
    db = _session()
    try:
        office = BusinessUnit(office="Астана", address="addr", latitude=51.1, longitude=71.4)
        db.add(office)
        db.flush()

        db.add_all(
            [
                Manager(full_name="M1", position="Главный специалист", skills=["VIP", "KZ", "ENG"], current_load=0, office_id=office.id),
                Manager(full_name="M2", position="Главный специалист", skills=["VIP", "KZ", "ENG"], current_load=2, office_id=office.id),
                Manager(full_name="M3", position="Главный специалист", skills=["VIP", "KZ", "ENG"], current_load=2, office_id=office.id),
            ]
        )
        db.commit()

        ai = AIResult(
            ticket_type="Консультация",
            tone="Нейтральный",
            priority=5,
            language="RU",
            summary="ok.",
            recommendation="next.",
        )
        decision = OfficeDecision(office_name="Астана", ticket_coords=(51.1, 71.4), office_coords=(51.1, 71.4))

        with db.begin():
            t1 = create_ticket_record(
                db,
                {
                    "ID": "t1",
                    "Пол клиента": "М",
                    "Дата рождения": "2000-01-01",
                    "Сегмент клиента": "Mass",
                    "Описание": "a",
                    "Вложения": "",
                    "Страна": "Казахстан",
                    "Регион": "",
                    "Город": "Астана",
                    "Улица": "X",
                    "Дом": "1",
                },
            )
            r1 = assign_ticket(db, t1, ai, decision, ticket_index=0, processing_ms=10)

        with db.begin():
            t2 = create_ticket_record(
                db,
                {
                    "ID": "t2",
                    "Пол клиента": "М",
                    "Дата рождения": "2000-01-01",
                    "Сегмент клиента": "Mass",
                    "Описание": "a",
                    "Вложения": "",
                    "Страна": "Казахстан",
                    "Регион": "",
                    "Город": "Астана",
                    "Улица": "X",
                    "Дом": "2",
                },
            )
            r2 = assign_ticket(db, t2, ai, decision, ticket_index=1, processing_ms=10)

        assert r1["assigned_manager"] == "M1"
        assert r2["assigned_manager"] == "M2"

        with db.begin():
            t3 = create_ticket_record(
                db,
                {
                    "ID": "t3",
                    "Пол клиента": "М",
                    "Дата рождения": "2000-01-01",
                    "Сегмент клиента": "Mass",
                    "Описание": "a",
                    "Вложения": "",
                    "Страна": "Казахстан",
                    "Регион": "",
                    "Город": "Астана",
                    "Улица": "X",
                    "Дом": "3",
                },
            )
            r3 = assign_ticket(db, t3, ai, decision, ticket_index=2, processing_ms=10)

        assert set(r3["selected_managers"]) == {"M1", "M3"}

        m1 = db.execute(select(Manager).where(Manager.full_name == "M1")).scalar_one()
        m2 = db.execute(select(Manager).where(Manager.full_name == "M2")).scalar_one()
        assert m1.current_load == 2
        assert m2.current_load == 3
    finally:
        db.close()
