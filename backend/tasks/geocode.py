from __future__ import annotations

from typing import Any

from sqlalchemy import select

from backend.celery_app import celery_app
from backend.core.config import get_settings
from backend.db.models import BusinessUnit, Ticket
from backend.db.session import SessionLocal
from backend.services.geocoding import GeocodingService
from backend.services.queue import bump_retry_with_jitter, update_ticket_progress
from backend.services.routing import choose_office
from backend.tasks.common import office_decision_to_payload, ticket_record_to_row


def _offices_payload(db) -> list[dict[str, Any]]:
    return [
        {"office": row.office, "latitude": row.latitude, "longitude": row.longitude}
        for row in db.execute(select(BusinessUnit)).scalars().all()
    ]


@celery_app.task(bind=True, name="backend.tasks.geocode.geocode_ticket", max_retries=3)
def geocode_ticket(self, context: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    ticket_id = int(context["ticket_id"])
    job_id = str(context["job_id"])
    ticket_index = int(context.get("ticket_index") or 0)

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            raise ValueError(f"Ticket not found: {ticket_id}")
        ticket_row = ticket_record_to_row(ticket)
        offices = _offices_payload(db)
        update_ticket_progress(
            db,
            job_id=job_id,
            ticket_id=ticket_id,
            stage="geocode",
            status="running",
            retries=int(self.request.retries or 0),
        )

    geocoder = GeocodingService(settings)
    try:
        decision = choose_office(
            ticket=ticket_row,
            offices=offices,
            geocoder=geocoder,
            ticket_index=ticket_index,
            compliance_mode=settings.fire_compliance_mode,
            enable_geocode=settings.enable_geocode,
            geocode_raise_on_error=True,
        )
    except Exception as exc:
        retries = int(self.request.retries or 0)
        with SessionLocal() as db:
            update_ticket_progress(
                db,
                job_id=job_id,
                ticket_id=ticket_id,
                stage="geocode",
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

        # Graceful fallback for persistent geocode failure (spec fallback path).
        decision = choose_office(
            ticket=ticket_row,
            offices=offices,
            geocoder=geocoder,
            ticket_index=ticket_index,
            compliance_mode=settings.fire_compliance_mode,
            enable_geocode=settings.enable_geocode,
        )

    with SessionLocal() as db:
        update_ticket_progress(
            db,
            job_id=job_id,
            ticket_id=ticket_id,
            stage="geocode",
            status="done",
            retries=int(self.request.retries or 0),
        )

    payload = dict(context)
    payload["office_decision"] = office_decision_to_payload(decision)
    return payload
