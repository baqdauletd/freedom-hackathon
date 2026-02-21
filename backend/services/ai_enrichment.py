from __future__ import annotations

import json
import logging
import re
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
DEFAULT_RECOMMENDATION = "Проверьте обращение и свяжитесь с клиентом для уточнения деталей."

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
        if not self.client:
            return self._fallback(text)

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
                return self._fallback(text)
            return self._normalize(data, text)
        except Exception as exc:  # pragma: no cover - depends on external API
            LOGGER.warning("openai_analysis_failed", extra={"error": str(exc)})
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
        recommendation = str(data.get("recommendation", "")).strip() or DEFAULT_RECOMMENDATION

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
            recommendation=DEFAULT_RECOMMENDATION,
        )

    def _normalize_summary(self, summary: str, source_text: str) -> str:
        value = summary.strip()
        if not value:
            source = source_text.strip()
            if source:
                value = source[:180].strip()
                if len(source) > 180:
                    value += "..."
            else:
                value = "Клиентское обращение требует обработки менеджером."

        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", value) if part.strip()]
        if not sentences:
            return "Клиентское обращение требует обработки менеджером."

        compact = " ".join(sentences[:2])
        if compact and compact[-1] not in ".!?":
            compact += "."
        return compact
