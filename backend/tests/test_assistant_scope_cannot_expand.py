from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from backend.services.analytics import AnalyticsService
from backend.tests._assistant_test_utils import DummySettings, build_session, seed_assistant_dataset


def test_ui_scope_intersection_prevents_run_expansion() -> None:
    session = build_session()
    try:
        seeded = seed_assistant_dataset(session)
        service = AnalyticsService(DummySettings())

        response = service.assistant_query(
            session,
            f"Show ticket count by city for run {seeded['run_2']}",
            scope={"run_id": seeded["run_1"]},
        )

        assert response["kind"] == "result"
        assert response["filters"]["run_id"] == seeded["run_1"]
        assert response["scope_applied"]["run_id"] == seeded["run_1"]
        assert response["table"] == [{"city": "Астана", "count": 2}]
    finally:
        session.close()
