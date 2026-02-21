from __future__ import annotations

import logging
import time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.db.models import AIAnalysis, BusinessUnit, ProcessingRun, Ticket
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
    run_id: str | None = None,
) -> dict:
    started_all = time.perf_counter()
    geocoder = GeocodingService(settings)
    ai_service = AIEnrichmentService(settings)
    total_expected = len(tickets)

    with db.begin():
        if run_id is None:
            run = ProcessingRun(
                status="processing",
                tickets_total=total_expected,
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
            run_id = run.id
        else:
            run = db.get(ProcessingRun, run_id)
            if run is None:
                raise ValueError(f"ProcessingRun not found: {run_id}")

            db.execute(delete(Ticket).where(Ticket.run_id == run_id))
            run.status = "processing"
            run.tickets_total = total_expected
            run.tickets_success = 0
            run.tickets_failed = 0
            run.avg_processing_ms = 0
            run.elapsed_ms = 0
            if source_filenames:
                run.tickets_filename = source_filenames.get("tickets") or run.tickets_filename
                run.managers_filename = source_filenames.get("managers") or run.managers_filename
                run.business_units_filename = source_filenames.get("business_units") or run.business_units_filename

        offices = upsert_business_units(db, business_units, geocoder)
        offices_by_name = {office.office: office for office in offices}
        upsert_managers(db, managers, offices_by_name)
        offices_payload = [
            {"office": office.office, "latitude": office.latitude, "longitude": office.longitude}
            for office in db.execute(select(BusinessUnit)).scalars().all()
        ]

    results: list[dict] = []
    success_count = 0
    failed_count = 0
    total_processing_ms = 0

    try:
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
            total_processing_ms += int(result.get("processing_ms") or 0)
            if result.get("assigned_manager"):
                success_count += 1
            else:
                failed_count += 1

            with db.begin():
                run_record = db.get(ProcessingRun, run_id)
                if run_record:
                    processed = success_count + failed_count
                    run_record.status = "processing"
                    run_record.tickets_total = total_expected
                    run_record.tickets_success = success_count
                    run_record.tickets_failed = failed_count
                    run_record.avg_processing_ms = round(total_processing_ms / processed) if processed else 0
                    run_record.elapsed_ms = int((time.perf_counter() - started_all) * 1000)
    except Exception:
        with db.begin():
            run_record = db.get(ProcessingRun, run_id)
            if run_record:
                run_record.status = "failed"
                run_record.tickets_total = total_expected
                run_record.tickets_success = success_count
                run_record.tickets_failed = max(total_expected - success_count, failed_count)
                processed = success_count + failed_count
                run_record.avg_processing_ms = round(total_processing_ms / processed) if processed else 0
                run_record.elapsed_ms = int((time.perf_counter() - started_all) * 1000)
        raise

    total = len(results)
    success = success_count
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
