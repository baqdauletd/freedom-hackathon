from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import Base, ProcessingJob, ProcessingJobTicket, ProcessingRun
from backend.services.queue import enqueue_processing_job, update_ticket_progress
from backend.tasks import run as run_tasks


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        fire_compliance_mode=True,
        enable_geocode=False,
        geocode_timeout_seconds=1.0,
        geocode_rate_limit_seconds=0.0,
        geocode_fail_streak_limit=3,
        worker_max_attempts=3,
        worker_retry_base_seconds=1,
        worker_retry_max_seconds=10,
    )


def _payload() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    tickets = [
        {
            "ID": "t1",
            "Пол клиента": "М",
            "Дата рождения": "2000-01-01",
            "Сегмент клиента": "Mass",
            "Описание": "one",
            "Вложения": "",
            "Страна": "Казахстан",
            "Регион": "",
            "Город": "Астана",
            "Улица": "X",
            "Дом": "1",
        },
        {
            "ID": "t2",
            "Пол клиента": "Ж",
            "Дата рождения": "2001-01-01",
            "Сегмент клиента": "Mass",
            "Описание": "two",
            "Вложения": "",
            "Страна": "Казахстан",
            "Регион": "",
            "Город": "Астана",
            "Улица": "X",
            "Дом": "2",
        },
    ]
    managers = [
        {
            "ФИО": "Менеджер 1",
            "Должность": "Главный специалист",
            "Офис": "Астана",
            "Навыки": "VIP;ENG;KZ;RU",
            "Количество обращений в работе": "0",
        }
    ]
    offices = [{"Офис": "Астана", "Адрес": "A", "Широта": "51.1", "Долгота": "71.4"}]
    return tickets, managers, offices


def test_job_progress_updates_on_ticket_success_and_failure(monkeypatch) -> None:
    SessionLocal = _session_factory()
    settings = _settings()
    tickets, managers, offices = _payload()

    with SessionLocal() as db:
        enqueue = enqueue_processing_job(
            db,
            settings,
            tickets=tickets,
            managers=managers,
            business_units=offices,
            idempotency_key="job-progress-1",
        )
        run_id = enqueue.job.run_id
        job_id = enqueue.job.id

    monkeypatch.setattr(run_tasks, "SessionLocal", SessionLocal)
    monkeypatch.setattr(run_tasks, "get_settings", lambda: settings)

    class _DummyResult:
        def __init__(self, fn):
            self._fn = fn

        def get(self, disable_sync_subtasks=False):
            return self._fn()

    def _fake_apply_async(*, kwargs, queue):
        ticket_id = int(kwargs["ticket_id"])
        ticket_index = int(kwargs["ticket_index"])
        local_job_id = str(kwargs["job_id"])

        def _run():
            with SessionLocal() as db:
                if ticket_index == 0:
                    update_ticket_progress(
                        db,
                        job_id=local_job_id,
                        ticket_id=ticket_id,
                        stage="done",
                        status="done",
                    )
                    return {"assigned_manager": "Менеджер 1", "processing_ms": 11}
            raise RuntimeError("simulated ticket failure")

        return _DummyResult(_run)

    monkeypatch.setattr(run_tasks.process_ticket, "apply_async", _fake_apply_async)

    outcome = run_tasks.process_run.run(run_id=run_id, job_id=job_id)

    assert outcome["status"] == "completed"
    assert outcome["summary"]["success"] == 1
    assert outcome["summary"]["failed"] == 1

    with SessionLocal() as db:
        run = db.get(ProcessingRun, run_id)
        job = db.get(ProcessingJob, job_id)
        states = db.execute(select(ProcessingJobTicket).where(ProcessingJobTicket.job_id == job_id)).scalars().all()

    assert run is not None and run.tickets_success == 1 and run.tickets_failed == 1
    assert job is not None and job.status == "completed"
    assert len(states) == 2
    assert sorted((state.status for state in states)) == ["done", "failed"]
