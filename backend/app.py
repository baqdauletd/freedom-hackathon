import os
import csv
import json
import time
import math
import io
from typing import Dict, Tuple, List, Any, Optional

import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ENABLE_GEOCODE = os.getenv("ENABLE_GEOCODE", "false").lower() in {"1", "true", "yes"}

TICKETS_CSV = os.getenv("TICKETS_CSV", "tickets.csv")
MANAGERS_CSV = os.getenv("MANAGERS_CSV", "managers.csv")
BUSINESS_UNITS_CSV = os.getenv("BUSINESS_UNITS_CSV", "business_units.csv")

ALLOWED_TYPES = {
    "Жалоба",
    "Смена данных",
    "Консультация",
    "Претензия",
    "Неработоспособность приложения",
    "Мошеннические действия",
    "Спам",
}
ALLOWED_SENTIMENTS = {"Позитивный", "Нейтральный", "Негативный"}
ALLOWED_LANGUAGES = {"KZ", "ENG", "RU"}

DEFAULT_AI = {
    "ticket_type": "Консультация",
    "sentiment": "Нейтральный",
    "priority": 5,
    "language": "RU",
    "summary": "",
    "recommendation": "",
}

# ---------- Helpers ----------

KEY_ALIASES = {
    "Описание ": "Описание",
    "Описание": "Описание",
    "Текст обращения": "Текст обращения",
    "GUID клиента": "ID",
    "ID": "ID",
    "Область": "Регион",
    "Регион": "Регион",
    "Населённый пункт": "Город",
    "Населенный пункт": "Город",
    "Город": "Город",
    "Должность ": "Должность",
    "Должность": "Должность",
    "Адрес": "Адрес",
}


def normalize_key(key: str) -> str:
    k = (key or "").strip().lstrip("\ufeff")
    return KEY_ALIASES.get(k, k)


def normalize_row(row: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, value in row.items():
        nk = normalize_key(key)
        out[nk] = value
    return out


def load_csv(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [normalize_row(dict(row)) for row in reader]


def load_csv_bytes(data: bytes) -> List[Dict[str, str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return [normalize_row(dict(row)) for row in reader]


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_skill_list(raw: str) -> List[str]:
    if not raw:
        return []
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    return [p for p in parts if p]


def build_address(row: Dict[str, str], prefix: str = "") -> str:
    def get(key: str) -> str:
        return (row.get(prefix + key) or "").strip()

    if row.get("Адрес"):
        return row.get("Адрес", "").strip()
    parts = [get("Страна"), get("Регион"), get("Город"), get("Улица"), get("Дом")]
    return ", ".join([p for p in parts if p])


def has_min_address_fields(row: Dict[str, str], prefix: str = "") -> bool:
    def get(key: str) -> str:
        return (row.get(prefix + key) or "").strip()

    if row.get("Адрес"):
        return True
    return bool(get("Страна") and get("Город") and get("Улица") and get("Дом"))


def is_kazakhstan(country: str) -> bool:
    c = (country or "").strip().lower()
    return c in {"казахстан", "kazakhstan", "kz", "қазақстан"}


def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    x = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(x), math.sqrt(1 - x))


def openai_client() -> Optional[OpenAI]:
    if not OPENAI_API_KEY:
        return None
    return OpenAI()


def validate_ai(data: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(DEFAULT_AI)

    if data.get("ticket_type") in ALLOWED_TYPES:
        out["ticket_type"] = data["ticket_type"]
    if data.get("sentiment") in ALLOWED_SENTIMENTS:
        out["sentiment"] = data["sentiment"]

    pr = safe_int(data.get("priority"), DEFAULT_AI["priority"])
    if 1 <= pr <= 10:
        out["priority"] = pr

    if data.get("language") in ALLOWED_LANGUAGES:
        out["language"] = data["language"]

    if isinstance(data.get("summary"), str):
        out["summary"] = data["summary"].strip()
    if isinstance(data.get("recommendation"), str):
        out["recommendation"] = data["recommendation"].strip()

    return out


def call_openai(ticket: Dict[str, str]) -> Dict[str, Any]:
    client = openai_client()
    if client is None:
        return dict(DEFAULT_AI)

    user_text = ticket.get("Текст обращения") or ticket.get("Описание") or ""
    prompt = (
        "Ты классификатор обращений. Верни строго JSON без markdown с ключами: "
        "ticket_type, sentiment, priority, language, summary, recommendation. "
        f"ticket_type из списка {sorted(ALLOWED_TYPES)}. "
        f"sentiment из списка {sorted(ALLOWED_SENTIMENTS)}. "
        "priority — целое 1..10. language из списка [KZ, ENG, RU], по умолчанию RU. "
        "summary — 1-2 предложения. recommendation — следующее действие. "
        f"Текст обращения: {user_text!r}"
    )

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        if not isinstance(data, dict):
            return dict(DEFAULT_AI)
        return validate_ai(data)
    except Exception:
        return dict(DEFAULT_AI)


class GeoCoder:
    def __init__(self) -> None:
        self.cache: Dict[str, Optional[Tuple[float, float]]] = {}
        self.last_call = 0.0
        self.client = httpx.Client(timeout=10.0, headers={"User-Agent": "FIRE-Hackathon/0.1"})

    def geocode(self, address: str) -> Optional[Tuple[float, float]]:
        address = address.strip()
        if not address:
            return None
        if address in self.cache:
            return self.cache[address]

        # Be polite to Nominatim (1 req/sec)
        elapsed = time.monotonic() - self.last_call
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        try:
            r = self.client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                self.cache[address] = (lat, lon)
            else:
                self.cache[address] = None
        except Exception:
            self.cache[address] = None

        self.last_call = time.monotonic()
        return self.cache[address]


def choose_office(
    ticket: Dict[str, str],
    offices: List[Dict[str, Any]],
    geocoder: GeoCoder,
    ticket_index: int,
    use_geocode: bool,
) -> str:
    country = (ticket.get("Страна") or "").strip()
    if not is_kazakhstan(country) or not has_min_address_fields(ticket):
        return "Астана" if ticket_index % 2 == 0 else "Алматы"

    if not use_geocode:
        city = (ticket.get("Город") or "").strip()
        if city and any((o.get("Офис") or "").strip() == city for o in offices):
            return city
        return "Астана" if ticket_index % 2 == 0 else "Алматы"

    ticket_address = build_address(ticket)
    t_coords = geocoder.geocode(ticket_address)
    if not t_coords:
        return "Астана" if ticket_index % 2 == 0 else "Алматы"

    best_office = None
    best_dist = None
    for office in offices:
        o_coords = office.get("_coords")
        if not o_coords:
            continue
        dist = haversine_km(t_coords, o_coords)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_office = office.get("Офис") or office.get("Название") or ""

    if not best_office:
        return "Астана" if ticket_index % 2 == 0 else "Алматы"
    return best_office


def eligible_managers(ticket: Dict[str, Any], managers: List[Dict[str, Any]], office: str) -> List[Dict[str, Any]]:
    seg = (ticket.get("Сегмент клиента") or "").strip()
    need_vip = seg in {"VIP", "Priority"}
    t_type = ticket.get("ticket_type")
    lang = ticket.get("language")

    eligible = []
    for m in managers:
        if (m.get("Офис") or "").strip() != office:
            continue

        skills = normalize_skill_list(m.get("Навыки") or "")
        position = (m.get("Должность") or "").strip()
        position_norm = position.replace(".", "").lower()

        if need_vip and "VIP" not in skills:
            continue
        if t_type == "Смена данных" and position_norm not in {
            "главный специалист",
            "главный спец",
            "глав спец",
            "главныйспециалист",
        }:
            continue
        if lang in {"KZ", "ENG"} and lang not in skills:
            continue

        eligible.append(m)

    return eligible




def pick_two_lowest_load(managers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def load(m: Dict[str, Any]) -> int:
        return safe_int(m.get("Количество обращений в работе"), 0)

    sorted_ms = sorted(managers, key=lambda m: (load(m), (m.get("ФИО") or "")))
    return sorted_ms[:2]


def assign_manager(two: List[Dict[str, Any]], ticket_index: int) -> Optional[Dict[str, Any]]:
    if not two:
        return None
    if len(two) == 1:
        return two[0]
    return two[ticket_index % 2]


def prepare_offices(business_units: List[Dict[str, str]], geocoder: GeoCoder) -> List[Dict[str, Any]]:
    offices = []
    for row in business_units:
        office = dict(row)
        lat = row.get("Широта")
        lon = row.get("Долгота")
        coords = None
        if lat and lon:
            try:
                coords = (float(lat), float(lon))
            except Exception:
                coords = None
        if not coords:
            addr = build_address(row)
            coords = geocoder.geocode(addr)
        office["_coords"] = coords
        offices.append(office)
    return offices


app = FastAPI(title="FIRE Prototype")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/route")
def route() -> List[Dict[str, Any]]:
    tickets = load_csv(TICKETS_CSV)
    managers = load_csv(MANAGERS_CSV)
    business_units = load_csv(BUSINESS_UNITS_CSV)

    geocoder = GeoCoder()
    offices = prepare_offices(business_units, geocoder)

    results = []

    for idx, t in enumerate(tickets):
        ai = call_openai(t)
        t_enriched = dict(t)
        t_enriched.update(ai)

        office = choose_office(t_enriched, offices, geocoder, idx, ENABLE_GEOCODE)
        eligible = eligible_managers(t_enriched, managers, office)
        two = pick_two_lowest_load(eligible)
        assigned = assign_manager(two, idx)

        result = {
            "ticket_id": t.get("ID") or t.get("ticket_id") or idx,
            "ticket_index": idx,
            "ticket_type": ai["ticket_type"],
            "sentiment": ai["sentiment"],
            "priority": ai["priority"],
            "language": ai["language"],
            "summary": ai["summary"],
            "recommendation": ai["recommendation"],
            "office": office,
            "selected_managers": [m.get("ФИО") or m.get("ID") for m in two],
            "assigned_manager": (assigned.get("ФИО") or assigned.get("ID")) if assigned else None,
        }
        results.append(result)

    return results


@app.post("/route/upload")
async def route_upload(
    tickets: UploadFile = File(...),
    managers: UploadFile = File(...),
    business_units: UploadFile = File(...),
) -> List[Dict[str, Any]]:
    if tickets.content_type is None or managers.content_type is None or business_units.content_type is None:
        raise HTTPException(status_code=400, detail="Missing file content types")

    tickets_data = load_csv_bytes(await tickets.read())
    managers_data = load_csv_bytes(await managers.read())
    business_units_data = load_csv_bytes(await business_units.read())

    geocoder = GeoCoder()
    offices = prepare_offices(business_units_data, geocoder)

    results = []

    for idx, t in enumerate(tickets_data):
        ai = call_openai(t)
        t_enriched = dict(t)
        t_enriched.update(ai)

        office = choose_office(t_enriched, offices, geocoder, idx, ENABLE_GEOCODE)
        eligible = eligible_managers(t_enriched, managers_data, office)
        two = pick_two_lowest_load(eligible)
        assigned = assign_manager(two, idx)

        result = {
            "ticket_id": t.get("ID") or t.get("ticket_id") or idx,
            "ticket_index": idx,
            "ticket_type": ai["ticket_type"],
            "sentiment": ai["sentiment"],
            "priority": ai["priority"],
            "language": ai["language"],
            "summary": ai["summary"],
            "recommendation": ai["recommendation"],
            "office": office,
            "selected_managers": [m.get("ФИО") or m.get("ID") for m in two],
            "assigned_manager": (assigned.get("ФИО") or assigned.get("ID")) if assigned else None,
        }
        results.append(result)

    return results
