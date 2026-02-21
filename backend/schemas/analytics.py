from __future__ import annotations

from pydantic import BaseModel


class AnalyticsSummaryResponse(BaseModel):
    ticket_types_by_city: list[dict]
    tickets_by_office: list[dict]
    sentiment_distribution: list[dict]
    avg_priority_by_office: list[dict]
    avg_priority_by_city: list[dict]
    workload_by_manager: list[dict]
