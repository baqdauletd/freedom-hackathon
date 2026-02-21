from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.models import Base, ProcessingJob, ProcessingRun
from backend.services.queue import claim_next_job, enqueue_processing_job, mark_job_failed


class DummySettings:
    worker_max_attempts = 2
    worker_retry_base_seconds = 1
    worker_retry_max_seconds = 5


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


def _sample_rows() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    tickets = [
        {
            "ID": "T-1",
            "Пол клиента": "М",
            "Дата рождения": "1995-01-01",
            "Сегмент клиента": "Mass",
            "Описание": "Test ticket",
            "Вложения": "",
            "Страна": "Казахстан",
            "Регион": "Акмолинская область",
            "Город": "Астана",
            "Улица": "Достык",
            "Дом": "1",
        }
    ]
    managers = [
        {
            "ФИО": "Manager A",
            "Должность": "Специалист",
            "Навыки": "RU",
            "Офис": "Астана",
            "Количество обращений в работе": "0",
        }
    ]
    business_units = [
        {"Офис": "Астана", "Адрес": "Астана", "Широта": "51.1694", "Долгота": "71.4491"}
    ]
    return tickets, managers, business_units


def test_enqueue_processing_job_respects_idempotency_key() -> None:
    session = _session()
    try:
        tickets, managers, business_units = _sample_rows()
        first = enqueue_processing_job(
            session,
            DummySettings(),
            tickets=tickets,
            managers=managers,
            business_units=business_units,
            idempotency_key="abc-123",
        )
        second = enqueue_processing_job(
            session,
            DummySettings(),
            tickets=tickets,
            managers=managers,
            business_units=business_units,
            idempotency_key="abc-123",
        )

        assert first.reused is False
        assert second.reused is True
        assert first.job.id == second.job.id
        assert first.job.run_id == second.job.run_id

        jobs_count = int(session.execute(select(func.count()).select_from(ProcessingJob)).scalar_one() or 0)
        runs_count = int(session.execute(select(func.count()).select_from(ProcessingRun)).scalar_one() or 0)
        assert jobs_count == 1
        assert runs_count == 1
    finally:
        session.close()


def test_claim_and_retry_transition_to_failed_when_attempts_exhausted() -> None:
    session = _session()
    try:
        tickets, managers, business_units = _sample_rows()
        enqueue = enqueue_processing_job(
            session,
            DummySettings(),
            tickets=tickets,
            managers=managers,
            business_units=business_units,
            idempotency_key="retry-case",
        )

        first_claim = claim_next_job(session, worker_id="worker-1")
        assert first_claim is not None
        assert first_claim.status == "running"
        assert first_claim.attempt_count == 1

        first_status = mark_job_failed(session, DummySettings(), enqueue.job.id, "boom-1")
        assert first_status == "retry_wait"

        with session.begin():
            job = session.get(ProcessingJob, enqueue.job.id)
            assert job is not None
            job.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        second_claim = claim_next_job(session, worker_id="worker-1")
        assert second_claim is not None
        assert second_claim.attempt_count == 2

        second_status = mark_job_failed(session, DummySettings(), enqueue.job.id, "boom-2")
        assert second_status == "failed"

        job = session.get(ProcessingJob, enqueue.job.id)
        run = session.get(ProcessingRun, enqueue.job.run_id)
        assert job is not None and run is not None
        assert job.status == "failed"
        assert run.status == "failed"
    finally:
        session.close()
