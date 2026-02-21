from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient

from backend.app import app


def test_missing_ticket_headers_returns_400() -> None:
    client = TestClient(app)

    tickets_csv = "ID,Сегмент клиента,Описание\n1,Mass,hello\n"  # missing many required columns
    managers_csv = (
        "ФИО,Должность,Офис,Навыки,Количество обращений в работе\n"
        "Менеджер 1,Главный специалист,Астана,VIP,0\n"
    )
    business_csv = "Офис,Адрес\nАстана,addr\n"

    response = client.post(
        "/route/upload",
        files={
            "tickets": ("tickets.csv", tickets_csv, "text/csv"),
            "managers": ("managers.csv", managers_csv, "text/csv"),
            "business_units": ("business_units.csv", business_csv, "text/csv"),
        },
    )

    assert response.status_code == 400
    assert "Missing required headers" in response.json()["detail"]
