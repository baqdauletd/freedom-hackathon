from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app
from backend.db.models import AIAnalysis, Assignment, Base, BusinessUnit, Manager, ProcessingRun, Ticket
from backend.db.session import get_db


def _build_client() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = SessionLocal()

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app), session


def _seed_consistency_case(session: Session) -> tuple[str, int]:
    run = ProcessingRun(
        id="run-consistency",
        status="completed",
        tickets_total=14,
        tickets_success=14,
        tickets_failed=0,
        avg_processing_ms=1200,
        elapsed_ms=17000,
    )
    session.add(run)
    session.flush()

    office = BusinessUnit(office="Астана", address="addr", latitude=51.1, longitude=71.4)
    session.add(office)
    session.flush()

    manager_a = Manager(
        full_name="Иван Иванов",
        position="Специалист",
        skills=["RU"],
        current_load=8,
        office_id=office.id,
    )
    session.add(manager_a)
    session.flush()

    old_assigned_at = datetime(2026, 2, 1, 10, 0, 0)
    new_assigned_at = datetime(2026, 2, 20, 10, 0, 0)

    for index in range(14):
        ticket = Ticket(
            run_id=run.id,
            external_id=f"T-{index + 1}",
            segment="Mass",
            description=f"Ticket {index + 1}",
            country="Казахстан",
            region="",
            city="Астана",
            street="X",
            house=str(index + 1),
        )
        session.add(ticket)
        session.flush()

        session.add(
            AIAnalysis(
                ticket_id=ticket.id,
                ticket_type="Консультация",
                tone="Нейтральный",
                priority=3,
                language="RU",
                summary="Summary",
                recommendation="Recommendation",
                ticket_lat=51.1,
                ticket_lon=71.4,
                processing_ms=900,
            )
        )
        session.flush()

        session.add(
            Assignment(
                ticket_id=ticket.id,
                office_id=office.id,
                manager_id=manager_a.id,
                selected_pair_snapshot=["Иван Иванов"],
                rr_turn=0,
                decision_trace={"geo": {"strategy": "nearest_geo"}},
                assigned_at=old_assigned_at if index < 10 else new_assigned_at,
            )
        )

    session.commit()
    return run.id, manager_a.id


def test_assigned_ticket_count_is_consistent_between_results_and_analytics() -> None:
    client, session = _build_client()
    try:
        run_id, manager_id = _seed_consistency_case(session)

        results_response = client.get(
            "/results",
            params={"run_id": run_id, "manager_id": manager_id, "limit": 200, "offset": 0},
        )
        assert results_response.status_code == 200
        results_payload = results_response.json()
        assert results_payload["total"] == 14

        analytics_response = client.get("/analytics/summary", params={"run_id": run_id})
        assert analytics_response.status_code == 200
        analytics_payload = analytics_response.json()
        manager_row = next(row for row in analytics_payload["workload_by_manager"] if row["manager_id"] == manager_id)
        assert manager_row["assigned_ticket_count"] == 14
        assert manager_row["current_load"] == 8

        scoped_results_response = client.get(
            "/results",
            params={
                "run_id": run_id,
                "manager_id": manager_id,
                "date_from": "2026-02-15",
                "date_to": "2026-02-28",
                "limit": 200,
                "offset": 0,
            },
        )
        assert scoped_results_response.status_code == 200
        scoped_results_payload = scoped_results_response.json()
        assert scoped_results_payload["total"] == 4

        scoped_analytics_response = client.get(
            "/analytics/summary",
            params={"run_id": run_id, "date_from": "2026-02-15", "date_to": "2026-02-28"},
        )
        assert scoped_analytics_response.status_code == 200
        scoped_analytics_payload = scoped_analytics_response.json()
        scoped_row = next(row for row in scoped_analytics_payload["workload_by_manager"] if row["manager_id"] == manager_id)
        assert scoped_row["assigned_ticket_count"] == 4
    finally:
        app.dependency_overrides.clear()
        client.close()
        session.close()
