from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from backend.services.analytics import AnalyticsService
from backend.tests._assistant_test_utils import DummySettings, build_session, seed_assistant_dataset


def test_fallback_mode_returns_valid_result_schema() -> None:
    session = build_session()
    try:
        seeded = seed_assistant_dataset(session)
        service = AnalyticsService(DummySettings())

        response = service.assistant_query(
            session,
            "Покажи распределение по офисам",
            scope={"run_id": seeded["run_1"]},
        )

        assert response["kind"] == "result"
        assert response["used_fallback"] is True
        assert response["intent"] == "office_distribution"
        assert isinstance(response["data"]["labels"], list)
        assert isinstance(response["data"]["values"], list)
        assert len(response["data"]["labels"]) == len(response["data"]["values"])
        assert isinstance(response["table"], list)
        assert isinstance(response["explanation"], str)
    finally:
        session.close()
