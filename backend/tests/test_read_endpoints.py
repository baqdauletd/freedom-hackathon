from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app
from backend.db.models import AIAnalysis, Assignment, Base, BusinessUnit, Manager, ProcessingJob, ProcessingRun, Ticket
from backend.db.session import get_db


def _seed(session: Session) -> tuple[int, str]:
    run = ProcessingRun(
        id="run-test-1",
        status="completed",
        tickets_total=2,
        tickets_success=2,
        tickets_failed=0,
        avg_processing_ms=2100,
        elapsed_ms=4200,
    )
    session.add(run)
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
        run_id=run.id,
        external_id="TK-1",
        segment="VIP",
        description="Fraud complaint",
        country="Казахстан",
        region="",
        city="Астана",
        street="X",
        house="1",
    )
    ticket_2 = Ticket(
        run_id=run.id,
        external_id="TK-2",
        segment="Mass",
        description="Consultation",
        country="Казахстан",
        region="",
        city="Алматы",
        street="Y",
        house="2",
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

    return ticket_1.id, run.id


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


def test_results_endpoint_supports_filter_and_pagination() -> None:
    client, session = _build_client()
    try:
        _, run_id = _seed(session)

        response = client.get(
            "/results",
            params={
                "run_id": run_id,
                "office": "Астана",
                "limit": 1,
                "offset": 0,
                "sort_by": "priority",
                "sort_order": "desc",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert len(payload["items"]) == 1
        assert payload["items"][0]["ticket_id"] == "TK-1"
    finally:
        app.dependency_overrides.clear()
        client.close()
        session.close()


def test_ticket_detail_exposes_decision_trace() -> None:
    client, session = _build_client()
    try:
        ticket_id, _ = _seed(session)
        response = client.get(f"/tickets/{ticket_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ticket"]["external_id"] == "TK-1"
        assert payload["assignment"]["decision_trace"]["geo"]["strategy"] == "nearest_geo"
    finally:
        app.dependency_overrides.clear()
        client.close()
        session.close()


def test_managers_endpoint_returns_assigned_count() -> None:
    client, session = _build_client()
    try:
        _, run_id = _seed(session)
        response = client.get("/managers", params={"run_id": run_id})
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["items"]) == 2
        first = payload["items"][0]
        assert "assigned_count" in first
    finally:
        app.dependency_overrides.clear()
        client.close()
        session.close()


def test_run_and_job_status_endpoints() -> None:
    client, session = _build_client()
    try:
        _, run_id = _seed(session)
        with session.begin():
            job = ProcessingJob(
                run_id=run_id,
                status="queued",
                attempt_count=0,
                max_attempts=3,
                payload={"tickets": [], "managers": [], "business_units": []},
            )
            session.add(job)
            session.flush()
            job_id = job.id

        run_response = client.get(f"/runs/{run_id}/status")
        assert run_response.status_code == 200
        run_payload = run_response.json()
        assert run_payload["run_id"] == run_id
        assert run_payload["job"]["job_id"] == job_id

        job_response = client.get(f"/jobs/{job_id}")
        assert job_response.status_code == 200
        job_payload = job_response.json()
        assert job_payload["job_id"] == job_id
        assert job_payload["run_id"] == run_id
    finally:
        app.dependency_overrides.clear()
        client.close()
        session.close()
