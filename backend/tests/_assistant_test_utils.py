from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.models import AIAnalysis, Assignment, Base, BusinessUnit, Manager, ProcessingRun, Ticket


class DummySettings:
    openai_api_key = None
    openai_model = "gpt-4o-mini"
    openai_timeout_seconds = 5.0


def build_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return session_local()


def seed_assistant_dataset(session: Session) -> dict[str, str]:
    run_1 = ProcessingRun(id="11111111-1111-4111-8111-111111111111", status="completed")
    run_2 = ProcessingRun(id="22222222-2222-4222-8222-222222222222", status="completed")
    session.add_all([run_1, run_2])
    session.flush()

    astana = BusinessUnit(office="Астана", address="addr", latitude=51.1, longitude=71.4)
    almaty = BusinessUnit(office="Алматы", address="addr2", latitude=43.2, longitude=76.8)
    session.add_all([astana, almaty])
    session.flush()

    manager_a = Manager(
        full_name="Manager A",
        position="Главный специалист",
        skills=["VIP", "KZ"],
        current_load=3,
        office_id=astana.id,
    )
    manager_b = Manager(
        full_name="Manager B",
        position="Специалист",
        skills=["ENG"],
        current_load=1,
        office_id=almaty.id,
    )
    session.add_all([manager_a, manager_b])
    session.flush()

    ticket_1 = Ticket(
        run_id=run_1.id,
        external_id="TK-R1-1",
        segment="VIP",
        description="Fraud complaint in Astana",
        country="Казахстан",
        region="",
        city="Астана",
        street="X",
        house="1",
        birth_date="1990-01-01",
    )
    ticket_2 = Ticket(
        run_id=run_2.id,
        external_id="TK-R2-1",
        segment="Mass",
        description="Consultation in Almaty",
        country="Казахстан",
        region="",
        city="Алматы",
        street="Y",
        house="2",
        birth_date="2000-01-01",
    )
    ticket_3 = Ticket(
        run_id=run_1.id,
        external_id="TK-R1-2",
        segment="Mass",
        description="Unassigned case",
        country="Казахстан",
        region="",
        city="Астана",
        street="Z",
        house="3",
        birth_date="1988-03-03",
    )
    session.add_all([ticket_1, ticket_2, ticket_3])
    session.flush()

    session.add_all(
        [
            AIAnalysis(
                ticket_id=ticket_1.id,
                ticket_type="Жалоба",
                tone="Негативный",
                priority=9,
                language="RU",
                summary="Summary 1",
                recommendation="Action 1",
                ticket_lat=51.1,
                ticket_lon=71.4,
                processing_ms=3200,
            ),
            AIAnalysis(
                ticket_id=ticket_2.id,
                ticket_type="Консультация",
                tone="Нейтральный",
                priority=4,
                language="ENG",
                summary="Summary 2",
                recommendation="Action 2",
                ticket_lat=43.2,
                ticket_lon=76.8,
                processing_ms=1200,
            ),
            AIAnalysis(
                ticket_id=ticket_3.id,
                ticket_type="Смена данных",
                tone="Нейтральный",
                priority=5,
                language="RU",
                summary="Summary 3",
                recommendation="Action 3",
                ticket_lat=51.2,
                ticket_lon=71.3,
                processing_ms=4600,
            ),
        ]
    )
    session.flush()

    session.add_all(
        [
            Assignment(
                ticket_id=ticket_1.id,
                office_id=astana.id,
                manager_id=manager_a.id,
                selected_pair_snapshot=["Manager A", "Manager B"],
                rr_turn=0,
                assignment_status="assigned",
                assigned_at=datetime(2026, 2, 20, 10, 0, 0),
                decision_trace={"geo": {"strategy": "nearest_geo"}},
            ),
            Assignment(
                ticket_id=ticket_2.id,
                office_id=almaty.id,
                manager_id=manager_b.id,
                selected_pair_snapshot=["Manager B", "Manager A"],
                rr_turn=1,
                assignment_status="assigned",
                assigned_at=datetime(2026, 2, 21, 10, 0, 0),
                decision_trace={"geo": {"strategy": "nearest_geo"}},
            ),
            Assignment(
                ticket_id=ticket_3.id,
                office_id=astana.id,
                manager_id=None,
                selected_pair_snapshot=[],
                rr_turn=0,
                assignment_status="unassigned",
                unassigned_reason="no_eligible_managers",
                assigned_at=datetime(2026, 2, 21, 12, 0, 0),
                decision_trace={"warnings": ["No eligible manager"]},
            ),
        ]
    )
    session.commit()

    return {"run_1": run_1.id, "run_2": run_2.id}
