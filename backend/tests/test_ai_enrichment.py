from __future__ import annotations

from backend.core.config import Settings
from backend.services.ai_enrichment import (
    AIEnrichmentService,
    DEFAULT_RECOMMENDATION,
    RECOMMENDATION_MAX_CHARS,
    SUMMARY_MAX_CHARS,
)


def _service() -> AIEnrichmentService:
    return AIEnrichmentService(Settings())


def test_normalize_missing_fields_uses_deterministic_fallbacks() -> None:
    service = _service()
    result = service._normalize({}, "Не работает мобильное приложение, ошибка авторизации")

    assert result.summary.startswith("Клиент обратился с запросом:")
    assert result.summary.endswith(".")
    assert result.recommendation == DEFAULT_RECOMMENDATION


def test_normalize_empty_strings_produces_non_empty_summary_and_recommendation() -> None:
    service = _service()
    result = service._normalize({"summary": "   ", "recommendation": "  "}, "   ")

    assert result.summary
    assert result.recommendation
    assert result.summary.endswith(".")
    assert result.recommendation.endswith(".")


def test_summary_is_limited_to_two_sentences() -> None:
    service = _service()
    result = service._normalize(
        {
            "summary": "Первое предложение. Второе предложение! Третье предложение? Четвертое.",
            "recommendation": "Проверить клиента.",
        },
        "source",
    )

    sentences = [part for part in result.summary.replace("!", ".").replace("?", ".").split(".") if part.strip()]
    assert len(sentences) <= 2


def test_very_long_summary_and_recommendation_are_truncated() -> None:
    service = _service()
    long_summary = "Очень длинный текст " * 80
    long_recommendation = "Рекомендация " * 80
    result = service._normalize(
        {"summary": long_summary, "recommendation": long_recommendation},
        "source text",
    )

    assert len(result.summary) <= SUMMARY_MAX_CHARS + 1
    assert len(result.recommendation) <= RECOMMENDATION_MAX_CHARS + 1
    assert result.summary.endswith(".")
    assert result.recommendation.endswith(".")

