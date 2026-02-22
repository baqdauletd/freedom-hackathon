from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from backend.services.analytics import AnalyticsService
from backend.tests._assistant_test_utils import DummySettings, build_session, seed_assistant_dataset


def test_office_name_normalization_maps_astana_variants() -> None:
    session = build_session()
    try:
        seeded = seed_assistant_dataset(session)
        service = AnalyticsService(DummySettings())

        response = service.assistant_query(
            session,
            "Show ticket type distribution for Astana office",
            scope={"run_id": seeded["run_1"], "office": "Astana"},
        )

        assert response["kind"] == "result"
        assert response["scope_applied"]["office"] == "Астана"
        assert response["filters"]["office_names"] == ["Астана"]
        assert response["filters"]["run_id"] == seeded["run_1"]
    finally:
        session.close()
