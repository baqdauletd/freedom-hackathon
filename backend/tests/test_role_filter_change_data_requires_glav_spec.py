from __future__ import annotations

from backend.services.routing import filter_eligible_managers


def test_change_data_accepts_only_glav_spec_variants() -> None:
    managers = [
        {"id": 1, "full_name": "Spec", "position": "Спец", "skills": ["RU"], "current_load": 0},
        {"id": 2, "full_name": "Lead", "position": "Ведущий специалист", "skills": ["RU"], "current_load": 0},
        {"id": 3, "full_name": "Glav1", "position": "Глав спец", "skills": ["RU"], "current_load": 0},
        {"id": 4, "full_name": "Glav2", "position": "Главный специалист", "skills": ["RU"], "current_load": 0},
        {"id": 5, "full_name": "Glav3", "position": "ГЛАВНЫЙСПЕЦИАЛИСТ", "skills": ["RU"], "current_load": 0},
        {"id": 6, "full_name": "Glav4", "position": "Глав. спец", "skills": ["RU"], "current_load": 0},
    ]

    eligible = filter_eligible_managers("Mass", "Смена данных", "RU", managers)

    assert [manager["full_name"] for manager in eligible] == ["Glav1", "Glav2", "Glav3", "Glav4"]
