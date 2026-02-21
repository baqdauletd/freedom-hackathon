from __future__ import annotations

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


class AssistantQueryResponse(BaseModel):
    answer: str
    intent: str
    chart_type: str
    suggested_title: str
    data: dict
    table: list[dict]
    chart: str | None = None
    sql: str | None = None
    chartConfig: dict | None = None
