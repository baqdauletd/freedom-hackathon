from __future__ import annotations

from backend.services.routing import choose_office, filter_eligible_managers


class DummyGeocoder:
    def is_foreign(self, country: str | None) -> bool:
        return (country or "").lower() not in {"казахстан", "kz", "kazakhstan"}

    def has_enough_address(self, row: dict[str, str]) -> bool:
        return bool(row.get("Город") and row.get("Улица") and row.get("Дом") and row.get("Страна"))

    def build_address(self, row: dict[str, str]) -> str:
        return "dummy"

    def geocode(self, address: str):
        return (51.0, 71.0)


def test_vip_priority_requires_vip_skill() -> None:
    managers = [
        {"full_name": "A", "position": "Главный специалист", "skills": ["VIP", "ENG"], "current_load": 0},
        {"full_name": "B", "position": "Специалист", "skills": ["ENG"], "current_load": 0},
    ]

    eligible = filter_eligible_managers("VIP", "Консультация", "RU", managers)
    assert [manager["full_name"] for manager in eligible] == ["A"]


def test_change_data_requires_glav_spec() -> None:
    managers = [
        {"full_name": "A", "position": "Главный спец", "skills": ["VIP"], "current_load": 0},
        {"full_name": "B", "position": "Специалист", "skills": ["VIP"], "current_load": 0},
    ]

    eligible = filter_eligible_managers("Mass", "Смена данных", "RU", managers)
    assert [manager["full_name"] for manager in eligible] == ["A"]


def test_language_requires_matching_skill() -> None:
    managers = [
        {"full_name": "A", "position": "Специалист", "skills": ["ENG"], "current_load": 0},
        {"full_name": "B", "position": "Специалист", "skills": ["KZ"], "current_load": 0},
    ]

    eligible = filter_eligible_managers("Mass", "Консультация", "KZ", managers)
    assert [manager["full_name"] for manager in eligible] == ["B"]


def test_unknown_or_foreign_is_split_50_50() -> None:
    offices = [
        {"office": "Астана", "latitude": 51.1694, "longitude": 71.4491},
        {"office": "Алматы", "latitude": 43.2389, "longitude": 76.8897},
    ]
    geocoder = DummyGeocoder()

    ticket = {"Страна": "Germany", "Город": "Berlin", "Улица": "X", "Дом": "1"}

    decisions = [
        choose_office(ticket, offices, geocoder, ticket_index=index, compliance_mode=True, enable_geocode=True).office_name
        for index in range(6)
    ]

    assert decisions.count("Астана") == 3
    assert decisions.count("Алматы") == 3
