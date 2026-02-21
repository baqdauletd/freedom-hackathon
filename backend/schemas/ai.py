from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AIResult(BaseModel):
    ticket_type: str
    tone: str
    priority: int = Field(ge=1, le=10)
    language: str
    summary: str
    recommendation: str


class AssistantQueryRequest(BaseModel):
    query: str | None = None
    prompt: str | None = None
    run_id: str | None = None
    office: str | None = None
    date_from: str | None = None
    date_to: str | None = None


AllowedIntent = Literal[
    "average_age_by_office",
    "ticket_count_by_city",
    "ticket_type_distribution",
    "sentiment_distribution",
    "avg_priority_by_office",
    "workload_by_manager",
    "custom_filtered_summary",
]

AllowedChartType = Literal["bar", "line", "pie", "table"]


class AssistantFilters(BaseModel):
    office_names: list[str] = Field(default_factory=list)
    office_ids: list[int] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None
    segment: Literal["Mass", "VIP", "Priority"] | None = None
    ticket_type: str | None = None
    language: Literal["KZ", "ENG", "RU"] | None = None
    run_id: str | None = None


class AssistantQueryResponse(BaseModel):
    intent: AllowedIntent
    title: str
    chart_type: AllowedChartType
    data: dict
    table: list[dict]
    explanation: str
    filters: AssistantFilters = Field(default_factory=AssistantFilters)
