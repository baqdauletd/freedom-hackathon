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
    assigned_manager: str | None
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
