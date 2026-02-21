from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass


class CSVValidationError(ValueError):
    def __init__(self, dataset: str, message: str) -> None:
        super().__init__(f"{dataset}: {message}")
        self.dataset = dataset
        self.message = message


KEY_ALIASES = {
    "GUID клиента": "ID",
    "ID": "ID",
    "Пол": "Пол клиента",
    "Пол клиента": "Пол клиента",
    "Дата рождения": "Дата рождения",
    "Сегмент": "Сегмент клиента",
    "Сегмент клиента": "Сегмент клиента",
    "Описание ": "Описание",
    "Описание": "Описание",
    "Текст обращения": "Описание",
    "Вложения": "Вложения",
    "Страна": "Страна",
    "Область": "Регион",
    "Регион": "Регион",
    "Населённый пункт": "Город",
    "Населенный пункт": "Город",
    "Город": "Город",
    "Улица": "Улица",
    "Дом": "Дом",
    "ФИО": "ФИО",
    "Должность ": "Должность",
    "Должность": "Должность",
    "Офис": "Офис",
    "Бизнес-единица": "Офис",
    "Навыки": "Навыки",
    "Количество обращений в работе": "Количество обращений в работе",
    "Адрес": "Адрес",
    "Широта": "Широта",
    "Долгота": "Долгота",
}

REQUIRED_TICKET_HEADERS = {
    "ID",
    "Пол клиента",
    "Дата рождения",
    "Сегмент клиента",
    "Описание",
    "Вложения",
    "Страна",
    "Регион",
    "Город",
    "Улица",
    "Дом",
}

REQUIRED_MANAGER_HEADERS = {
    "ФИО",
    "Должность",
    "Офис",
    "Навыки",
    "Количество обращений в работе",
}

REQUIRED_BUSINESS_UNIT_HEADERS = {
    "Офис",
    "Адрес",
}

ALLOWED_SEGMENTS = {"Mass", "VIP", "Priority"}
ALLOWED_POSITIONS = {
    "спец",
    "специалист",
    "ведущий спец",
    "ведущий специалист",
    "глав спец",
    "главный спец",
    "главный специалист",
}


@dataclass
class ParsedCSV:
    headers: list[str]
    rows: list[dict[str, str]]


def normalize_key(key: str) -> str:
    return KEY_ALIASES.get((key or "").strip().lstrip("\ufeff"), (key or "").strip().lstrip("\ufeff"))


def _read_csv_text(text: str) -> ParsedCSV:
    reader = csv.DictReader(io.StringIO(text))
    raw_headers = reader.fieldnames or []
    headers = [normalize_key(h) for h in raw_headers if h]

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        row: dict[str, str] = {}
        for key, value in raw_row.items():
            row[normalize_key(key or "")] = (value or "").strip()
        rows.append(row)

    return ParsedCSV(headers=headers, rows=rows)


def parse_csv_bytes(data: bytes) -> ParsedCSV:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    return _read_csv_text(text)


def parse_csv_path(path: str) -> ParsedCSV:
    with open(path, "r", encoding="utf-8") as file:
        return _read_csv_text(file.read())


def _validate_headers(dataset: str, headers: list[str], required: set[str]) -> None:
    missing = sorted(required - set(headers))
    if missing:
        raise CSVValidationError(dataset, f"Missing required headers: {', '.join(missing)}")


def _validate_ticket_rows(rows: list[dict[str, str]]) -> None:
    first_seen_row_by_ticket_id: dict[str, int] = {}
    duplicates: list[tuple[str, int, int]] = []

    for idx, row in enumerate(rows, start=1):
        ticket_id = (row.get("ID") or "").strip()
        if not ticket_id:
            raise CSVValidationError("tickets", f"Row {idx}: empty ID/GUID")

        if ticket_id in first_seen_row_by_ticket_id:
            duplicates.append((ticket_id, first_seen_row_by_ticket_id[ticket_id], idx))
        else:
            first_seen_row_by_ticket_id[ticket_id] = idx

        segment = row.get("Сегмент клиента", "")
        if segment not in ALLOWED_SEGMENTS:
            raise CSVValidationError("tickets", f"Row {idx}: invalid segment '{segment}'")

    if duplicates:
        preview = "; ".join(
            f"{ticket_id} (rows {first_row} and {duplicate_row})"
            for ticket_id, first_row, duplicate_row in duplicates[:5]
        )
        extra = " ..." if len(duplicates) > 5 else ""
        raise CSVValidationError("tickets", f"Duplicate ticket IDs are not allowed: {preview}{extra}")


def _validate_manager_rows(rows: list[dict[str, str]]) -> None:
    for idx, row in enumerate(rows, start=1):
        if not row.get("ФИО"):
            raise CSVValidationError("managers", f"Row {idx}: empty manager name")

        position = (row.get("Должность") or "").replace(".", "").strip().lower()
        if position not in ALLOWED_POSITIONS:
            raise CSVValidationError("managers", f"Row {idx}: invalid position '{row.get('Должность')}'")

        try:
            load = int(row.get("Количество обращений в работе") or "0")
        except ValueError as exc:
            raise CSVValidationError("managers", f"Row {idx}: load must be an integer") from exc

        if load < 0:
            raise CSVValidationError("managers", f"Row {idx}: load must be >= 0")


def _validate_business_unit_rows(rows: list[dict[str, str]]) -> None:
    for idx, row in enumerate(rows, start=1):
        if not row.get("Офис"):
            raise CSVValidationError("business_units", f"Row {idx}: empty office")
        if not row.get("Адрес"):
            raise CSVValidationError("business_units", f"Row {idx}: empty address")


def validate_tickets(parsed: ParsedCSV) -> list[dict[str, str]]:
    _validate_headers("tickets", parsed.headers, REQUIRED_TICKET_HEADERS)
    _validate_ticket_rows(parsed.rows)
    return parsed.rows


def validate_managers(parsed: ParsedCSV) -> list[dict[str, str]]:
    _validate_headers("managers", parsed.headers, REQUIRED_MANAGER_HEADERS)
    _validate_manager_rows(parsed.rows)
    return parsed.rows


def validate_business_units(parsed: ParsedCSV) -> list[dict[str, str]]:
    _validate_headers("business_units", parsed.headers, REQUIRED_BUSINESS_UNIT_HEADERS)
    _validate_business_unit_rows(parsed.rows)
    return parsed.rows


def split_skills(raw: str) -> list[str]:
    if not raw:
        return []
    raw_parts = re.split(r"[;,/|]", raw)
    normalized: list[str] = []
    seen: set[str] = set()

    alias_map = {
        "EN": "ENG",
        "ENGLISH": "ENG",
        "ENG": "ENG",
        "KZ": "KZ",
        "KAZ": "KZ",
        "KAZAKH": "KZ",
        "KAZAKHSTAN": "KZ",
        "RU": "RU",
        "RUS": "RU",
        "RUSSIAN": "RU",
        "VIP": "VIP",
    }

    for part in raw_parts:
        token = re.sub(r"\s+", "", (part or "").strip()).upper()
        if not token:
            continue
        canonical = alias_map.get(token, token)
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)

    return normalized
