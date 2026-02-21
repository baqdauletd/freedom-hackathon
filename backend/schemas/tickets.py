from __future__ import annotations

from pydantic import BaseModel


class ProcessSingleTicketRequest(BaseModel):
    ticket: dict
    managers: list[dict]
    business_units: list[dict]


class ProcessedTicketResponse(BaseModel):
    id: int | None = None
    run_id: str | None = None
    ticket_id: str | int
    ticket_index: int
    ticket_type: str
    sentiment: str
    priority: int
    language: str
    summary: str
    recommendation: str
    office: str
    selected_managers: list[str]
    manager_id: int | None = None
    assigned_manager: str | None
    assignment_status: str | None = None
    unassigned_reason: str | None = None
    warnings: list[str] = []
    ticket_lat: float | None = None
    ticket_lon: float | None = None
    office_lat: float | None = None
    office_lon: float | None = None
    processing_ms: int
    segment: str | None = None
    city: str | None = None
    description: str | None = None
    created_at: str | None = None
    rr_turn: int | None = None
    decision_trace: dict | None = None


class RunSummaryResponse(BaseModel):
    total: int
    success: int
    failed: int
    avg_processing_ms: int
    elapsed_ms: int


class RoutingRunResponse(BaseModel):
    run_id: str
    summary: RunSummaryResponse
    results: list[ProcessedTicketResponse]


class BatchResponse(BaseModel):
    run_id: str | None = None
    summary: RunSummaryResponse | None = None
    results: list[ProcessedTicketResponse]


class JobStatusResponse(BaseModel):
    job_id: str
    run_id: str
    status: str
    idempotency_key: str | None = None
    attempt_count: int
    max_attempts: int
    next_attempt_at: str | None = None
    locked_at: str | None = None
    locked_by: str | None = None
    last_error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    idempotency_reused: bool = False


class QueuedRunResponse(BaseModel):
    run_id: str
    run_status: str
    job: JobStatusResponse


class RunStatusResponse(BaseModel):
    run_id: str
    status: str
    summary: RunSummaryResponse
    job: JobStatusResponse | None = None
