from __future__ import annotations

from typing import Any

from sqlalchemy.exc import DBAPIError, OperationalError

from backend.celery_app import celery_app
from backend.core.config import get_settings
from backend.db.models import Ticket
from backend.db.session import SessionLocal
from backend.services.assignment import assign_ticket
from backend.services.queue import bump_retry_with_jitter, update_ticket_progress
from backend.tasks.common import ai_result_from_payload, office_decision_from_payload


def _is_deadlock_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "deadlock" in text or "could not serialize access" in text


@celery_app.task(bind=True, name="backend.tasks.routing.route_and_assign_ticket", max_retries=2)
def route_and_assign_ticket(self, context: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    ticket_id = int(context["ticket_id"])
    job_id = str(context["job_id"])
    ticket_index = int(context.get("ticket_index") or 0)
    processing_ms = int(context.get("processing_ms") or 0)

    ai_result = ai_result_from_payload(context["ai_result"])
    office_decision = office_decision_from_payload(context["office_decision"])

    with SessionLocal() as db:
        update_ticket_progress(
            db,
            job_id=job_id,
            ticket_id=ticket_id,
            stage="routing",
            status="running",
            retries=int(self.request.retries or 0),
        )

    try:
        with SessionLocal() as db:
            with db.begin():
                ticket = db.get(Ticket, ticket_id)
                if ticket is None:
                    raise ValueError(f"Ticket not found: {ticket_id}")
                result = assign_ticket(
                    db=db,
                    ticket_record=ticket,
                    ai_result=ai_result,
                    office_decision=office_decision,
                    ticket_index=ticket_index,
                    processing_ms=processing_ms,
                )
            update_ticket_progress(
                db,
                job_id=job_id,
                ticket_id=ticket_id,
                stage="done",
                status="done",
                retries=int(self.request.retries or 0),
            )
        return result
    except (OperationalError, DBAPIError) as exc:
        retries = int(self.request.retries or 0)
        should_retry = _is_deadlock_error(exc) and retries < int(self.max_retries or 0)
        with SessionLocal() as db:
            update_ticket_progress(
                db,
                job_id=job_id,
                ticket_id=ticket_id,
                stage="routing",
                status="retry_wait" if should_retry else "failed",
                error_message=str(exc),
                retries=retries,
            )
        if should_retry:
            countdown = bump_retry_with_jitter(
                settings.worker_retry_base_seconds,
                settings.worker_retry_max_seconds,
                retries,
            )
            raise self.retry(exc=exc, countdown=countdown)
        raise
