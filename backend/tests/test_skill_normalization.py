from __future__ import annotations

from backend.services.ingestion import split_skills


def test_split_skills_normalizes_aliases_and_case() -> None:
    skills = split_skills(" vip ; en , english | KAZ / ru ")
    assert skills == ["VIP", "ENG", "KZ", "RU"]


def test_split_skills_deduplicates_and_ignores_empty_tokens() -> None:
    skills = split_skills("ENG,, en ; VIP ; vip ;  ")
    assert skills == ["ENG", "VIP"]

