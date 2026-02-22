from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.db.models import ProcessingJob, ProcessingJobTicket, ProcessingRun, Ticket


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


def _dispatch_celery_run(run_id: str, job_id: str) -> None:
    # Lazy import to avoid mandatory Celery dependency when USE_CELERY=false.
    from backend.tasks.run import process_run

    process_run.apply_async(kwargs={"run_id": run_id, "job_id": job_id}, queue="default")


def enqueue_run(
    db: Session,
    settings: Settings,
    *,
    tickets: list[dict[str, str]],
    managers: list[dict[str, str]],
    business_units: list[dict[str, str]],
    source_filenames: dict[str, str] | None = None,
    idempotency_key: str | None = None,
) -> EnqueueResult:
    enqueue = enqueue_processing_job(
        db,
        settings,
        tickets=tickets,
        managers=managers,
        business_units=business_units,
        source_filenames=source_filenames,
        idempotency_key=idempotency_key,
    )

    if settings.use_celery and not enqueue.reused:
        with db.begin():
            job = db.execute(select(ProcessingJob).where(ProcessingJob.id == enqueue.job.id).with_for_update()).scalar_one_or_none()
            run = db.get(ProcessingRun, enqueue.job.run_id)
            if job:
                job.status = "scheduled"
                job.updated_at = _utc_now()
            if run:
                run.status = "scheduled"

        try:
            _dispatch_celery_run(enqueue.job.run_id, enqueue.job.id)
        except Exception as exc:
            mark_job_failed(db, settings, enqueue.job.id, f"celery_dispatch_failed: {exc}", retryable=False)
            raise

    return enqueue


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


def start_job_execution(db: Session, job_id: str, worker_id: str) -> ProcessingJob | None:
    now = _utc_now()
    with db.begin():
        job = db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()).scalar_one_or_none()
        if not job:
            return None
        if job.status in {"completed", "failed"}:
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


def mark_job_failed(
    db: Session,
    settings: Settings,
    job_id: str,
    error_message: str,
    *,
    retryable: bool = True,
) -> str:
    now = _utc_now()
    with db.begin():
        job = db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()).scalar_one_or_none()
        if not job:
            return "missing"

        can_retry = retryable and int(job.attempt_count or 0) < int(job.max_attempts or 1)
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


def upsert_ticket_progress(db: Session, job_id: str, ticket: Ticket) -> ProcessingJobTicket:
    now = _utc_now()
    with db.begin():
        state = db.execute(
            select(ProcessingJobTicket)
            .where(ProcessingJobTicket.job_id == job_id, ProcessingJobTicket.ticket_id == ticket.id)
            .with_for_update()
        ).scalar_one_or_none()
        if state is None:
            state = ProcessingJobTicket(
                job_id=job_id,
                ticket_id=ticket.id,
                external_ticket_id=ticket.external_id or str(ticket.id),
                stage="queued",
                status="pending",
                started_at=now,
                updated_at=now,
            )
            db.add(state)
            db.flush()
        return state


def update_ticket_progress(
    db: Session,
    *,
    job_id: str,
    ticket_id: int,
    stage: str,
    status: str,
    error_message: str | None = None,
    retries: int | None = None,
) -> None:
    now = _utc_now()
    with db.begin():
        state = db.execute(
            select(ProcessingJobTicket)
            .where(ProcessingJobTicket.job_id == job_id, ProcessingJobTicket.ticket_id == ticket_id)
            .with_for_update()
        ).scalar_one_or_none()
        if state is None:
            ticket = db.get(Ticket, ticket_id)
            if not ticket:
                return
            state = ProcessingJobTicket(
                job_id=job_id,
                ticket_id=ticket_id,
                external_ticket_id=ticket.external_id or str(ticket_id),
                stage=stage,
                status=status,
                updated_at=now,
                started_at=now,
            )
            db.add(state)
        else:
            state.stage = stage
            state.status = status
            state.updated_at = now

        if retries is not None:
            state.retries = max(0, int(retries))

        if error_message:
            state.last_error = error_message[:4000]
        elif status not in {"failed", "retry_wait"}:
            state.last_error = None

        if status == "running" and state.started_at is None:
            state.started_at = now
        if status in {"done", "failed"}:
            state.finished_at = now


def bump_retry_with_jitter(base_seconds: int, max_seconds: int, retries: int) -> int:
    exponent = max(0, retries)
    raw = min(max_seconds, base_seconds * (2**exponent))
    jitter = random.randint(0, max(1, raw // 5))
    return raw + jitter
