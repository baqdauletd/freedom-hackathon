from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

try:
    from openai import OpenAI as OpenAIClient
except ModuleNotFoundError:  # pragma: no cover - optional in local tests
    OpenAIClient = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIType
else:  # pragma: no cover - typing fallback for missing package
    OpenAIType = Any
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.db.models import AIAnalysis, Assignment, BusinessUnit, Manager, Ticket


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _title_for_intent(intent: str) -> str:
    mapping = {
        "ticket_types_by_city": "Ticket types by city",
        "tickets_by_office": "Ticket distribution by office",
        "sentiment_distribution": "Sentiment distribution",
        "avg_priority_by_office": "Average priority by office",
        "avg_priority_by_city": "Average priority by city",
        "workload_by_manager": "Manager workload",
    }
    return mapping.get(intent, "Analytics result")


@dataclass
class AnalyticsService:
    settings: Settings

    def __post_init__(self) -> None:
        self.client: OpenAIType | None = None
        if self.settings.openai_api_key and OpenAIClient is not None:
            self.client = OpenAIClient(api_key=self.settings.openai_api_key, timeout=self.settings.openai_timeout_seconds)

    def get_summary(
        self,
        db: Session,
        *,
        run_id: str | None = None,
        office: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        parsed_from = _parse_date(date_from)
        parsed_to = _parse_date(date_to)

        ticket_types_stmt = (
            select(Ticket.city, AIAnalysis.ticket_type, func.count(Ticket.id))
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        tickets_by_office_stmt = (
            select(BusinessUnit.office, func.count(Assignment.id))
            .join(Assignment, Assignment.office_id == BusinessUnit.id)
            .join(Ticket, Ticket.id == Assignment.ticket_id)
        )
        sentiment_stmt = (
            select(AIAnalysis.tone, func.count(AIAnalysis.id))
            .join(Ticket, Ticket.id == AIAnalysis.ticket_id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        avg_priority_by_office_stmt = (
            select(BusinessUnit.office, func.avg(AIAnalysis.priority))
            .join(Assignment, Assignment.office_id == BusinessUnit.id)
            .join(AIAnalysis, AIAnalysis.ticket_id == Assignment.ticket_id)
            .join(Ticket, Ticket.id == Assignment.ticket_id)
        )
        avg_priority_by_city_stmt = (
            select(Ticket.city, func.avg(AIAnalysis.priority))
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        workload_stmt = (
            select(
                Manager.full_name,
                BusinessUnit.office,
                Manager.current_load,
                func.count(Assignment.id),
            )
            .join(BusinessUnit, BusinessUnit.id == Manager.office_id)
            .outerjoin(Assignment, Assignment.manager_id == Manager.id)
            .outerjoin(Ticket, Ticket.id == Assignment.ticket_id)
        )

        if run_id:
            ticket_types_stmt = ticket_types_stmt.where(Ticket.run_id == run_id)
            tickets_by_office_stmt = tickets_by_office_stmt.where(Ticket.run_id == run_id)
            sentiment_stmt = sentiment_stmt.where(Ticket.run_id == run_id)
            avg_priority_by_office_stmt = avg_priority_by_office_stmt.where(Ticket.run_id == run_id)
            avg_priority_by_city_stmt = avg_priority_by_city_stmt.where(Ticket.run_id == run_id)
            workload_stmt = workload_stmt.where((Ticket.run_id == run_id) | (Ticket.id.is_(None)))

        if office:
            ticket_types_stmt = ticket_types_stmt.where(BusinessUnit.office == office)
            tickets_by_office_stmt = tickets_by_office_stmt.where(BusinessUnit.office == office)
            sentiment_stmt = sentiment_stmt.where(BusinessUnit.office == office)
            avg_priority_by_office_stmt = avg_priority_by_office_stmt.where(BusinessUnit.office == office)
            avg_priority_by_city_stmt = avg_priority_by_city_stmt.where(BusinessUnit.office == office)
            workload_stmt = workload_stmt.where(BusinessUnit.office == office)

        if parsed_from:
            tickets_by_office_stmt = tickets_by_office_stmt.where(Assignment.assigned_at >= parsed_from)
            avg_priority_by_office_stmt = avg_priority_by_office_stmt.where(Assignment.assigned_at >= parsed_from)
            avg_priority_by_city_stmt = avg_priority_by_city_stmt.where(Assignment.assigned_at >= parsed_from)
            workload_stmt = workload_stmt.where((Assignment.assigned_at >= parsed_from) | (Assignment.id.is_(None)))
            ticket_types_stmt = ticket_types_stmt.where(Assignment.assigned_at >= parsed_from)
            sentiment_stmt = sentiment_stmt.where(Assignment.assigned_at >= parsed_from)

        if parsed_to:
            tickets_by_office_stmt = tickets_by_office_stmt.where(Assignment.assigned_at <= parsed_to)
            avg_priority_by_office_stmt = avg_priority_by_office_stmt.where(Assignment.assigned_at <= parsed_to)
            avg_priority_by_city_stmt = avg_priority_by_city_stmt.where(Assignment.assigned_at <= parsed_to)
            workload_stmt = workload_stmt.where((Assignment.assigned_at <= parsed_to) | (Assignment.id.is_(None)))
            ticket_types_stmt = ticket_types_stmt.where(Assignment.assigned_at <= parsed_to)
            sentiment_stmt = sentiment_stmt.where(Assignment.assigned_at <= parsed_to)

        ticket_types_by_city = (
            db.execute(ticket_types_stmt.group_by(Ticket.city, AIAnalysis.ticket_type).order_by(Ticket.city, AIAnalysis.ticket_type)).all()
        )
        tickets_by_office = (
            db.execute(tickets_by_office_stmt.group_by(BusinessUnit.office).order_by(BusinessUnit.office)).all()
        )
        sentiment_distribution = (
            db.execute(sentiment_stmt.group_by(AIAnalysis.tone).order_by(AIAnalysis.tone)).all()
        )
        avg_priority_by_office = (
            db.execute(
                avg_priority_by_office_stmt.group_by(BusinessUnit.office).order_by(BusinessUnit.office)
            ).all()
        )
        avg_priority_by_city = (
            db.execute(avg_priority_by_city_stmt.group_by(Ticket.city).order_by(Ticket.city)).all()
        )
        workload_by_manager = (
            db.execute(
                workload_stmt.group_by(Manager.full_name, BusinessUnit.office, Manager.current_load).order_by(Manager.full_name)
            ).all()
        )

        return {
            "ticket_types_by_city": [
                {"city": city or "Unknown", "ticket_type": ticket_type, "count": count}
                for city, ticket_type, count in ticket_types_by_city
            ],
            "tickets_by_office": [{"office": office_name, "count": count} for office_name, count in tickets_by_office],
            "sentiment_distribution": [{"tone": tone, "count": count} for tone, count in sentiment_distribution],
            "avg_priority_by_office": [
                {"office": office_name, "avg_priority": round(float(avg_priority or 0), 2)}
                for office_name, avg_priority in avg_priority_by_office
            ],
            "avg_priority_by_city": [
                {"city": city or "Unknown", "avg_priority": round(float(avg_priority or 0), 2)}
                for city, avg_priority in avg_priority_by_city
            ],
            "workload_by_manager": [
                {
                    "manager": manager_name,
                    "office": office_name,
                    "current_load": int(current_load or 0),
                    "assigned_count": int(assigned_count or 0),
                }
                for manager_name, office_name, current_load, assigned_count in workload_by_manager
            ],
        }

    def assistant_query(self, db: Session, query: str) -> dict:
        intent, chart = self._resolve_intent(query)
        summary = self.get_summary(db)

        intent_to_data = {
            "ticket_types_by_city": summary["ticket_types_by_city"],
            "tickets_by_office": summary["tickets_by_office"],
            "sentiment_distribution": summary["sentiment_distribution"],
            "avg_priority_by_office": summary["avg_priority_by_office"],
            "avg_priority_by_city": summary["avg_priority_by_city"],
            "workload_by_manager": summary["workload_by_manager"],
        }

        table = intent_to_data[intent]
        data = {"series": table}
        answer = f"Built report '{_title_for_intent(intent)}' based on your query."

        sql_map = {
            "ticket_types_by_city": "SELECT city, ticket_type, COUNT(*) FROM tickets JOIN ai_analysis ... GROUP BY city, ticket_type",
            "tickets_by_office": "SELECT office, COUNT(*) FROM assignments JOIN business_units ... GROUP BY office",
            "sentiment_distribution": "SELECT tone, COUNT(*) FROM ai_analysis GROUP BY tone",
            "avg_priority_by_office": "SELECT office, AVG(priority) FROM ... GROUP BY office",
            "avg_priority_by_city": "SELECT city, AVG(priority) FROM ... GROUP BY city",
            "workload_by_manager": "SELECT manager, current_load, COUNT(*) FROM managers LEFT JOIN assignments ... GROUP BY manager",
        }

        return {
            "answer": answer,
            "intent": intent,
            "chart_type": chart,
            "suggested_title": _title_for_intent(intent),
            "data": data,
            "table": table,
            "chart": chart,
            "sql": sql_map[intent],
            "chartConfig": {"type": chart, "x": list(data["series"][0].keys())[0] if data["series"] else "label"},
        }

    def _resolve_intent(self, query: str) -> tuple[str, str]:
        allowed_intents = {
            "ticket_types_by_city": "bar",
            "tickets_by_office": "bar",
            "sentiment_distribution": "pie",
            "avg_priority_by_office": "bar",
            "avg_priority_by_city": "line",
            "workload_by_manager": "bar",
        }

        if self.client:
            prompt = (
                "Determine analytics intent. Return JSON with keys intent and chart. "
                f"intent must be one of: {list(allowed_intents.keys())}. "
                "chart must be one of: bar, pie, line. "
                f"User query: {query!r}"
            )
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.openai_model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                payload = json.loads(response.choices[0].message.content or "{}")
                intent = payload.get("intent")
                chart = payload.get("chart")
                if intent in allowed_intents:
                    return intent, chart if chart in {"bar", "pie", "line"} else allowed_intents[intent]
            except Exception:
                pass

        q = query.lower()
        if "manager" in q or "нагруз" in q:
            return "workload_by_manager", "bar"
        if "город" in q or "city" in q:
            if "тип" in q or "type" in q:
                return "ticket_types_by_city", "bar"
            return "avg_priority_by_city", "line"
        if "офис" in q:
            if "сред" in q or "avg" in q:
                return "avg_priority_by_office", "bar"
            return "tickets_by_office", "bar"
        if "тон" in q or "sentiment" in q:
            return "sentiment_distribution", "pie"

        return "ticket_types_by_city", "bar"
