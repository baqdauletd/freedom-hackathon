from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time as dtime
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
    "ticket_type_distribution",
    "sentiment_distribution",
    "avg_priority_by_office",
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

INTENT_META = {
    "average_age_by_office": {
        "title": "Средний возраст клиентов по офисам",
        "chart": "bar",
        "explanation": "Средний возраст рассчитан по клиентам, чьи обращения были распределены в выбранные офисы.",
    },
    "ticket_count_by_city": {
        "title": "Количество обращений по городам",
        "chart": "bar",
        "explanation": "Показано количество распределенных обращений в разрезе городов клиентов.",
    },
    "ticket_type_distribution": {
        "title": "Распределение типов обращений",
        "chart": "pie",
        "explanation": "Диаграмма показывает долю каждого типа обращений в выборке.",
    },
    "sentiment_distribution": {
        "title": "Распределение тональности",
        "chart": "pie",
        "explanation": "Распределение тональности обращений (позитивный, нейтральный, негативный).",
    },
    "avg_priority_by_office": {
        "title": "Средний приоритет по офисам",
        "chart": "bar",
        "explanation": "Средний приоритет обращений рассчитан по каждому офису назначения.",
    },
    "workload_by_manager": {
        "title": "Нагрузка по менеджерам",
        "chart": "bar",
        "explanation": "Показана текущая нагрузка и количество назначений по менеджерам.",
    },
    "custom_filtered_summary": {
        "title": "Сводка по выбранным фильтрам",
        "chart": "table",
        "explanation": "Сводные метрики рассчитаны по отфильтрованной выборке обращений.",
    },
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
        intent, filters = self._classify_and_extract_filters(db, query)
        filters = self._apply_scope_overrides(db, filters, scope)

        function_map = {
            "average_age_by_office": self.get_average_age_by_office,
            "ticket_count_by_city": self.get_ticket_distribution_by_city,
            "ticket_type_distribution": self.get_ticket_type_distribution,
            "sentiment_distribution": self.get_sentiment_distribution,
            "avg_priority_by_office": self.get_avg_priority_by_office,
            "workload_by_manager": self.get_manager_workload,
            "custom_filtered_summary": self.get_custom_filtered_summary,
        }

        payload = function_map[intent](db, filters)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        LOGGER.info(
            "assistant_query_processed",
            extra={
                "query": query,
                "intent": intent,
                "filters": filters.model_dump(),
                "duration_ms": duration_ms,
                "result_rows": len(payload["table"]),
            },
        )

        meta = INTENT_META[intent]
        return {
            "intent": intent,
            "title": meta["title"],
            "chart_type": meta["chart"],
            "data": {"labels": payload["labels"], "values": payload["values"]},
            "table": payload["table"],
            "explanation": meta["explanation"],
            "filters": filters.model_dump(),
        }

    def _apply_scope_overrides(
        self,
        db: Session,
        filters: AssistantFilters,
        scope: dict[str, str | None] | None,
    ) -> AssistantFilters:
        if not scope:
            return filters

        run_id = (scope.get("run_id") or "").strip() or None
        office = (scope.get("office") or "").strip() or None
        date_from = scope.get("date_from") if _parse_iso_date(scope.get("date_from")) else None
        date_to = scope.get("date_to") if _parse_iso_date(scope.get("date_to")) else None

        office_names = filters.office_names
        if office:
            known_offices = [row[0] for row in db.execute(select(BusinessUnit.office)).all() if row and row[0]]
            normalized = next((value for value in known_offices if value.lower() == office.lower()), None)
            if normalized:
                office_names = [normalized]

        return AssistantFilters(
            office_names=office_names,
            office_ids=filters.office_ids,
            cities=filters.cities,
            date_from=date_from or filters.date_from,
            date_to=date_to or filters.date_to,
            segment=filters.segment,
            ticket_type=filters.ticket_type,
            language=filters.language,
            run_id=run_id or filters.run_id,
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

    def _classify_and_extract_filters(self, db: Session, query: str) -> tuple[str, AssistantFilters]:
        known_offices = [row[0] for row in db.execute(select(BusinessUnit.office).order_by(BusinessUnit.office)).all() if row[0]]
        known_cities = [row[0] for row in db.execute(select(Ticket.city).where(Ticket.city.is_not(None)).distinct()).all() if row[0]]

        if self.client:
            parsed = self._classify_with_llm(query, known_offices, known_cities)
            if parsed is not None:
                return parsed

        return self._classify_with_heuristics(query, known_offices, known_cities)

    def _classify_with_llm(
        self,
        query: str,
        known_offices: list[str],
        known_cities: list[str],
    ) -> tuple[str, AssistantFilters] | None:
        if not self.client:
            return None

        prompt = (
            "Classify analytics request to one allowed intent and extract filters as strict JSON. "
            f"Allowed intents: {sorted(ALLOWED_INTENTS)}. "
            "Allowed filters keys: office_names (array), cities (array), date_from (YYYY-MM-DD), date_to (YYYY-MM-DD), "
            "segment (Mass/VIP/Priority), ticket_type, language (KZ/ENG/RU), run_id. "
            "Do not add unknown keys. "
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
        q = query.lower()

        intent = "custom_filtered_summary"
        if "возраст" in q or "age" in q:
            intent = "average_age_by_office"
        elif "тип" in q and "обращ" in q:
            intent = "ticket_type_distribution"
        elif "тон" in q or "sentiment" in q or "эмо" in q:
            intent = "sentiment_distribution"
        elif "приоритет" in q:
            intent = "avg_priority_by_office"
        elif "нагруз" in q or "manager" in q:
            intent = "workload_by_manager"
        elif "город" in q or "city" in q or "количеств" in q or "count" in q:
            intent = "ticket_count_by_city"

        filters_dict: dict[str, Any] = {
            "office_names": [office for office in known_offices if office.lower() in q],
            "cities": [city for city in known_cities if city.lower() in q],
        }

        for segment in ALLOWED_SEGMENTS:
            if segment.lower() in q:
                filters_dict["segment"] = segment
                break

        for language in ALLOWED_LANGUAGES:
            if language.lower() in q:
                filters_dict["language"] = language
                break

        for ticket_type in ALLOWED_TYPES:
            if ticket_type.lower() in q:
                filters_dict["ticket_type"] = ticket_type
                break

        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", query)
        if len(dates) >= 1:
            filters_dict["date_from"] = dates[0]
        if len(dates) >= 2:
            filters_dict["date_to"] = dates[1]

        filters = _sanitize_filters(filters_dict, known_offices, known_cities)
        return intent, filters


def _sanitize_filters(raw: dict[str, Any], known_offices: list[str], known_cities: list[str]) -> AssistantFilters:
    office_lookup = {office.lower(): office for office in known_offices}
    city_lookup = {city.lower(): city for city in known_cities}

    office_names = []
    for value in raw.get("office_names") or []:
        if not isinstance(value, str):
            continue
        normalized = office_lookup.get(value.strip().lower())
        if normalized and normalized not in office_names:
            office_names.append(normalized)

    cities = []
    for value in raw.get("cities") or []:
        if not isinstance(value, str):
            continue
        normalized = city_lookup.get(value.strip().lower())
        if normalized and normalized not in cities:
            cities.append(normalized)

    segment = raw.get("segment") if raw.get("segment") in ALLOWED_SEGMENTS else None
    ticket_type = raw.get("ticket_type") if raw.get("ticket_type") in ALLOWED_TYPES else None
    language = raw.get("language") if raw.get("language") in ALLOWED_LANGUAGES else None

    date_from = raw.get("date_from") if _parse_iso_date(raw.get("date_from")) else None
    date_to = raw.get("date_to") if _parse_iso_date(raw.get("date_to")) else None

    run_id = raw.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        run_id = None

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


def _ordered_labels(labels: Any, preferred_order: list[str]) -> list[str]:
    """Order labels by caller preference, then alphabetically for the rest."""
    values = list(labels)
    if not preferred_order:
        return sorted(values)

    rank = {label: index for index, label in enumerate(preferred_order)}
    return sorted(values, key=lambda value: (rank.get(value, 10**6), value))


def _parse_iso_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
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
