from __future__ import annotations

import json
import logging
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from threading import Lock
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.db.models import AIAnalysis, Assignment, BusinessUnit, Manager, Ticket
from backend.schemas.ai import AssistantFilters

try:
    from openai import OpenAI as OpenAIClient
except ModuleNotFoundError:  # pragma: no cover - optional in local tests
    OpenAIClient = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIType
else:  # pragma: no cover - typing fallback for missing package
    OpenAIType = Any

LOGGER = logging.getLogger("fire.assistant")

ALLOWED_INTENTS = {
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
}

ALLOWED_SEGMENTS = {"Mass", "VIP", "Priority"}
ALLOWED_LANGUAGES = {"KZ", "ENG", "RU"}
ALLOWED_TYPES = {
    "Жалоба",
    "Смена данных",
    "Консультация",
    "Претензия",
    "Неработоспособность приложения",
    "Мошеннические действия",
    "Спам",
}

NORMALIZATION_ALIASES = {
    "астана": {"астана", "astana", "nur sultan", "nursultan", "нур султан", "нур султан"},
    "алматы": {"алматы", "almaty", "alma ata", "алма ата"},
}

ASSISTANT_CACHE_TTL_SECONDS = 60.0
ASSISTANT_CACHE_MAX_ENTRIES = 256
_ASSISTANT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_ASSISTANT_CACHE_LOCK = Lock()
_ASSISTANT_METRICS = defaultdict(int)

INTENT_META = {
    "average_age_by_office": {
        "title": "Average customer age by office",
        "chart": "bar",
        "explanation": "Average customer age for tickets assigned to each office.",
        "computed_from": "assignments join tickets join ai_analysis join business_units",
    },
    "ticket_count_by_city": {
        "title": "Ticket count by city",
        "chart": "bar",
        "explanation": "Number of assigned tickets grouped by customer city.",
        "computed_from": "assignments join tickets join ai_analysis join business_units",
    },
    "office_distribution": {
        "title": "Tickets by office",
        "chart": "bar",
        "explanation": "Distribution of assigned tickets across offices.",
        "computed_from": "assignments join tickets join ai_analysis join business_units",
    },
    "manager_workload": {
        "title": "Assigned tickets by manager",
        "chart": "bar",
        "explanation": "Assigned tickets in scope and manager current load snapshot.",
        "computed_from": "assignments join tickets join ai_analysis join managers join business_units",
    },
    "ticket_type_distribution": {
        "title": "Ticket type distribution",
        "chart": "donut",
        "explanation": "Share of ticket categories in the selected scope.",
        "computed_from": "ai_analysis join tickets join assignments join business_units",
    },
    "sentiment_distribution": {
        "title": "Sentiment distribution",
        "chart": "donut",
        "explanation": "Distribution of sentiment labels in the selected scope.",
        "computed_from": "ai_analysis join tickets join assignments join business_units",
    },
    "language_distribution": {
        "title": "Language distribution",
        "chart": "donut",
        "explanation": "Distribution of detected language labels.",
        "computed_from": "ai_analysis join tickets join assignments join business_units",
    },
    "avg_priority_by_office": {
        "title": "Average priority by office",
        "chart": "bar",
        "explanation": "Average AI priority for tickets assigned to each office.",
        "computed_from": "ai_analysis join tickets join assignments join business_units",
    },
    "vip_priority_breakdown": {
        "title": "VIP vs non-VIP priority",
        "chart": "bar",
        "explanation": "Comparison of ticket counts and average priority for VIP vs non-VIP segments.",
        "computed_from": "ai_analysis join tickets join assignments join business_units",
    },
    "unassigned_rate_and_reasons": {
        "title": "Unassigned rate and reasons",
        "chart": "bar",
        "explanation": "Assigned vs unassigned share and unassigned reason breakdown.",
        "computed_from": "assignments join tickets join ai_analysis join business_units",
    },
    "processing_time_stats": {
        "title": "Processing time stats",
        "chart": "bar",
        "explanation": "Average and P95 AI processing time in milliseconds.",
        "computed_from": "ai_analysis join tickets join assignments join business_units",
    },
    "trend_over_time": {
        "title": "Tickets trend over time",
        "chart": "line",
        "explanation": "Assigned ticket volume per day in the selected scope.",
        "computed_from": "assignments join tickets join ai_analysis join business_units",
    },
    "top_entities": {
        "title": "Top entities",
        "chart": "bar",
        "explanation": "Top cities and top ticket types in the selected scope.",
        "computed_from": "assignments join tickets join ai_analysis join business_units",
    },
    "cross_tab_type_by_office": {
        "title": "Type by office",
        "chart": "table",
        "explanation": "Cross-tab of ticket types by office.",
        "computed_from": "assignments join tickets join ai_analysis join business_units",
    },
    "cross_tab_sentiment_by_office": {
        "title": "Sentiment by office",
        "chart": "table",
        "explanation": "Cross-tab of sentiment labels by office.",
        "computed_from": "assignments join tickets join ai_analysis join business_units",
    },
    "workload_by_manager": {
        "title": "Assigned tickets by manager",
        "chart": "bar",
        "explanation": "Assigned tickets in scope and manager current load snapshot.",
        "computed_from": "assignments join tickets join ai_analysis join managers join business_units",
    },
    "custom_filtered_summary": {
        "title": "Filtered summary",
        "chart": "table",
        "explanation": "Key totals for the current filtered scope.",
        "computed_from": "assignments join tickets join ai_analysis join business_units",
    },
}

INTENT_KEYWORDS: dict[str, set[str]] = {
    "average_age_by_office": {"возраст", "age"},
    "ticket_count_by_city": {"город", "city", "cities", "count by city"},
    "office_distribution": {"по офисам", "by office", "офис", "office distribution", "tickets by office"},
    "manager_workload": {"менеджер", "manager", "нагруз", "workload"},
    "ticket_type_distribution": {"тип", "категор", "type distribution", "ticket type"},
    "sentiment_distribution": {"тон", "sentiment", "эмоц", "эмо"},
    "language_distribution": {"язык", "language", "lang"},
    "avg_priority_by_office": {"приоритет", "priority"},
    "vip_priority_breakdown": {"vip", "мас", "mass", "priority by segment", "segment"},
    "unassigned_rate_and_reasons": {"unassigned", "не назнач", "без назначения", "reason"},
    "processing_time_stats": {"processing", "время", "p95", "latency", "скорость"},
    "trend_over_time": {"trend", "тренд", "динам", "по дням", "daily"},
    "top_entities": {"top", "топ", "лидер"},
    "cross_tab_type_by_office": {"type by office", "тип по офис", "cross tab"},
    "cross_tab_sentiment_by_office": {"sentiment by office", "тон по офис", "cross tab"},
}

AMBIGUOUS_QUERIES = {
    "статистика",
    "аналитика",
    "покажи статистику",
    "show statistics",
    "dashboard",
    "metrics",
    "report",
}


@dataclass
class AnalyticsService:
    settings: Settings

    def __post_init__(self) -> None:
        self.client: OpenAIType | None = None
        if self.settings.openai_api_key and OpenAIClient is not None:
            self.client = OpenAIClient(api_key=self.settings.openai_api_key, timeout=self.settings.openai_timeout_seconds)

    def get_average_age_by_office(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(BusinessUnit.office, Ticket.birth_date)
            .join(Assignment, Assignment.office_id == BusinessUnit.id)
            .join(Ticket, Ticket.id == Assignment.ticket_id)
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
        )
        statement = self._apply_filters(statement, filters)

        office_ages: dict[str, list[int]] = defaultdict(list)
        for office, birth_date in db.execute(statement).all():
            age = _age_from_birth_date(birth_date)
            if age is not None:
                office_ages[office].append(age)

        table = []
        for office in _ordered_labels(office_ages.keys(), filters.office_names):
            ages = office_ages[office]
            avg_age = round(sum(ages) / len(ages), 2)
            table.append({"office": office, "avg_age": avg_age, "count": len(ages)})

        return {
            "labels": [row["office"] for row in table],
            "values": [row["avg_age"] for row in table],
            "table": table,
        }

    def get_ticket_distribution_by_city(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(Ticket.city, func.count(Ticket.id))
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement.group_by(Ticket.city).order_by(Ticket.city)).all()

        table = [{"city": city or "Unknown", "count": int(count)} for city, count in rows]
        return {
            "labels": [row["city"] for row in table],
            "values": [row["count"] for row in table],
            "table": table,
        }

    def get_office_distribution(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(BusinessUnit.office, func.count(Assignment.id))
            .join(Assignment, Assignment.office_id == BusinessUnit.id)
            .join(Ticket, Ticket.id == Assignment.ticket_id)
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement.group_by(BusinessUnit.office).order_by(BusinessUnit.office)).all()

        table = [{"office": office, "count": int(count)} for office, count in rows]
        return {
            "labels": [row["office"] for row in table],
            "values": [row["count"] for row in table],
            "table": table,
        }

    def get_ticket_type_distribution(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(AIAnalysis.ticket_type, func.count(AIAnalysis.id))
            .join(Ticket, Ticket.id == AIAnalysis.ticket_id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement.group_by(AIAnalysis.ticket_type).order_by(AIAnalysis.ticket_type)).all()

        table = [{"ticket_type": ticket_type, "count": int(count)} for ticket_type, count in rows]
        return {
            "labels": [row["ticket_type"] for row in table],
            "values": [row["count"] for row in table],
            "table": table,
        }

    def get_sentiment_distribution(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(AIAnalysis.tone, func.count(AIAnalysis.id))
            .join(Ticket, Ticket.id == AIAnalysis.ticket_id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement.group_by(AIAnalysis.tone).order_by(AIAnalysis.tone)).all()

        table = [{"tone": tone, "count": int(count)} for tone, count in rows]
        return {
            "labels": [row["tone"] for row in table],
            "values": [row["count"] for row in table],
            "table": table,
        }

    def get_language_distribution(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(AIAnalysis.language, func.count(AIAnalysis.id))
            .join(Ticket, Ticket.id == AIAnalysis.ticket_id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement.group_by(AIAnalysis.language).order_by(AIAnalysis.language)).all()

        table = [{"language": language or "Unknown", "count": int(count)} for language, count in rows]
        return {
            "labels": [row["language"] for row in table],
            "values": [row["count"] for row in table],
            "table": table,
        }

    def get_avg_priority_by_office(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(BusinessUnit.office, func.avg(AIAnalysis.priority))
            .join(Assignment, Assignment.office_id == BusinessUnit.id)
            .join(Ticket, Ticket.id == Assignment.ticket_id)
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement.group_by(BusinessUnit.office).order_by(BusinessUnit.office)).all()

        table = [
            {"office": office, "avg_priority": round(float(avg_priority or 0), 2)}
            for office, avg_priority in rows
        ]
        return {
            "labels": [row["office"] for row in table],
            "values": [row["avg_priority"] for row in table],
            "table": table,
        }

    def get_manager_workload(self, db: Session, filters: AssistantFilters) -> dict:
        count_statement = (
            select(Assignment.manager_id.label("manager_id"), func.count(Assignment.id).label("assigned_ticket_count"))
            .join(Ticket, Ticket.id == Assignment.ticket_id)
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        count_statement = self._apply_filters(count_statement, filters)
        count_subquery = count_statement.group_by(Assignment.manager_id).subquery()

        statement = (
            select(
                Manager.id,
                Manager.full_name,
                BusinessUnit.office,
                Manager.current_load,
                func.coalesce(count_subquery.c.assigned_ticket_count, 0),
            )
            .join(BusinessUnit, BusinessUnit.id == Manager.office_id)
            .outerjoin(count_subquery, count_subquery.c.manager_id == Manager.id)
            .order_by(desc(func.coalesce(count_subquery.c.assigned_ticket_count, 0)), Manager.full_name)
        )

        if filters.office_names:
            statement = statement.where(BusinessUnit.office.in_(filters.office_names))

        rows = db.execute(statement).all()
        table = [
            {
                "manager_id": int(manager_id),
                "manager": full_name,
                "manager_name": full_name,
                "office": office,
                "current_load": int(current_load or 0),
                "assigned_ticket_count": int(assigned_ticket_count or 0),
                "assigned_count": int(assigned_ticket_count or 0),
            }
            for manager_id, full_name, office, current_load, assigned_ticket_count in rows
        ]

        return {
            "labels": [row["manager"] for row in table],
            "values": [row["assigned_ticket_count"] for row in table],
            "table": table,
        }

    def get_workload_by_manager(self, db: Session, filters: AssistantFilters) -> dict:
        return self.get_manager_workload(db, filters)

    def get_vip_priority_breakdown(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(Ticket.segment, AIAnalysis.priority)
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement).all()

        groups: dict[str, list[int]] = {"VIP": [], "Non-VIP": []}
        for segment, priority in rows:
            key = "VIP" if segment == "VIP" else "Non-VIP"
            groups[key].append(int(priority or 0))

        table = []
        for label in ["VIP", "Non-VIP"]:
            priorities = groups[label]
            if not priorities:
                continue
            table.append(
                {
                    "segment_group": label,
                    "ticket_count": len(priorities),
                    "avg_priority": round(sum(priorities) / len(priorities), 2),
                }
            )

        return {
            "labels": [row["segment_group"] for row in table],
            "values": [row["ticket_count"] for row in table],
            "table": table,
        }

    def get_unassigned_rate_and_reasons(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(Assignment.assignment_status, Assignment.unassigned_reason, func.count(Assignment.id))
            .join(Ticket, Ticket.id == Assignment.ticket_id)
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement.group_by(Assignment.assignment_status, Assignment.unassigned_reason)).all()

        table = [
            {
                "assignment_status": status or "unknown",
                "unassigned_reason": reason or "-",
                "count": int(count),
            }
            for status, reason, count in rows
        ]

        assigned_count = sum(row["count"] for row in table if row["assignment_status"] == "assigned")
        total_count = sum(row["count"] for row in table)
        unassigned_count = max(total_count - assigned_count, 0)

        data_table = [
            {"bucket": "Assigned", "count": assigned_count},
            {"bucket": "Unassigned", "count": unassigned_count},
        ]
        reason_rows = [
            row
            for row in table
            if row["assignment_status"] != "assigned"
        ]

        return {
            "labels": [row["bucket"] for row in data_table],
            "values": [row["count"] for row in data_table],
            "table": data_table + reason_rows,
            "unassigned_rate": round((unassigned_count / total_count) * 100, 2) if total_count else 0,
        }

    def get_processing_time_stats(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(BusinessUnit.office, AIAnalysis.processing_ms)
            .join(Assignment, Assignment.office_id == BusinessUnit.id)
            .join(Ticket, Ticket.id == Assignment.ticket_id)
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .where(AIAnalysis.processing_ms.is_not(None))
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement).all()

        office_values: dict[str, list[float]] = defaultdict(list)
        for office, processing_ms in rows:
            if processing_ms is None:
                continue
            office_values[str(office)].append(float(processing_ms))

        table = []
        for office in _ordered_labels(office_values.keys(), filters.office_names):
            values = sorted(office_values[office])
            if not values:
                continue
            avg_ms = round(sum(values) / len(values), 2)
            p95_ms = round(_percentile(values, 95), 2)
            table.append(
                {
                    "office": office,
                    "avg_processing_ms": avg_ms,
                    "p95_processing_ms": p95_ms,
                    "count": len(values),
                }
            )

        return {
            "labels": [row["office"] for row in table],
            "values": [row["avg_processing_ms"] for row in table],
            "table": table,
        }

    def get_trend_over_time(self, db: Session, filters: AssistantFilters) -> dict:
        day_label = func.date(Assignment.assigned_at)
        statement = (
            select(day_label, func.count(Assignment.id))
            .join(Ticket, Ticket.id == Assignment.ticket_id)
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement.group_by(day_label).order_by(day_label)).all()

        table = [{"day": str(day), "count": int(count)} for day, count in rows if day]
        return {
            "labels": [row["day"] for row in table],
            "values": [row["count"] for row in table],
            "table": table,
        }

    def get_top_entities(self, db: Session, filters: AssistantFilters) -> dict:
        cities_statement = (
            select(Ticket.city, func.count(Ticket.id).label("count"))
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        cities_statement = self._apply_filters(cities_statement, filters)
        city_rows = db.execute(
            cities_statement.group_by(Ticket.city).order_by(desc(func.count(Ticket.id)), Ticket.city).limit(5)
        ).all()

        type_statement = (
            select(AIAnalysis.ticket_type, func.count(AIAnalysis.id).label("count"))
            .join(Ticket, Ticket.id == AIAnalysis.ticket_id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        type_statement = self._apply_filters(type_statement, filters)
        type_rows = db.execute(
            type_statement.group_by(AIAnalysis.ticket_type).order_by(desc(func.count(AIAnalysis.id)), AIAnalysis.ticket_type).limit(5)
        ).all()

        table = [
            {"entity_type": "city", "entity": city or "Unknown", "count": int(count)}
            for city, count in city_rows
        ]
        table.extend(
            {"entity_type": "ticket_type", "entity": ticket_type or "Unknown", "count": int(count)}
            for ticket_type, count in type_rows
        )

        city_table = [row for row in table if row["entity_type"] == "city"]
        chart_rows = city_table if city_table else table
        return {
            "labels": [row["entity"] for row in chart_rows],
            "values": [row["count"] for row in chart_rows],
            "table": table,
        }

    def get_cross_tab_type_by_office(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(BusinessUnit.office, AIAnalysis.ticket_type, func.count(AIAnalysis.id))
            .join(Assignment, Assignment.office_id == BusinessUnit.id)
            .join(Ticket, Ticket.id == Assignment.ticket_id)
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement.group_by(BusinessUnit.office, AIAnalysis.ticket_type)).all()

        table = [
            {"office": office, "ticket_type": ticket_type, "count": int(count)}
            for office, ticket_type, count in rows
        ]
        return {
            "labels": [f"{row['office']} · {row['ticket_type']}" for row in table],
            "values": [row["count"] for row in table],
            "table": table,
        }

    def get_cross_tab_sentiment_by_office(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(BusinessUnit.office, AIAnalysis.tone, func.count(AIAnalysis.id))
            .join(Assignment, Assignment.office_id == BusinessUnit.id)
            .join(Ticket, Ticket.id == Assignment.ticket_id)
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
        )
        statement = self._apply_filters(statement, filters)
        rows = db.execute(statement.group_by(BusinessUnit.office, AIAnalysis.tone)).all()

        table = [
            {"office": office, "tone": tone, "count": int(count)}
            for office, tone, count in rows
        ]
        return {
            "labels": [f"{row['office']} · {row['tone']}" for row in table],
            "values": [row["count"] for row in table],
            "table": table,
        }

    def get_custom_filtered_summary(self, db: Session, filters: AssistantFilters) -> dict:
        statement = (
            select(
                func.count(Ticket.id),
                func.avg(AIAnalysis.priority),
                func.count(func.distinct(BusinessUnit.office)),
                func.count(func.distinct(Ticket.city)),
            )
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        statement = self._apply_filters(statement, filters)
        total, avg_priority, office_count, city_count = db.execute(statement).one()

        table = [
            {"metric": "tickets_total", "value": int(total or 0)},
            {"metric": "avg_priority", "value": round(float(avg_priority or 0), 2)},
            {"metric": "offices", "value": int(office_count or 0)},
            {"metric": "cities", "value": int(city_count or 0)},
        ]
        return {
            "labels": [row["metric"] for row in table],
            "values": [row["value"] for row in table],
            "table": table,
        }

    def assistant_query(self, db: Session, query: str, scope: dict[str, str | None] | None = None) -> dict:
        started = time.perf_counter()
        _ASSISTANT_METRICS["requests_total"] += 1

        query_text = query.strip()
        known_offices, known_cities = self._known_entities(db)

        base_scope_filters, scope_applied, scope_warnings = self._apply_scope_intersection(
            db,
            AssistantFilters(),
            scope,
            known_offices,
        )

        if self._is_ambiguous_query(query_text):
            _ASSISTANT_METRICS["clarification_total"] += 1
            return {
                "kind": "clarification",
                "title": "Please clarify your analytics request",
                "explanation": "Choose one of these suggestions, or ask a specific metric such as sentiment, priority, type, or processing time.",
                "options": self._clarification_options(base_scope_filters),
                "filters": base_scope_filters.model_dump(),
                "scope_applied": scope_applied,
                "warnings": scope_warnings,
            }

        intent, query_filters, used_fallback = self._classify_and_extract_filters(db, query_text)
        final_filters, scope_applied, scope_warnings = self._apply_scope_intersection(
            db,
            query_filters,
            scope,
            known_offices,
        )

        cache_key = _build_cache_key(query_text, intent, final_filters, scope_applied)
        cached = _cache_get(cache_key)
        if cached is not None:
            cached["cache_hit"] = True
            cached["used_fallback"] = used_fallback
            cached["scope_applied"] = scope_applied
            cached["warnings"] = list(dict.fromkeys([*cached.get("warnings", []), *scope_warnings]))
            _ASSISTANT_METRICS["cache_hit_total"] += 1
            LOGGER.info(
                "assistant_query_processed",
                extra={
                    "query": query_text,
                    "intent": intent,
                    "source": "fallback" if used_fallback else "llm",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "result_rows": len(cached.get("table", [])),
                    "cache_hit": True,
                },
            )
            return cached

        payload = self._execute_intent(db, intent, final_filters)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        meta = INTENT_META[intent]
        warnings = list(scope_warnings)
        chart_type = meta["chart"]
        explanation = payload.get("explanation") or meta["explanation"]

        if not payload.get("table"):
            chart_type = "empty"
            explanation = "Нет данных в выбранном диапазоне; попробуйте расширить фильтры."
            warnings.append("No data in selected scope.")

        response = {
            "kind": "result",
            "intent": intent,
            "title": payload.get("title") or meta["title"],
            "chart_type": chart_type,
            "data": {
                "labels": payload.get("labels", []),
                "values": payload.get("values", []),
            },
            "table": payload.get("table", []),
            "explanation": explanation,
            "filters": final_filters.model_dump(),
            "computed_from": meta["computed_from"],
            "scope_applied": scope_applied,
            "warnings": warnings,
            "used_fallback": used_fallback,
            "cache_hit": False,
        }

        _cache_set(cache_key, response)
        _ASSISTANT_METRICS["responses_total"] += 1
        if used_fallback:
            _ASSISTANT_METRICS["fallback_total"] += 1

        LOGGER.info(
            "assistant_query_processed",
            extra={
                "query": query_text,
                "intent": intent,
                "source": "fallback" if used_fallback else "llm",
                "filters": final_filters.model_dump(),
                "duration_ms": duration_ms,
                "result_rows": len(response["table"]),
                "cache_hit": False,
            },
        )

        return response

    def _clarification_options(self, filters: AssistantFilters) -> list[dict[str, str]]:
        office_hint = f" for office {filters.office_names[0]}" if filters.office_names else ""
        return [
            {
                "intent": "ticket_type_distribution",
                "label": "Ticket type distribution",
                "query_hint": f"Show ticket type distribution{office_hint}",
            },
            {
                "intent": "sentiment_distribution",
                "label": "Sentiment distribution",
                "query_hint": f"Show sentiment distribution{office_hint}",
            },
            {
                "intent": "avg_priority_by_office",
                "label": "Average priority by office",
                "query_hint": "Show average priority by office",
            },
        ]

    def _execute_intent(self, db: Session, intent: str, filters: AssistantFilters) -> dict:
        function_map = {
            "average_age_by_office": self.get_average_age_by_office,
            "ticket_count_by_city": self.get_ticket_distribution_by_city,
            "office_distribution": self.get_office_distribution,
            "manager_workload": self.get_manager_workload,
            "ticket_type_distribution": self.get_ticket_type_distribution,
            "sentiment_distribution": self.get_sentiment_distribution,
            "language_distribution": self.get_language_distribution,
            "avg_priority_by_office": self.get_avg_priority_by_office,
            "vip_priority_breakdown": self.get_vip_priority_breakdown,
            "unassigned_rate_and_reasons": self.get_unassigned_rate_and_reasons,
            "processing_time_stats": self.get_processing_time_stats,
            "trend_over_time": self.get_trend_over_time,
            "top_entities": self.get_top_entities,
            "cross_tab_type_by_office": self.get_cross_tab_type_by_office,
            "cross_tab_sentiment_by_office": self.get_cross_tab_sentiment_by_office,
            "workload_by_manager": self.get_workload_by_manager,
            "custom_filtered_summary": self.get_custom_filtered_summary,
        }

        if intent not in function_map:
            return self.get_custom_filtered_summary(db, filters)
        return function_map[intent](db, filters)

    def _apply_scope_intersection(
        self,
        db: Session,
        filters: AssistantFilters,
        scope: dict[str, str | None] | None,
        known_offices: list[str] | None = None,
    ) -> tuple[AssistantFilters, dict[str, str | None], list[str]]:
        known = known_offices or [row[0] for row in db.execute(select(BusinessUnit.office)).all() if row and row[0]]

        warnings: list[str] = []
        scope_run_id = _normalize_run_id(scope.get("run_id") if scope else None)
        scope_date_from = _normalize_date_filter(scope.get("date_from") if scope else None)
        scope_date_to = _normalize_date_filter(scope.get("date_to") if scope else None)
        scope_office_raw = (scope.get("office") if scope else "") or ""
        scope_offices = _resolve_values([scope_office_raw], known, entity_type="office") if scope_office_raw.strip() else []

        office_names = list(filters.office_names)
        if scope_office_raw.strip():
            if office_names:
                intersection = [office for office in office_names if office in scope_offices]
                office_names = intersection if intersection else ["__scope_no_match__"]
                if not intersection:
                    warnings.append("Query office filter does not match page scope office.")
            else:
                office_names = scope_offices if scope_offices else ["__scope_no_match__"]

        date_from, date_to, date_warnings = _intersect_date_ranges(
            filters.date_from,
            filters.date_to,
            scope_date_from,
            scope_date_to,
        )
        warnings.extend(date_warnings)

        run_id = filters.run_id
        if scope_run_id:
            if run_id and run_id != scope_run_id:
                warnings.append("Query run_id was ignored to keep page scope.")
            run_id = scope_run_id

        scope_applied = {
            "run_id": scope_run_id,
            "office": scope_offices[0] if scope_offices else (scope_office_raw.strip() or None),
            "date_from": scope_date_from,
            "date_to": scope_date_to,
        }

        return (
            AssistantFilters(
                office_names=office_names,
                office_ids=filters.office_ids,
                cities=filters.cities,
                date_from=date_from,
                date_to=date_to,
                segment=filters.segment,
                ticket_type=filters.ticket_type,
                language=filters.language,
                run_id=run_id,
            ),
            scope_applied,
            warnings,
        )

    def get_summary(
        self,
        db: Session,
        *,
        run_id: str | None = None,
        office: str | None = None,
        office_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        filters = AssistantFilters(
            run_id=run_id,
            office_names=[office] if office else [],
            office_ids=[office_id] if office_id else [],
            date_from=date_from,
            date_to=date_to,
        )

        statement = (
            select(Ticket.city, AIAnalysis.ticket_type, func.count(Ticket.id))
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        statement = self._apply_filters(statement, filters)
        ticket_types_by_city = db.execute(
            statement.group_by(Ticket.city, AIAnalysis.ticket_type).order_by(Ticket.city, AIAnalysis.ticket_type)
        ).all()

        tickets_by_office_statement = (
            select(BusinessUnit.office, func.count(Assignment.id))
            .join(Assignment, Assignment.office_id == BusinessUnit.id)
            .join(Ticket, Ticket.id == Assignment.ticket_id)
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
        )
        tickets_by_office_statement = self._apply_filters(tickets_by_office_statement, filters)
        tickets_by_office = db.execute(
            tickets_by_office_statement.group_by(BusinessUnit.office).order_by(BusinessUnit.office)
        ).all()

        sentiment = self.get_sentiment_distribution(db, filters)
        avg_priority = self.get_avg_priority_by_office(db, filters)
        workload = self.get_manager_workload(db, filters)

        avg_priority_by_city_statement = (
            select(Ticket.city, func.avg(AIAnalysis.priority))
            .join(AIAnalysis, AIAnalysis.ticket_id == Ticket.id)
            .join(Assignment, Assignment.ticket_id == Ticket.id)
            .join(BusinessUnit, BusinessUnit.id == Assignment.office_id)
        )
        avg_priority_by_city_statement = self._apply_filters(avg_priority_by_city_statement, filters)
        avg_priority_by_city = db.execute(
            avg_priority_by_city_statement.group_by(Ticket.city).order_by(Ticket.city)
        ).all()

        return {
            "ticket_types_by_city": [
                {"city": city or "Unknown", "ticket_type": ticket_type, "count": int(count)}
                for city, ticket_type, count in ticket_types_by_city
            ],
            "tickets_by_office": [{"office": office_name, "count": int(count)} for office_name, count in tickets_by_office],
            "sentiment_distribution": sentiment["table"],
            "avg_priority_by_office": avg_priority["table"],
            "avg_priority_by_city": [
                {"city": city or "Unknown", "avg_priority": round(float(avg_value or 0), 2)}
                for city, avg_value in avg_priority_by_city
            ],
            "workload_by_manager": workload["table"],
        }

    def _apply_filters(self, statement, filters: AssistantFilters):
        parsed_from, parsed_to = _parse_date_range(filters.date_from, filters.date_to)

        if filters.run_id:
            statement = statement.where(Ticket.run_id == filters.run_id)
        if filters.office_names:
            statement = statement.where(BusinessUnit.office.in_(filters.office_names))
        if filters.office_ids:
            statement = statement.where(BusinessUnit.id.in_(filters.office_ids))
        if filters.cities:
            statement = statement.where(Ticket.city.in_(filters.cities))
        if filters.segment:
            statement = statement.where(Ticket.segment == filters.segment)
        if filters.ticket_type:
            statement = statement.where(AIAnalysis.ticket_type == filters.ticket_type)
        if filters.language:
            statement = statement.where(AIAnalysis.language == filters.language)
        if parsed_from:
            statement = statement.where(Assignment.assigned_at >= parsed_from)
        if parsed_to:
            statement = statement.where(Assignment.assigned_at <= parsed_to)

        return statement

    def _classify_and_extract_filters(self, db: Session, query: str) -> tuple[str, AssistantFilters, bool]:
        known_offices, known_cities = self._known_entities(db)

        if self.client:
            parsed = self._classify_with_llm(query, known_offices, known_cities)
            if parsed is not None:
                return parsed[0], parsed[1], False

        intent, filters = self._classify_with_heuristics(query, known_offices, known_cities)
        return intent, filters, True

    def _known_entities(self, db: Session) -> tuple[list[str], list[str]]:
        offices = [row[0] for row in db.execute(select(BusinessUnit.office).order_by(BusinessUnit.office)).all() if row[0]]
        cities = [
            row[0]
            for row in db.execute(select(Ticket.city).where(Ticket.city.is_not(None)).distinct()).all()
            if row[0]
        ]
        return offices, cities

    def _classify_with_llm(
        self,
        query: str,
        known_offices: list[str],
        known_cities: list[str],
    ) -> tuple[str, AssistantFilters] | None:
        if not self.client:
            return None

        prompt = (
            "Classify analytics request into one allowed intent and extract strict filters as JSON. "
            f"Allowed intents: {sorted(ALLOWED_INTENTS)}. "
            "Allowed filters keys: office_names (array), cities (array), date_from (YYYY-MM-DD), date_to (YYYY-MM-DD), "
            "segment (Mass/VIP/Priority), ticket_type, language (KZ/ENG/RU), run_id. "
            "Do not add unknown keys, SQL, or calculations. "
            f"Known offices: {known_offices}. Known cities: {known_cities[:100]}. "
            f"User query: {query!r}. "
            "Return JSON object: {intent: string, filters: object}."
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
            if intent not in ALLOWED_INTENTS:
                return None
            filters = _sanitize_filters(payload.get("filters") or {}, known_offices, known_cities)
            return intent, filters
        except Exception:
            return None

    def _classify_with_heuristics(
        self,
        query: str,
        known_offices: list[str],
        known_cities: list[str],
    ) -> tuple[str, AssistantFilters]:
        q = _normalize_text(query)

        intent = "custom_filtered_summary"

        if "распредел" in q or "distribution" in q:
            if any(token in q for token in {"язык", "language", "lang"}):
                intent = "language_distribution"
            elif any(token in q for token in {"тон", "sentiment", "эмоц", "эмо"}):
                intent = "sentiment_distribution"
            elif any(token in q for token in {"тип", "категор", "ticket"}):
                intent = "ticket_type_distribution"
            elif any(token in q for token in {"офис", "office"}):
                intent = "office_distribution"
            elif any(token in q for token in {"город", "city"}):
                intent = "ticket_count_by_city"

        if intent == "custom_filtered_summary":
            if "возраст" in q or "age" in q:
                intent = "average_age_by_office"
            elif "unassigned" in q or "без назначения" in q or "не назнач" in q:
                intent = "unassigned_rate_and_reasons"
            elif "processing" in q or "время" in q or "p95" in q or "latency" in q:
                intent = "processing_time_stats"
            elif "trend" in q or "тренд" in q or "динам" in q or "по дням" in q:
                intent = "trend_over_time"
            elif "vip" in q and ("priority" in q or "приоритет" in q or "mass" in q or "мас" in q):
                intent = "vip_priority_breakdown"
            elif "тип" in q or "категор" in q:
                intent = "ticket_type_distribution"
            elif "тон" in q or "sentiment" in q or "эмоц" in q:
                intent = "sentiment_distribution"
            elif "язык" in q or "language" in q or "lang" in q:
                intent = "language_distribution"
            elif "приоритет" in q or "priority" in q:
                intent = "avg_priority_by_office"
            elif "нагруз" in q or "manager" in q or "менеджер" in q:
                intent = "manager_workload"
            elif "офис" in q or "office" in q:
                intent = "office_distribution"
            elif "город" in q or "city" in q or "count" in q or "количеств" in q:
                intent = "ticket_count_by_city"
            elif "топ" in q or "top" in q:
                intent = "top_entities"

        filters_dict: dict[str, Any] = {
            "office_names": _resolve_values(_extract_mentions(query), known_offices, entity_type="office"),
            "cities": _resolve_values(_extract_mentions(query), known_cities, entity_type="city"),
        }

        for segment in ALLOWED_SEGMENTS:
            if segment.lower() in q:
                filters_dict["segment"] = segment
                break
        if "массов" in q:
            filters_dict["segment"] = "Mass"
        if "приорит" in q and "segment" not in filters_dict:
            filters_dict["segment"] = "Priority"

        for language in ALLOWED_LANGUAGES:
            if language.lower() in q:
                filters_dict["language"] = language
                break

        for ticket_type in ALLOWED_TYPES:
            if _normalize_text(ticket_type) in q:
                filters_dict["ticket_type"] = ticket_type
                break

        run_ids = re.findall(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", q)
        if run_ids:
            filters_dict["run_id"] = run_ids[0]

        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", query)
        if len(dates) >= 1:
            filters_dict["date_from"] = dates[0]
        if len(dates) >= 2:
            filters_dict["date_to"] = dates[1]

        filters = _sanitize_filters(filters_dict, known_offices, known_cities)
        return intent, filters

    def _is_ambiguous_query(self, query: str) -> bool:
        normalized = _normalize_text(query)
        if not normalized:
            return True
        if normalized in AMBIGUOUS_QUERIES:
            return True

        tokens = normalized.split()
        if len(tokens) <= 2 and any(token in {"статистика", "analytics", "dashboard", "report"} for token in tokens):
            return True

        has_intent_signal = any(
            keyword in normalized
            for keywords in INTENT_KEYWORDS.values()
            for keyword in keywords
        )
        has_filter_signal = bool(re.search(r"\d{4}-\d{2}-\d{2}|vip|mass|priority|офис|office|город|city", normalized))
        return not has_intent_signal and not has_filter_signal


def _sanitize_filters(raw: dict[str, Any], known_offices: list[str], known_cities: list[str]) -> AssistantFilters:
    office_names = _resolve_values(raw.get("office_names") or [], known_offices, entity_type="office")
    cities = _resolve_values(raw.get("cities") or [], known_cities, entity_type="city")

    segment = raw.get("segment") if raw.get("segment") in ALLOWED_SEGMENTS else None
    ticket_type = raw.get("ticket_type") if raw.get("ticket_type") in ALLOWED_TYPES else None
    language = raw.get("language") if raw.get("language") in ALLOWED_LANGUAGES else None

    date_from = _normalize_date_filter(raw.get("date_from"))
    date_to = _normalize_date_filter(raw.get("date_to"))

    run_id = _normalize_run_id(raw.get("run_id"))

    return AssistantFilters(
        office_names=office_names,
        office_ids=[],
        cities=cities,
        date_from=date_from,
        date_to=date_to,
        segment=segment,
        ticket_type=ticket_type,
        language=language,
        run_id=run_id,
    )


def _normalize_run_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _ordered_labels(labels: Any, preferred_order: list[str]) -> list[str]:
    values = list(labels)
    if not preferred_order:
        return sorted(values)

    rank = {label: index for index, label in enumerate(preferred_order)}
    return sorted(values, key=lambda value: (rank.get(value, 10**6), value))


def _normalize_text(value: str) -> str:
    normalized = value.strip().lower().replace("ё", "е")
    normalized = re.sub(r"[\(\)\[\]\{\}.,;:!?\\/\\|]+", " ", normalized)
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _extract_mentions(query: str) -> list[str]:
    normalized = _normalize_text(query)
    if not normalized:
        return []
    tokens = normalized.split()
    ngrams = set(tokens)
    for size in (2, 3, 4):
        for index in range(0, max(len(tokens) - size + 1, 0)):
            ngrams.add(" ".join(tokens[index : index + size]))
    return sorted(ngrams)


def _resolve_values(values: list[Any], known_values: list[str], *, entity_type: str) -> list[str]:
    if not known_values:
        return []

    normalized_known = {_normalize_text(value): value for value in known_values}
    matched: list[str] = []

    alias_lookup: dict[str, list[str]] = defaultdict(list)
    for known in known_values:
        normalized_known_value = _normalize_text(known)
        alias_lookup[normalized_known_value].append(known)
        for token in normalized_known_value.split():
            if len(token) > 2:
                alias_lookup[token].append(known)
        for canonical, aliases in NORMALIZATION_ALIASES.items():
            if any(alias in normalized_known_value for alias in aliases):
                for alias in aliases:
                    alias_lookup[alias].append(known)
                alias_lookup[canonical].append(known)

    for raw_value in values:
        if not isinstance(raw_value, str):
            continue
        needle = _normalize_text(raw_value)
        if not needle:
            continue

        exact = normalized_known.get(needle)
        if exact and exact not in matched:
            matched.append(exact)
            continue

        candidates = alias_lookup.get(needle, [])
        if not candidates:
            candidates = [known for known in known_values if needle in _normalize_text(known)]

        for candidate in candidates:
            if candidate not in matched:
                matched.append(candidate)

    return matched


def _normalize_date_filter(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None

    parsed_date: date | None = None
    try:
        parsed_date = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        try:
            parsed_date = datetime.fromisoformat(raw).date()
        except ValueError:
            return None

    min_date = date(2000, 1, 1)
    max_date = (datetime.utcnow() + timedelta(days=1)).date()
    if parsed_date < min_date:
        parsed_date = min_date
    if parsed_date > max_date:
        parsed_date = max_date

    return parsed_date.isoformat()


def _parse_iso_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d")
        except ValueError:
            return None


def _parse_date_range(date_from: str | None, date_to: str | None) -> tuple[datetime | None, datetime | None]:
    start = _parse_iso_date(date_from)
    end = _parse_iso_date(date_to)

    if start and start.time() == dtime(0, 0, 0):
        start = datetime.combine(start.date(), dtime.min)
    if end and end.time() == dtime(0, 0, 0):
        end = datetime.combine(end.date(), dtime.max)

    return start, end


def _intersect_date_ranges(
    query_from: str | None,
    query_to: str | None,
    scope_from: str | None,
    scope_to: str | None,
) -> tuple[str | None, str | None, list[str]]:
    warnings: list[str] = []

    parsed_query_from = _normalize_date_filter(query_from)
    parsed_query_to = _normalize_date_filter(query_to)
    parsed_scope_from = _normalize_date_filter(scope_from)
    parsed_scope_to = _normalize_date_filter(scope_to)

    final_from = parsed_query_from
    final_to = parsed_query_to

    if parsed_scope_from:
        if not final_from or parsed_scope_from > final_from:
            final_from = parsed_scope_from
    if parsed_scope_to:
        if not final_to or parsed_scope_to < final_to:
            final_to = parsed_scope_to

    if final_from and final_to and final_from > final_to:
        warnings.append("Query date range does not overlap with page scope date range.")

    return final_from, final_to, warnings


def _age_from_birth_date(value: str | None) -> int | None:
    if not value:
        return None

    text = str(value).strip().split(" ")[0]
    try:
        birth = date.fromisoformat(text)
    except ValueError:
        return None

    today = date.today()
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return years if years >= 0 else None


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (percentile / 100) * (len(sorted_values) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[lower]
    fraction = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def _build_cache_key(query: str, intent: str, filters: AssistantFilters, scope_applied: dict[str, Any]) -> str:
    payload = {
        "query": _normalize_text(query),
        "intent": intent,
        "filters": filters.model_dump(),
        "scope": scope_applied,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _cache_get(key: str) -> dict[str, Any] | None:
    now = time.time()
    with _ASSISTANT_CACHE_LOCK:
        entry = _ASSISTANT_CACHE.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at <= now:
            _ASSISTANT_CACHE.pop(key, None)
            return None
        return json.loads(json.dumps(value, ensure_ascii=False))


def _cache_set(key: str, value: dict[str, Any]) -> None:
    now = time.time()
    with _ASSISTANT_CACHE_LOCK:
        if len(_ASSISTANT_CACHE) >= ASSISTANT_CACHE_MAX_ENTRIES:
            oldest_key = min(_ASSISTANT_CACHE.items(), key=lambda item: item[1][0])[0]
            _ASSISTANT_CACHE.pop(oldest_key, None)
        _ASSISTANT_CACHE[key] = (now + ASSISTANT_CACHE_TTL_SECONDS, json.loads(json.dumps(value, ensure_ascii=False)))
