from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

try:
    from openai import OpenAI as OpenAIClient
except ModuleNotFoundError:  # pragma: no cover - optional in local tests
    OpenAIClient = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIType
else:  # pragma: no cover - typing fallback for missing package
    OpenAIType = Any

from backend.core.config import Settings
from backend.schemas.ai import AIResult

ALLOWED_TYPES = {
    "Жалоба",
    "Смена данных",
    "Консультация",
    "Претензия",
    "Неработоспособность приложения",
    "Мошеннические действия",
    "Спам",
}
ALLOWED_TONES = {"Позитивный", "Нейтральный", "Негативный"}
ALLOWED_LANGUAGES = {"KZ", "ENG", "RU"}

DEFAULT_TYPE = "Консультация"
DEFAULT_TONE = "Нейтральный"
DEFAULT_PRIORITY = 5
DEFAULT_LANGUAGE = "RU"
SUMMARY_MAX_CHARS = 240
RECOMMENDATION_MAX_CHARS = 240
DEFAULT_RECOMMENDATION = "Рекомендуется уточнить детали и выполнить стандартную проверку по регламенту."
DEFAULT_SUMMARY = "Клиентское обращение требует обработки менеджером."

LOGGER = logging.getLogger("fire.ai")


@dataclass
class AIEnrichmentService:
    settings: Settings

    def __post_init__(self) -> None:
        self.client: OpenAIType | None = None
        if self.settings.openai_api_key and OpenAIClient is not None:
            self.client = OpenAIClient(api_key=self.settings.openai_api_key, timeout=self.settings.openai_timeout_seconds)

    def analyze(self, ticket: dict[str, str]) -> AIResult:
        text = (ticket.get("Описание") or "").strip()
        started = time.perf_counter()
        if not self.client:
            result = self._fallback(text)
            LOGGER.info(
                "ai_analysis_completed",
                extra={"provider": "fallback", "duration_ms": round((time.perf_counter() - started) * 1000, 2)},
            )
            return result

        prompt = (
            "Ты классификатор обращений. Верни JSON с ключами: "
            "ticket_type, tone, priority, language, summary, recommendation. "
            f"ticket_type только из: {sorted(ALLOWED_TYPES)}. "
            f"tone только из: {sorted(ALLOWED_TONES)}. "
            "priority целое от 1 до 10. language только KZ/ENG/RU, если не уверен RU. "
            "summary строго 1-2 предложения. recommendation краткая рекомендация для менеджера. "
            f"Текст обращения: {text!r}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            payload = response.choices[0].message.content or "{}"
            data = json.loads(payload)
            if not isinstance(data, dict):
                result = self._fallback(text)
                LOGGER.warning(
                    "ai_analysis_invalid_payload",
                    extra={"provider": "openai", "duration_ms": round((time.perf_counter() - started) * 1000, 2)},
                )
                return result
            result = self._normalize(data, text)
            LOGGER.info(
                "ai_analysis_completed",
                extra={"provider": "openai", "duration_ms": round((time.perf_counter() - started) * 1000, 2)},
            )
            return result
        except Exception as exc:  # pragma: no cover - depends on external API
            LOGGER.warning(
                "openai_analysis_failed",
                extra={"error": str(exc), "duration_ms": round((time.perf_counter() - started) * 1000, 2)},
            )
            return self._fallback(text)

    def _normalize(self, data: dict, source_text: str) -> AIResult:
        ticket_type = data.get("ticket_type") if data.get("ticket_type") in ALLOWED_TYPES else DEFAULT_TYPE
        tone = data.get("tone")
        if tone not in ALLOWED_TONES:
            # backward compatibility if model still returns sentiment key
            sentiment = data.get("sentiment")
            tone = sentiment if sentiment in ALLOWED_TONES else DEFAULT_TONE

        try:
            priority = int(data.get("priority", DEFAULT_PRIORITY))
        except (TypeError, ValueError):
            priority = DEFAULT_PRIORITY
        if priority < 1 or priority > 10:
            priority = DEFAULT_PRIORITY

        language = data.get("language") if data.get("language") in ALLOWED_LANGUAGES else DEFAULT_LANGUAGE

        summary = self._normalize_summary(str(data.get("summary", "")).strip(), source_text)
        recommendation = self._normalize_recommendation(str(data.get("recommendation", "")).strip())

        return AIResult(
            ticket_type=ticket_type,
            tone=tone,
            priority=priority,
            language=language,
            summary=summary,
            recommendation=recommendation,
        )

    def _fallback(self, source_text: str) -> AIResult:
        return AIResult(
            ticket_type=DEFAULT_TYPE,
            tone=DEFAULT_TONE,
            priority=DEFAULT_PRIORITY,
            language=DEFAULT_LANGUAGE,
            summary=self._normalize_summary("", source_text),
            recommendation=self._normalize_recommendation(""),
        )

    def _normalize_summary(self, summary: str, source_text: str) -> str:
        value = summary.strip()
        if not value:
            value = self._build_summary_fallback(source_text)

        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", value) if part.strip()]
        if not sentences:
            sentences = [self._build_summary_fallback(source_text)]

        compact = " ".join(sentences[:2]).strip()
        if not compact:
            compact = self._build_summary_fallback(source_text)

        compact = compact[:SUMMARY_MAX_CHARS].strip()
        if compact and compact[-1] not in ".!?":
            compact += "."
        return compact

    def _build_summary_fallback(self, source_text: str) -> str:
        source = re.sub(r"\s+", " ", source_text or "").strip()
        if not source:
            return DEFAULT_SUMMARY

        snippet = source[:160].strip()
        if len(source) > 160:
            snippet += "..."
        return f"Клиент обратился с запросом: {snippet}."

    def _normalize_recommendation(self, recommendation: str) -> str:
        value = re.sub(r"\s+", " ", recommendation or "").strip()
        if not value:
            value = DEFAULT_RECOMMENDATION
        value = value[:RECOMMENDATION_MAX_CHARS].strip()
        if value and value[-1] not in ".!?":
            value += "."
        return value
