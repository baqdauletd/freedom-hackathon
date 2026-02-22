from __future__ import annotations

from typing import Any

from backend.celery_app import celery_app
from backend.core.config import get_settings
from backend.db.models import Ticket
from backend.db.session import SessionLocal
from backend.services.ai_enrichment import AIEnrichmentService
from backend.services.queue import bump_retry_with_jitter, update_ticket_progress
from backend.tasks.common import ai_result_to_payload, ticket_record_to_row


@celery_app.task(bind=True, name="backend.tasks.ai.ai_enrich_ticket", max_retries=3)
def ai_enrich_ticket(self, context: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    ticket_id = int(context["ticket_id"])
    run_id = str(context["run_id"])
    job_id = str(context["job_id"])

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            raise ValueError(f"Ticket not found: {ticket_id}")
        update_ticket_progress(
            db,
            job_id=job_id,
            ticket_id=ticket_id,
            stage="ai",
            status="running",
            retries=int(self.request.retries or 0),
        )
        ticket_row = ticket_record_to_row(ticket)

    try:
        result = AIEnrichmentService(settings).analyze(ticket_row, raise_on_error=True)
        payload = dict(context)
        payload["run_id"] = run_id
        payload["ai_result"] = ai_result_to_payload(result)
        with SessionLocal() as db:
            update_ticket_progress(
                db,
                job_id=job_id,
                ticket_id=ticket_id,
                stage="ai",
                status="done",
                retries=int(self.request.retries or 0),
            )
        return payload
    except Exception as exc:
        retries = int(self.request.retries or 0)
        with SessionLocal() as db:
            update_ticket_progress(
                db,
                job_id=job_id,
                ticket_id=ticket_id,
                stage="ai",
                status="retry_wait" if retries < int(self.max_retries or 0) else "failed",
                error_message=str(exc),
                retries=retries,
            )
        if retries < int(self.max_retries or 0):
            countdown = bump_retry_with_jitter(
                settings.worker_retry_base_seconds,
                settings.worker_retry_max_seconds,
                retries,
            )
            raise self.retry(exc=exc, countdown=countdown)
        raise
