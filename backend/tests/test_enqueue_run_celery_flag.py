from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import Base, ProcessingJob
from backend.services.queue import enqueue_run


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    return SessionLocal()


def test_enqueue_run_uses_celery_when_flag_on(monkeypatch) -> None:
    db = _session()
    dispatched: list[tuple[str, str]] = []

    def _fake_dispatch(run_id: str, job_id: str) -> None:
        dispatched.append((run_id, job_id))

    monkeypatch.setattr("backend.services.queue._dispatch_celery_run", _fake_dispatch)

    settings = SimpleNamespace(
        use_celery=True,
        worker_max_attempts=3,
        worker_retry_base_seconds=2,
        worker_retry_max_seconds=60,
    )

    enqueue = enqueue_run(
        db,
        settings,
        tickets=[{"ID": "t1"}],
        managers=[{"ФИО": "M1"}],
        business_units=[{"Офис": "Астана"}],
        idempotency_key="abc-1",
    )

    job = db.get(ProcessingJob, enqueue.job.id)
    assert job is not None
    assert job.status == "scheduled"
    assert dispatched == [(enqueue.job.run_id, enqueue.job.id)]

