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
    "office_distribution",
    "manager_workload",
    "ticket_type_distribution",
    "sentiment_distribution",
    "language_distribution",
    "avg_priority_by_office",
    "vip_priority_breakdown",
    "unassigned_rate_and_reasons",
    "processing_time_stats",
    "trend_over_time",
    "top_entities",
    "cross_tab_type_by_office",
    "cross_tab_sentiment_by_office",
    "workload_by_manager",
    "custom_filtered_summary",
]

AllowedChartType = Literal["bar", "line", "pie", "donut", "table", "empty"]


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


class AssistantScopeApplied(BaseModel):
    run_id: str | None = None
    office: str | None = None
    date_from: str | None = None
    date_to: str | None = None


class AssistantClarificationOption(BaseModel):
    intent: AllowedIntent
    label: str
    query_hint: str


class AssistantQueryResponse(BaseModel):
    kind: Literal["result"] = "result"
    intent: AllowedIntent
    title: str
    chart_type: AllowedChartType
    data: dict
    table: list[dict]
    explanation: str
    filters: AssistantFilters = Field(default_factory=AssistantFilters)
    computed_from: str | None = None
    scope_applied: AssistantScopeApplied = Field(default_factory=AssistantScopeApplied)
    warnings: list[str] = Field(default_factory=list)
    used_fallback: bool = False
    cache_hit: bool = False


class AssistantClarificationResponse(BaseModel):
    kind: Literal["clarification"] = "clarification"
    title: str = "Clarify your request"
    explanation: str
    options: list[AssistantClarificationOption]
    filters: AssistantFilters = Field(default_factory=AssistantFilters)
    scope_applied: AssistantScopeApplied = Field(default_factory=AssistantScopeApplied)
    warnings: list[str] = Field(default_factory=list)


AssistantResponse = AssistantQueryResponse | AssistantClarificationResponse
