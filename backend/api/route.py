from __future__ import annotations

from datetime import datetime, time as dtime
import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Header, Query, UploadFile
from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.models import AIAnalysis, Assignment, BusinessUnit, Manager, ProcessingJob, ProcessingRun, Ticket
from backend.db.session import get_db
from backend.schemas.tickets import (
    BatchResponse,
    JobStatusResponse,
    ProcessSingleTicketRequest,
    ProcessedTicketResponse,
    QueuedRunResponse,
    RunStatusResponse,
    RoutingRunResponse,
)
from backend.services.ingestion import (
    CSVValidationError,
    parse_csv_bytes,
    parse_csv_path,
    validate_business_units,
    validate_managers,
    validate_tickets,
)
from backend.services.processing import process_tickets
from backend.services.queue import enqueue_processing_job

router = APIRouter(tags=["routing"])
LOGGER = logging.getLogger("fire.ingestion")


def _bad_request(error: CSVValidationError) -> HTTPException:
    LOGGER.warning("csv_validation_failed", extra={"dataset": error.dataset, "error_message": error.message})
    return HTTPException(status_code=400, detail=error.message)


def _parse_date(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if "T" not in value and " " not in value:
        return datetime.combine(parsed.date(), dtime.max if end_of_day else dtime.min)
    return parsed


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _job_status_payload(job: ProcessingJob, *, reused: bool = False) -> dict:
    return {
        "job_id": job.id,
        "run_id": job.run_id,
        "status": job.status,
        "idempotency_key": job.idempotency_key,
        "attempt_count": int(job.attempt_count or 0),
        "max_attempts": int(job.max_attempts or 0),
        "next_attempt_at": _iso(job.next_attempt_at),
        "locked_at": _iso(job.locked_at),
        "locked_by": job.locked_by,
        "last_error": job.last_error,
        "created_at": _iso(job.created_at),
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "idempotency_reused": reused,
    }


def _to_result_item(
    ticket: Ticket,
    analysis: AIAnalysis | None,
    assignment: Assignment | None,
    office: BusinessUnit | None,
    manager: Manager | None,
) -> dict:
    trace_warnings: list[str] = []
    if assignment and assignment.decision_trace and isinstance(assignment.decision_trace, dict):
        raw = assignment.decision_trace.get("warnings")
        if isinstance(raw, list):
            trace_warnings = [str(item) for item in raw if str(item).strip()]

    return {
        "id": ticket.id,
        "run_id": ticket.run_id,
        "ticket_id": ticket.external_id or ticket.id,
        "ticket_index": ticket.id,
        "ticket_type": analysis.ticket_type if analysis else "Unknown",
        "sentiment": analysis.tone if analysis else "Unknown",
        "priority": analysis.priority if analysis else 0,
        "language": analysis.language if analysis else "RU",
        "summary": analysis.summary if analysis else "",
        "recommendation": analysis.recommendation if analysis else "",
        "office": office.office if office else "",
        "selected_managers": assignment.selected_pair_snapshot if assignment else [],
        "manager_id": manager.id if manager else None,
        "assigned_manager": manager.full_name if manager else None,
        "assignment_status": assignment.assignment_status if assignment else "unassigned",
        "unassigned_reason": assignment.unassigned_reason if assignment else "no_assignment",
        "warnings": trace_warnings,
        "ticket_lat": analysis.ticket_lat if analysis else None,
        "ticket_lon": analysis.ticket_lon if analysis else None,
        "office_lat": office.latitude if office else None,
        "office_lon": office.longitude if office else None,
        "processing_ms": analysis.processing_ms if analysis else None,
        "segment": ticket.segment,
        "city": ticket.city,
        "description": ticket.description,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "rr_turn": assignment.rr_turn if assignment else None,
        "decision_trace": assignment.decision_trace if assignment else None,
    }


@router.post("/route", response_model=list[ProcessedTicketResponse])
def route_from_paths(db: Session = Depends(get_db)) -> list[dict]:
    settings = get_settings()

    try:
        tickets = validate_tickets(parse_csv_path(settings.tickets_csv_path))
        managers = validate_managers(parse_csv_path(settings.managers_csv_path))
        business_units = validate_business_units(parse_csv_path(settings.business_units_csv_path))
    except CSVValidationError as exc:
        raise _bad_request(exc) from exc

    envelope = process_tickets(
        db,
        settings,
        tickets,
        managers,
        business_units,
        source_filenames={
            "tickets": settings.tickets_csv_path,
            "managers": settings.managers_csv_path,
            "business_units": settings.business_units_csv_path,
        },
    )
    return envelope["results"]


@router.post("/route/upload", response_model=RoutingRunResponse | list[ProcessedTicketResponse])
async def route_upload(
    tickets: UploadFile = File(...),
    managers: UploadFile = File(...),
    business_units: UploadFile = File(...),
    legacy: bool = Query(default=False, description="Return legacy list response"),
    db: Session = Depends(get_db),
) -> dict | list[dict]:
    try:
        tickets_rows = validate_tickets(parse_csv_bytes(await tickets.read()))
        managers_rows = validate_managers(parse_csv_bytes(await managers.read()))
        business_rows = validate_business_units(parse_csv_bytes(await business_units.read()))
    except CSVValidationError as exc:
        raise _bad_request(exc) from exc

    envelope = process_tickets(
        db,
        get_settings(),
        tickets_rows,
        managers_rows,
        business_rows,
        source_filenames={
            "tickets": tickets.filename or "tickets.csv",
            "managers": managers.filename or "managers.csv",
            "business_units": business_units.filename or "business_units.csv",
        },
    )
    if legacy:
        return envelope["results"]
    return envelope


@router.post("/route/upload/async", response_model=QueuedRunResponse)
async def route_upload_async(
    tickets: UploadFile = File(...),
    managers: UploadFile = File(...),
    business_units: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        tickets_rows = validate_tickets(parse_csv_bytes(await tickets.read()))
        managers_rows = validate_managers(parse_csv_bytes(await managers.read()))
        business_rows = validate_business_units(parse_csv_bytes(await business_units.read()))
    except CSVValidationError as exc:
        raise _bad_request(exc) from exc

    enqueue = enqueue_processing_job(
        db,
        get_settings(),
        tickets=tickets_rows,
        managers=managers_rows,
        business_units=business_rows,
        source_filenames={
            "tickets": tickets.filename or "tickets.csv",
            "managers": managers.filename or "managers.csv",
            "business_units": business_units.filename or "business_units.csv",
        },
        idempotency_key=idempotency_key,
    )
    run = db.get(ProcessingRun, enqueue.job.run_id)
    if not run:
        raise HTTPException(status_code=500, detail="Run creation failed")

    return {
        "run_id": run.id,
        "run_status": run.status,
        "job": _job_status_payload(enqueue.job, reused=enqueue.reused),
    }


@router.post("/tickets/process", response_model=ProcessedTicketResponse)
def process_single_ticket(payload: ProcessSingleTicketRequest, db: Session = Depends(get_db)) -> dict:
    try:
        tickets = validate_tickets(parse_csv_bytes(_dicts_to_csv_bytes(payload.ticket, "tickets")))
        managers = validate_managers(parse_csv_bytes(_dicts_to_csv_bytes(payload.managers, "managers")))
        business_units = validate_business_units(parse_csv_bytes(_dicts_to_csv_bytes(payload.business_units, "business_units")))
    except CSVValidationError as exc:
        raise _bad_request(exc) from exc

    envelope = process_tickets(db, get_settings(), tickets[:1], managers, business_units)
    return envelope["results"][0]


@router.post("/tickets/batch", response_model=BatchResponse)
async def process_ticket_batch(
    tickets: UploadFile = File(...),
    managers: UploadFile = File(...),
    business_units: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> BatchResponse:
    try:
        tickets_rows = validate_tickets(parse_csv_bytes(await tickets.read()))
        managers_rows = validate_managers(parse_csv_bytes(await managers.read()))
        business_rows = validate_business_units(parse_csv_bytes(await business_units.read()))
    except CSVValidationError as exc:
        raise _bad_request(exc) from exc

    envelope = process_tickets(
        db,
        get_settings(),
        tickets_rows,
        managers_rows,
        business_rows,
        source_filenames={
            "tickets": tickets.filename or "tickets.csv",
            "managers": managers.filename or "managers.csv",
            "business_units": business_units.filename or "business_units.csv",
        },
    )
    return BatchResponse(run_id=envelope["run_id"], summary=envelope["summary"], results=envelope["results"])


@router.post("/tickets/batch/async", response_model=QueuedRunResponse)
async def process_ticket_batch_async(
    tickets: UploadFile = File(...),
    managers: UploadFile = File(...),
    business_units: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        tickets_rows = validate_tickets(parse_csv_bytes(await tickets.read()))
        managers_rows = validate_managers(parse_csv_bytes(await managers.read()))
        business_rows = validate_business_units(parse_csv_bytes(await business_units.read()))
    except CSVValidationError as exc:
        raise _bad_request(exc) from exc

    enqueue = enqueue_processing_job(
        db,
        get_settings(),
        tickets=tickets_rows,
        managers=managers_rows,
        business_units=business_rows,
        source_filenames={
            "tickets": tickets.filename or "tickets.csv",
            "managers": managers.filename or "managers.csv",
            "business_units": business_units.filename or "business_units.csv",
        },
        idempotency_key=idempotency_key,
    )
    run = db.get(ProcessingRun, enqueue.job.run_id)
    if not run:
        raise HTTPException(status_code=500, detail="Run creation failed")

    return {
        "run_id": run.id,
        "run_status": run.status,
        "job": _job_status_payload(enqueue.job, reused=enqueue.reused),
    }


@router.get("/runs/{run_id}/status", response_model=RunStatusResponse)
def get_run_status(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = db.get(ProcessingRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    job = db.execute(select(ProcessingJob).where(ProcessingJob.run_id == run_id)).scalar_one_or_none()

    return {
        "run_id": run.id,
        "status": run.status,
        "summary": {
            "total": int(run.tickets_total or 0),
            "success": int(run.tickets_success or 0),
            "failed": int(run.tickets_failed or 0),
            "avg_processing_ms": int(run.avg_processing_ms or 0),
            "elapsed_ms": int(run.elapsed_ms or 0),
        },
        "job": _job_status_payload(job) if job else None,
    }


@router.get("/runs")
def list_runs(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    statement = select(ProcessingRun)
    if status:
        statement = statement.where(ProcessingRun.status == status)
    statement = statement.order_by(desc(ProcessingRun.created_at), desc(ProcessingRun.id))

    total_statement = select(func.count()).select_from(statement.subquery())
    total = int(db.execute(total_statement).scalar_one() or 0)

    rows = db.execute(statement.limit(limit).offset(offset)).scalars().all()
    items = [
        {
            "run_id": row.id,
            "status": row.status,
            "created_at": _iso(row.created_at),
            "summary": {
                "total": int(row.tickets_total or 0),
                "success": int(row.tickets_success or 0),
                "failed": int(row.tickets_failed or 0),
                "avg_processing_ms": int(row.avg_processing_ms or 0),
                "elapsed_ms": int(row.elapsed_ms or 0),
            },
            "source_files": {
                "tickets": row.tickets_filename,
                "managers": row.managers_filename,
                "business_units": row.business_units_filename,
            },
        }
        for row in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)) -> dict:
    job = db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_status_payload(job)


@router.get("/results")
def get_results(
    run_id: str | None = None,
    office: str | None = None,
    office_id: int | None = Query(default=None),
    city: str | None = None,
    type: str | None = Query(default=None, alias="type"),
    tone: str | None = None,
    language: str | None = None,
    manager_id: int | None = Query(default=None),
    manager: str | None = None,
    segment: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    sort_by: Literal["priority", "processing_ms", "created_at"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to, end_of_day=True)

    statement = (
        select(Ticket, AIAnalysis, Assignment, BusinessUnit, Manager)
        .outerjoin(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
        .outerjoin(Assignment, Assignment.ticket_id == Ticket.id)
        .outerjoin(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        .outerjoin(Manager, Manager.id == Assignment.manager_id)
    )

    filters = []
    if run_id:
        filters.append(Ticket.run_id == run_id)
    if office:
        filters.append(BusinessUnit.office == office)
    if office_id:
        filters.append(BusinessUnit.id == office_id)
    if city:
        filters.append(Ticket.city == city)
    if type:
        filters.append(AIAnalysis.ticket_type == type)
    if tone:
        filters.append(AIAnalysis.tone == tone)
    if language:
        filters.append(AIAnalysis.language == language)
    if manager_id is not None:
        filters.append(Manager.id == manager_id)
    if manager:
        filters.append(Manager.full_name == manager)
    if segment:
        filters.append(Ticket.segment == segment)
    if parsed_from:
        filters.append(Assignment.assigned_at >= parsed_from)
    if parsed_to:
        filters.append(Assignment.assigned_at <= parsed_to)
    if search:
        needle = f"%{search.lower()}%"
        filters.append(or_(func.lower(Ticket.external_id).like(needle), func.lower(Ticket.description).like(needle)))

    if filters:
        statement = statement.where(and_(*filters))

    sort_map = {
        "priority": AIAnalysis.priority,
        "processing_ms": AIAnalysis.processing_ms,
        "created_at": Ticket.created_at,
    }
    order_column = sort_map[sort_by]
    order_clause = asc(order_column) if sort_order == "asc" else desc(order_column)
    statement = statement.order_by(order_clause, desc(Ticket.id))

    total_statement = select(func.count()).select_from(statement.subquery())
    total = int(db.execute(total_statement).scalar_one() or 0)

    rows = db.execute(statement.limit(limit).offset(offset)).all()
    items = [_to_result_item(ticket, analysis, assignment, office_row, manager_row) for ticket, analysis, assignment, office_row, manager_row in rows]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/tickets/{ticket_id}")
def get_ticket_details(ticket_id: str, db: Session = Depends(get_db)) -> dict:
    statement = (
        select(Ticket, AIAnalysis, Assignment, BusinessUnit, Manager)
        .outerjoin(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
        .outerjoin(Assignment, Assignment.ticket_id == Ticket.id)
        .outerjoin(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        .outerjoin(Manager, Manager.id == Assignment.manager_id)
        .order_by(desc(Ticket.created_at))
    )

    if ticket_id.isdigit():
        statement = statement.where(or_(Ticket.id == int(ticket_id), Ticket.external_id == ticket_id))
    else:
        statement = statement.where(Ticket.external_id == ticket_id)

    row = db.execute(statement).first()
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket, analysis, assignment, office, manager = row

    return {
        "id": ticket.id,
        "run_id": ticket.run_id,
        "ticket": {
            "external_id": ticket.external_id,
            "segment": ticket.segment,
            "description": ticket.description,
            "country": ticket.country,
            "region": ticket.region,
            "city": ticket.city,
            "street": ticket.street,
            "house": ticket.house,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        },
        "ai_analysis": {
            "ticket_type": analysis.ticket_type,
            "tone": analysis.tone,
            "priority": analysis.priority,
            "language": analysis.language,
            "summary": analysis.summary,
            "recommendation": analysis.recommendation,
            "ticket_lat": analysis.ticket_lat,
            "ticket_lon": analysis.ticket_lon,
            "processing_ms": analysis.processing_ms,
        }
        if analysis
        else None,
        "assignment": {
            "office": office.office if office else "",
            "office_lat": office.latitude if office else None,
            "office_lon": office.longitude if office else None,
            "manager_id": manager.id if manager else None,
            "assigned_manager": manager.full_name if manager else None,
            "assignment_status": assignment.assignment_status if assignment else "unassigned",
            "unassigned_reason": assignment.unassigned_reason if assignment else "no_assignment",
            "selected_managers": assignment.selected_pair_snapshot if assignment else [],
            "rr_turn": assignment.rr_turn if assignment else 0,
            "decision_trace": assignment.decision_trace if assignment else None,
            "warnings": (
                assignment.decision_trace.get("warnings", [])
                if assignment and isinstance(assignment.decision_trace, dict)
                else []
            ),
        }
        if assignment
        else None,
    }


@router.get("/managers")
def get_managers(
    run_id: str | None = None,
    office: str | None = None,
    office_id: int | None = Query(default=None),
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to, end_of_day=True)

    count_stmt = (
        select(
            Assignment.manager_id.label("manager_id"),
            func.count(Assignment.id).label("assigned_count"),
        )
        .join(Ticket, Ticket.id == Assignment.ticket_id)
        .group_by(Assignment.manager_id)
    )
    if run_id:
        count_stmt = count_stmt.where(Ticket.run_id == run_id)
    if parsed_from:
        count_stmt = count_stmt.where(Assignment.assigned_at >= parsed_from)
    if parsed_to:
        count_stmt = count_stmt.where(Assignment.assigned_at <= parsed_to)

    count_subquery = count_stmt.subquery()

    statement = (
        select(
            Manager.id,
            Manager.full_name,
            Manager.position,
            Manager.skills,
            Manager.current_load,
            BusinessUnit.office,
            func.coalesce(count_subquery.c.assigned_count, 0).label("assigned_count"),
        )
        .join(BusinessUnit, BusinessUnit.id == Manager.office_id)
        .outerjoin(count_subquery, count_subquery.c.manager_id == Manager.id)
        .order_by(desc(Manager.current_load), Manager.full_name)
    )

    if office:
        statement = statement.where(BusinessUnit.office == office)
    if office_id:
        statement = statement.where(BusinessUnit.id == office_id)

    rows = db.execute(statement).all()
    items = [
        {
            "id": manager_id,
            "full_name": full_name,
            "position": position,
            "skills": skills or [],
            "current_load": int(current_load or 0),
            "office": office_name,
            "assigned_count": int(assigned_count_value or 0),
        }
        for manager_id, full_name, position, skills, current_load, office_name, assigned_count_value in rows
    ]
    return {"items": items}


def _dicts_to_csv_bytes(data: dict | list[dict], dataset: str) -> bytes:
    import csv
    import io

    rows = [data] if isinstance(data, dict) else data
    if not rows:
        raise CSVValidationError(dataset, "No rows provided")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")
