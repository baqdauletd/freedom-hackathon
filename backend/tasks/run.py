from __future__ import annotations

import os
import socket
import time
from typing import Any

from sqlalchemy import delete

from backend.celery_app import celery_app
from backend.core.config import get_settings
from backend.db.models import ProcessingRun, Ticket
from backend.db.session import SessionLocal
from backend.services.assignment import create_ticket_record, upsert_business_units, upsert_managers
from backend.services.geocoding import GeocodingService
from backend.services.queue import (
    mark_job_failed,
    mark_job_succeeded,
    start_job_execution,
    update_ticket_progress,
    upsert_ticket_progress,
)
from backend.tasks.ticket import process_ticket


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


@celery_app.task(bind=True, name="backend.tasks.run.process_run")
def process_run(self, *, run_id: str, job_id: str) -> dict[str, Any]:
    settings = get_settings()
    started_all = time.perf_counter()
    worker_id = _worker_id()

    with SessionLocal() as db:
        job = start_job_execution(db, job_id, worker_id)
        if job is None:
            return {"run_id": run_id, "job_id": job_id, "status": "skipped"}

        payload = job.payload or {}
        tickets = payload.get("tickets")
        managers = payload.get("managers")
        business_units = payload.get("business_units")

        if not isinstance(tickets, list) or not isinstance(managers, list) or not isinstance(business_units, list):
            status = mark_job_failed(db, settings, job_id, "Invalid job payload", retryable=False)
            return {"run_id": run_id, "job_id": job_id, "status": status}

    total_expected = len(tickets)
    missing_run = False

    with SessionLocal() as db:
        geocoder = GeocodingService(settings)
        with db.begin():
            run = db.get(ProcessingRun, run_id)
            if run is None:
                missing_run = True
            else:
                db.execute(delete(Ticket).where(Ticket.run_id == run_id))
                run.status = "running"
                run.tickets_total = total_expected
                run.tickets_success = 0
                run.tickets_failed = 0
                run.avg_processing_ms = 0
                run.elapsed_ms = 0

                offices = upsert_business_units(db, business_units, geocoder)
                offices_by_name = {office.office: office for office in offices}
                upsert_managers(db, managers, offices_by_name)

    if missing_run:
        with SessionLocal() as db:
            status = mark_job_failed(db, settings, job_id, "Run not found", retryable=False)
        return {"run_id": run_id, "job_id": job_id, "status": status}

    results: list[dict[str, Any]] = []
    success = 0
    failed = 0
    total_processing_ms = 0

    for idx, ticket_row in enumerate(tickets):
        with SessionLocal() as db:
            with db.begin():
                ticket_record = create_ticket_record(db, ticket_row, run_id=run_id)
            upsert_ticket_progress(db, job_id, ticket_record)
            ticket_id = ticket_record.id

        try:
            result = process_ticket.apply_async(
                kwargs={
                    "ticket_id": ticket_id,
                    "run_id": run_id,
                    "job_id": job_id,
                    "ticket_index": idx,
                },
                queue="default",
            ).get(disable_sync_subtasks=False)
        except Exception as exc:
            with SessionLocal() as db:
                update_ticket_progress(
                    db,
                    job_id=job_id,
                    ticket_id=ticket_id,
                    stage="failed",
                    status="failed",
                    error_message=str(exc),
                )
            result = {
                "id": ticket_id,
                "run_id": run_id,
                "ticket_id": ticket_row.get("ID") or ticket_id,
                "ticket_index": idx,
                "assigned_manager": None,
                "processing_ms": 0,
            }

        results.append(result)
        total_processing_ms += int(result.get("processing_ms") or 0)
        if result.get("assigned_manager"):
            success += 1
        else:
            failed += 1

        with SessionLocal() as db:
            with db.begin():
                run = db.get(ProcessingRun, run_id)
                if run:
                    run.status = "running"
                    run.tickets_total = total_expected
                    run.tickets_success = success
                    run.tickets_failed = failed
                    processed = success + failed
                    run.avg_processing_ms = round(total_processing_ms / processed) if processed else 0
                    run.elapsed_ms = int((time.perf_counter() - started_all) * 1000)

    total = len(results)
    avg_processing_ms = round(total_processing_ms / total) if total else 0
    elapsed_ms = int((time.perf_counter() - started_all) * 1000)
    with SessionLocal() as db:
        with db.begin():
            run = db.get(ProcessingRun, run_id)
            if run:
                run.status = "completed"
                run.tickets_total = total
                run.tickets_success = success
                run.tickets_failed = failed
                run.avg_processing_ms = avg_processing_ms
                run.elapsed_ms = elapsed_ms
        mark_job_succeeded(db, job_id)

    return {
        "run_id": run_id,
        "job_id": job_id,
        "status": "completed",
        "summary": {
            "total": total,
            "success": success,
            "failed": failed,
            "avg_processing_ms": avg_processing_ms,
            "elapsed_ms": elapsed_ms,
        },
    }
