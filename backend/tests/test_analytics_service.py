from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.models import AIAnalysis, Assignment, Base, BusinessUnit, Manager, Ticket
from backend.schemas.ai import AssistantFilters
from backend.services.analytics import AnalyticsService


class DummySettings:
    openai_api_key = None
    openai_model = "gpt-4o-mini"
    openai_timeout_seconds = 5.0


def _session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return SessionLocal()


def _seed(session: Session) -> None:
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
        external_id="TK-1",
        segment="VIP",
        description="Fraud complaint",
        country="Казахстан",
        region="",
        city="Астана",
        street="X",
        house="1",
        birth_date="1990-01-01",
    )
    ticket_2 = Ticket(
        external_id="TK-2",
        segment="Mass",
        description="Consultation",
        country="Казахстан",
        region="",
        city="Алматы",
        street="Y",
        house="2",
        birth_date="2000-01-01",
    )
    session.add_all([ticket_1, ticket_2])
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
                processing_ms=1000,
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
                decision_trace={"geo": {"strategy": "nearest_geo"}},
            ),
            Assignment(
                ticket_id=ticket_2.id,
                office_id=almaty.id,
                manager_id=manager_b.id,
                selected_pair_snapshot=["Manager B", "Manager A"],
                rr_turn=1,
                decision_trace={"geo": {"strategy": "fallback_split"}},
            ),
        ]
    )
    session.commit()


def test_average_age_by_office_returns_chart_ready_data() -> None:
    session = _session()
    try:
        _seed(session)
        service = AnalyticsService(DummySettings())

        result = service.get_average_age_by_office(session, AssistantFilters(office_names=["Астана", "Алматы"]))

        assert result["labels"] == ["Астана", "Алматы"]
        assert len(result["values"]) == 2
        assert all(isinstance(value, float) for value in result["values"])
        assert result["table"][0]["office"] == "Астана"
    finally:
        session.close()


def test_ticket_distribution_by_city_respects_language_filter() -> None:
    session = _session()
    try:
        _seed(session)
        service = AnalyticsService(DummySettings())

        result = service.get_ticket_distribution_by_city(session, AssistantFilters(language="ENG"))

        assert result["labels"] == ["Алматы"]
        assert result["values"] == [1]
        assert result["table"] == [{"city": "Алматы", "count": 1}]
    finally:
        session.close()


def test_assistant_query_maps_to_allowed_intent_and_shape() -> None:
    session = _session()
    try:
        _seed(session)
        service = AnalyticsService(DummySettings())

        response = service.assistant_query(session, "показать средний возраст клиентов по офисам Астаны и Алматы")

        assert response["intent"] == "average_age_by_office"
        assert response["chart_type"] == "bar"
        assert "title" in response
        assert "data" in response and set(response["data"].keys()) == {"labels", "values"}
        assert isinstance(response["table"], list)
        assert "explanation" in response
    finally:
        session.close()
