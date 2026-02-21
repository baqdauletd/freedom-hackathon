from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.db.models import AIAnalysis, BusinessUnit, ProcessingRun
from backend.services.ai_enrichment import AIEnrichmentService
from backend.services.assignment import assign_ticket, create_ticket_record, upsert_business_units, upsert_managers
from backend.services.geocoding import GeocodingService
from backend.services.routing import choose_office

LOGGER = logging.getLogger("fire.processing")


def process_tickets(
    db: Session,
    settings: Settings,
    tickets: list[dict[str, str]],
    managers: list[dict[str, str]],
    business_units: list[dict[str, str]],
    source_filenames: dict[str, str] | None = None,
) -> dict:
    started_all = time.perf_counter()
    geocoder = GeocodingService(settings)
    ai_service = AIEnrichmentService(settings)

    with db.begin():
        run = ProcessingRun(
            status="processing",
            tickets_filename=source_filenames.get("tickets") if source_filenames else None,
            managers_filename=source_filenames.get("managers") if source_filenames else None,
            business_units_filename=source_filenames.get("business_units") if source_filenames else None,
        )
        db.add(run)
        db.flush()

        offices = upsert_business_units(db, business_units, geocoder)
        offices_by_name = {office.office: office for office in offices}
        upsert_managers(db, managers, offices_by_name)
        offices_payload = [
            {"office": office.office, "latitude": office.latitude, "longitude": office.longitude}
            for office in db.execute(select(BusinessUnit)).scalars().all()
        ]

    run_id = run.id
    results: list[dict] = []

    for idx, ticket in enumerate(tickets):
        started = time.perf_counter()
        ai_result = ai_service.analyze(ticket)

        decision = choose_office(
            ticket=ticket,
            offices=offices_payload,
            geocoder=geocoder,
            ticket_index=idx,
            compliance_mode=settings.fire_compliance_mode,
            enable_geocode=settings.enable_geocode,
        )

        with db.begin():
            ticket_record = create_ticket_record(db, ticket, run_id=run_id)
            preliminary_ms = int((time.perf_counter() - started) * 1000)

            result = assign_ticket(
                db=db,
                ticket_record=ticket_record,
                ai_result=ai_result,
                office_decision=decision,
                ticket_index=idx,
                processing_ms=preliminary_ms,
            )

            final_ms = int((time.perf_counter() - started) * 1000)
            analysis = db.execute(select(AIAnalysis).where(AIAnalysis.ticket_id == ticket_record.id)).scalar_one_or_none()
            if analysis:
                analysis.processing_ms = final_ms
            result["processing_ms"] = final_ms

        if result["processing_ms"] > settings.per_ticket_budget_ms:
            LOGGER.warning(
                "ticket_processing_budget_exceeded",
                extra={
                    "ticket_id": result["ticket_id"],
                    "processing_ms": result["processing_ms"],
                    "budget_ms": settings.per_ticket_budget_ms,
                },
            )

        results.append(result)

    total = len(results)
    success = sum(1 for row in results if row.get("assigned_manager"))
    failed = total - success
    avg_processing_ms = round(sum(int(row.get("processing_ms") or 0) for row in results) / total) if total else 0
    elapsed_ms = int((time.perf_counter() - started_all) * 1000)

    with db.begin():
        run_record = db.get(ProcessingRun, run_id)
        if run_record:
            run_record.status = "completed"
            run_record.tickets_total = total
            run_record.tickets_success = success
            run_record.tickets_failed = failed
            run_record.avg_processing_ms = avg_processing_ms
            run_record.elapsed_ms = elapsed_ms

    return {
        "run_id": run_id,
        "summary": {
            "total": total,
            "success": success,
            "failed": failed,
            "avg_processing_ms": avg_processing_ms,
            "elapsed_ms": elapsed_ms,
        },
        "results": results,
    }
