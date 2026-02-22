from __future__ import annotations

import time
from typing import Any

from backend.celery_app import celery_app
from backend.services.queue import update_ticket_progress
from backend.tasks.ai import ai_enrich_ticket
from backend.tasks.geocode import geocode_ticket
from backend.tasks.routing import route_and_assign_ticket


@celery_app.task(bind=True, name="backend.tasks.ticket.process_ticket")
def process_ticket(
    self,
    *,
    ticket_id: int,
    run_id: str,
    job_id: str,
    ticket_index: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    context: dict[str, Any] = {
        "ticket_id": int(ticket_id),
        "run_id": run_id,
        "job_id": job_id,
        "ticket_index": int(ticket_index),
    }

    try:
        ai_payload = ai_enrich_ticket.apply_async(args=[context], queue="ai").get(disable_sync_subtasks=False)
        geocode_payload = geocode_ticket.apply_async(args=[ai_payload], queue="geocode").get(disable_sync_subtasks=False)
        geocode_payload["processing_ms"] = int((time.perf_counter() - started) * 1000)
        result = route_and_assign_ticket.apply_async(args=[geocode_payload], queue="routing").get(
            disable_sync_subtasks=False
        )
        result["processing_ms"] = int((time.perf_counter() - started) * 1000)
        return result
    except Exception as exc:
        # Final failure after stage-level retries.
        from backend.db.session import SessionLocal

        with SessionLocal() as db:
            update_ticket_progress(
                db,
                job_id=job_id,
                ticket_id=int(ticket_id),
                stage="failed",
                status="failed",
                error_message=str(exc),
            )

        return {
            "id": int(ticket_id),
            "run_id": run_id,
            "ticket_id": int(ticket_id),
            "ticket_index": int(ticket_index),
            "ticket_type": "Unknown",
            "sentiment": "Unknown",
            "priority": 0,
            "language": "RU",
            "summary": "",
            "recommendation": "",
            "office": "",
            "selected_managers": [],
            "manager_id": None,
            "assigned_manager": None,
            "assignment_status": "unassigned",
            "unassigned_reason": "processing_failed",
            "warnings": [f"processing_failed:{exc}"],
            "ticket_lat": None,
            "ticket_lon": None,
            "office_lat": None,
            "office_lon": None,
            "processing_ms": int((time.perf_counter() - started) * 1000),
            "segment": None,
            "city": None,
            "description": None,
            "created_at": None,
            "rr_turn": None,
            "decision_trace": None,
        }
