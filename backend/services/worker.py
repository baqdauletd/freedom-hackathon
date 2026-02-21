from __future__ import annotations

import logging
import os
import socket
import time
from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.db.session import SessionLocal
from backend.services.processing import process_tickets
from backend.services.queue import claim_next_job, mark_job_failed, mark_job_succeeded

LOGGER = logging.getLogger("fire.worker")


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def process_next_job(db: Session, settings: Settings, worker_id: str) -> dict[str, Any] | None:
    job = claim_next_job(db, worker_id)
    if job is None:
        return None

    payload = job.payload or {}
    tickets = payload.get("tickets")
    managers = payload.get("managers")
    business_units = payload.get("business_units")
    source_filenames = payload.get("source_filenames") or {}

    if not isinstance(tickets, list) or not isinstance(managers, list) or not isinstance(business_units, list):
        status = mark_job_failed(db, settings, job.id, "Invalid job payload")
        return {"job_id": job.id, "run_id": job.run_id, "status": status}

    try:
        envelope = process_tickets(
            db=db,
            settings=settings,
            tickets=tickets,
            managers=managers,
            business_units=business_units,
            source_filenames=source_filenames if isinstance(source_filenames, dict) else {},
            run_id=job.run_id,
        )
    except Exception as exc:
        status = mark_job_failed(db, settings, job.id, str(exc))
        LOGGER.exception(
            "processing_job_failed",
            extra={
                "job_id": job.id,
                "run_id": job.run_id,
                "status": status,
                "attempt_count": job.attempt_count,
                "max_attempts": job.max_attempts,
            },
        )
        return {"job_id": job.id, "run_id": job.run_id, "status": status, "error": str(exc)}

    mark_job_succeeded(db, job.id)
    return {
        "job_id": job.id,
        "run_id": job.run_id,
        "status": "completed",
        "summary": envelope.get("summary", {}),
    }


def run_worker_loop(*, once: bool = False, max_jobs: int | None = None) -> int:
    settings = get_settings()
    worker_id = _worker_id()
    processed = 0

    while True:
        with SessionLocal() as db:
            outcome = process_next_job(db, settings, worker_id)

        if outcome is None:
            if once:
                break
            time.sleep(max(0.1, settings.worker_poll_interval_seconds))
            continue

        processed += 1
        LOGGER.info("processing_job_done", extra={"worker_id": worker_id, "outcome": outcome})

        if once:
            break
        if max_jobs is not None and processed >= max_jobs:
            break

    return processed
