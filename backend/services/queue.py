from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.db.models import ProcessingJob, ProcessingRun


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _retry_delay_seconds(settings: Settings, attempt_count: int) -> int:
    exponent = max(0, attempt_count - 1)
    delay = settings.worker_retry_base_seconds * (2**exponent)
    return min(delay, settings.worker_retry_max_seconds)


@dataclass
class EnqueueResult:
    job: ProcessingJob
    reused: bool


def enqueue_processing_job(
    db: Session,
    settings: Settings,
    *,
    tickets: list[dict[str, str]],
    managers: list[dict[str, str]],
    business_units: list[dict[str, str]],
    source_filenames: dict[str, str] | None = None,
    idempotency_key: str | None = None,
) -> EnqueueResult:
    normalized_key = _normalize_idempotency_key(idempotency_key)

    with db.begin():
        if normalized_key:
            existing = db.execute(
                select(ProcessingJob).where(ProcessingJob.idempotency_key == normalized_key).with_for_update()
            ).scalar_one_or_none()
            if existing:
                return EnqueueResult(job=existing, reused=True)

        run = ProcessingRun(
            status="queued",
            tickets_total=len(tickets),
            tickets_success=0,
            tickets_failed=0,
            avg_processing_ms=0,
            elapsed_ms=0,
            tickets_filename=source_filenames.get("tickets") if source_filenames else None,
            managers_filename=source_filenames.get("managers") if source_filenames else None,
            business_units_filename=source_filenames.get("business_units") if source_filenames else None,
        )
        db.add(run)
        db.flush()

        job = ProcessingJob(
            run_id=run.id,
            idempotency_key=normalized_key,
            status="queued",
            attempt_count=0,
            max_attempts=max(1, settings.worker_max_attempts),
            next_attempt_at=_utc_now(),
            payload={
                "tickets": tickets,
                "managers": managers,
                "business_units": business_units,
                "source_filenames": source_filenames or {},
            },
        )
        db.add(job)
        db.flush()

    return EnqueueResult(job=job, reused=False)


def claim_next_job(db: Session, worker_id: str) -> ProcessingJob | None:
    now = _utc_now()
    with db.begin():
        statement = (
            select(ProcessingJob)
            .where(
                ProcessingJob.status.in_(("queued", "retry_wait")),
                ProcessingJob.next_attempt_at <= now,
            )
            .order_by(ProcessingJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = db.execute(statement).scalar_one_or_none()
        if not job:
            return None

        job.status = "running"
        job.attempt_count = int(job.attempt_count or 0) + 1
        job.locked_at = now
        job.locked_by = worker_id
        job.started_at = job.started_at or now
        job.updated_at = now

        run = db.get(ProcessingRun, job.run_id)
        if run:
            run.status = "running"

        db.flush()
        return job


def mark_job_succeeded(db: Session, job_id: str) -> None:
    now = _utc_now()
    with db.begin():
        job = db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()).scalar_one_or_none()
        if not job:
            return

        job.status = "completed"
        job.locked_at = None
        job.locked_by = None
        job.finished_at = now
        job.last_error = None
        job.updated_at = now

        run = db.get(ProcessingRun, job.run_id)
        if run:
            run.status = "completed"


def mark_job_failed(db: Session, settings: Settings, job_id: str, error_message: str) -> str:
    now = _utc_now()
    with db.begin():
        job = db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()).scalar_one_or_none()
        if not job:
            return "missing"

        can_retry = int(job.attempt_count or 0) < int(job.max_attempts or 1)
        if can_retry:
            delay_seconds = _retry_delay_seconds(settings, int(job.attempt_count or 1))
            job.status = "retry_wait"
            job.next_attempt_at = now + timedelta(seconds=delay_seconds)
            run_status = "retry_wait"
        else:
            job.status = "failed"
            job.finished_at = now
            run_status = "failed"

        job.last_error = error_message[:4000]
        job.locked_at = None
        job.locked_by = None
        job.updated_at = now

        run = db.get(ProcessingRun, job.run_id)
        if run:
            run.status = run_status

        return job.status
