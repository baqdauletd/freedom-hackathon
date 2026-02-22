from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from backend.services.analytics import AnalyticsService
from backend.tests._assistant_test_utils import DummySettings, build_session, seed_assistant_dataset


@pytest.mark.parametrize(
    ("query", "expected_intent"),
    [
        ("Покажи распределение по офисам", "office_distribution"),
        ("Покажи VIP vs Mass priority", "vip_priority_breakdown"),
        ("Покажи без назначения и причины", "unassigned_rate_and_reasons"),
        ("Покажи processing time p95 по офисам", "processing_time_stats"),
        ("Покажи тренд по дням", "trend_over_time"),
    ],
)
def test_intents_return_valid_result_schema(query: str, expected_intent: str) -> None:
    session = build_session()
    try:
        seeded = seed_assistant_dataset(session)
        service = AnalyticsService(DummySettings())

        response = service.assistant_query(
            session,
            query,
            scope={"run_id": seeded["run_1"]},
        )

        assert response["kind"] == "result"
        assert response["intent"] == expected_intent
        assert response["chart_type"] in {"bar", "line", "pie", "donut", "table", "empty"}
        assert isinstance(response["data"], dict)
        assert isinstance(response["data"].get("labels"), list)
        assert isinstance(response["data"].get("values"), list)
        assert len(response["data"]["labels"]) == len(response["data"]["values"])
        assert isinstance(response["table"], list)
        assert isinstance(response["explanation"], str)
        assert response["filters"]["run_id"] == seeded["run_1"]
    finally:
        session.close()
