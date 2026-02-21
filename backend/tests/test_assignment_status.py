from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import Assignment, Base, BusinessUnit, Manager
from backend.schemas.ai import AIResult
from backend.services.assignment import assign_ticket, create_ticket_record
from backend.services.routing import OfficeDecision


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    return SessionLocal()


def test_unassigned_status_and_reason_when_no_eligible_manager() -> None:
    db = _session()
    try:
        office = BusinessUnit(office="Астана", address="addr", latitude=51.1, longitude=71.4)
        db.add(office)
        db.flush()
        db.add(Manager(full_name="M1", position="Специалист", skills=["RU"], current_load=0, office_id=office.id))
        db.commit()

        ai = AIResult(
            ticket_type="Консультация",
            tone="Нейтральный",
            priority=5,
            language="ENG",
            summary="ok.",
            recommendation="next.",
        )
        decision = OfficeDecision(
            office_name="Астана",
            ticket_coords=None,
            office_coords=(51.1, 71.4),
            strategy="fallback_split",
            used_fallback=True,
            fallback_reason="missing_address",
        )

        with db.begin():
            ticket = create_ticket_record(
                db,
                {
                    "ID": "t-unassigned",
                    "Пол клиента": "М",
                    "Дата рождения": "2000-01-01",
                    "Сегмент клиента": "VIP",
                    "Описание": "a",
                    "Вложения": "",
                    "Страна": "Казахстан",
                    "Регион": "",
                    "Город": "Астана",
                    "Улица": "X",
                    "Дом": "1",
                },
            )
            result = assign_ticket(db, ticket, ai, decision, ticket_index=0, processing_ms=10)

        assert result["assignment_status"] == "unassigned"
        assert result["unassigned_reason"] == "no_eligible_manager"
        assert "assignment:no_eligible_manager" in result["warnings"]
        assert "geo_fallback:missing_address" in result["warnings"]

        assignment = db.execute(select(Assignment).where(Assignment.ticket_id == ticket.id)).scalar_one()
        assert assignment.assignment_status == "unassigned"
        assert assignment.unassigned_reason == "no_eligible_manager"
    finally:
        db.close()


def test_decision_trace_contains_required_explainability_keys() -> None:
    db = _session()
    try:
        office = BusinessUnit(office="Астана", address="addr", latitude=51.1, longitude=71.4)
        db.add(office)
        db.flush()
        db.add_all(
            [
                Manager(full_name="M1", position="Главный специалист", skills=["VIP", "ENG"], current_load=1, office_id=office.id),
                Manager(full_name="M2", position="Главный специалист", skills=["VIP", "ENG"], current_load=2, office_id=office.id),
            ]
        )
        db.commit()

        ai = AIResult(
            ticket_type="Консультация",
            tone="Нейтральный",
            priority=5,
            language="ENG",
            summary="ok.",
            recommendation="next.",
        )
        decision = OfficeDecision(office_name="Астана", ticket_coords=(51.1, 71.4), office_coords=(51.1, 71.4), strategy="nearest_geo")

        with db.begin():
            ticket = create_ticket_record(
                db,
                {
                    "ID": "t-trace",
                    "Пол клиента": "М",
                    "Дата рождения": "2000-01-01",
                    "Сегмент клиента": "VIP",
                    "Описание": "a",
                    "Вложения": "",
                    "Страна": "Казахстан",
                    "Регион": "",
                    "Город": "Астана",
                    "Улица": "X",
                    "Дом": "1",
                },
            )
            result = assign_ticket(db, ticket, ai, decision, ticket_index=0, processing_ms=10)

        trace = result["decision_trace"]
        assert "geo" in trace
        assert "rules" in trace
        assert "eligibility" in trace
        assert "selected_pair" in trace
        assert "round_robin" in trace
        assert "assignment_status" in trace
        assert isinstance(trace["selected_pair"], list)
    finally:
        db.close()

