"""LLM slot extraction for Amharic / Afaan Oromoo free text (Phase U2, item 1).

The deterministic extractor in ``slot_extraction`` reads English (and the
translated quick-reply protocol sentences in every language). Free text in
``am``/``om`` cannot be read by rules, so — **only when ``OPENAI_API_KEY`` is
set** — one structured-JSON call maps the latest message onto the same
canonical data-contract values (``practice_family``, ``indicator``, a place
name, coordinates, a crop). Nothing the model returns is trusted blindly:
every value is validated against the enumerations, coordinates against the
Ethiopia bounds, and place names go through the offline gazetteer. Without a
key the chat steers the user to the quick replies / Advisor (catalogued
message ``clarify.use_advisor``) instead of guessing.

Doctrine: the LLM never touches a number the ML model owns — it only reads
the user's intent. English stays on the rule-based parser.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.i18n import LANGUAGE_NAMES
from app.services import slot_extraction as se
from app.services.geocode import geocode_place
from app.services.openai_chat import (
    OPENAI_CHAT_COMPLETIONS_URL,
    OPENAI_CHAT_MODEL,
    make_client,
)
from app.services.recommender_service import (
    INDICATORS,
    LAT_BOUNDS,
    LON_BOUNDS,
    PRACTICE_FAMILIES,
)

logger = logging.getLogger(__name__)

FIELDS: tuple[str, ...] = (
    "practice_family",
    "indicator",
    "place_name",
    "lat",
    "lon",
    "crop_type",
    "is_followup",
    "wants_advice",
)


def needs_llm(message: str, language: str, slots: se.ChatSlots) -> bool:
    """True for free text in a non-English language the rules could not read.

    Quick-reply chips arrive with a structured ``hint`` or as a protocol
    sentence; both are read deterministically and never need the model.
    """
    if language == "en":
        return False
    if slots.source in ("hint", "protocol"):
        return False
    return bool((message or "").strip())


def crop_type_vocabulary() -> list[str]:
    """Dataset crop types for the prompt (falls back to the extractor's short list)."""
    try:
        from app.services import recommender_service as svc

        return svc.crop_types()
    except Exception:  # pragma: no cover - artefacts missing in a bare checkout
        return [c.title() for c in se._CROPS]


def build_prompt(message: str, language: str, crop_types: list[str]) -> list[dict[str, str]]:
    """The one-shot extraction prompt (pure; asserted in tests)."""
    name = LANGUAGE_NAMES.get(language, language)
    system = (
        "You extract structured fields from a farmer's chat message written in "
        f"{name}. Return ONLY a JSON object with exactly these keys: "
        f"{', '.join(FIELDS)}.\n"
        "Rules:\n"
        f"- practice_family: one of {json.dumps(PRACTICE_FAMILIES)} or null.\n"
        f"- indicator: one of {json.dumps(INDICATORS)} or null (the outcome the farmer "
        "wants to change; 'soil loss' covers erosion, 'SOM content' soil organic matter, "
        "'biomass yield' fodder/forage).\n"
        "- place_name: the Ethiopian town or area the farmer names, transliterated into "
        "Latin letters (e.g. 'Debre Birhan', 'Hawassa'), or null.\n"
        "- lat, lon: decimal degrees if the message states coordinates, else null.\n"
        f"- crop_type: the English crop name from this list if one is named, else null: "
        f"{json.dumps(crop_types)}.\n"
        "- is_followup: true if the message asks why/how/for evidence about an earlier answer.\n"
        "- wants_advice: true if the farmer is asking for practice recommendations.\n"
        "Never guess a value that is not stated; use null. Never invent numbers."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": message},
    ]


async def call_openai_json(messages: list[dict[str, str]], settings: Any) -> dict[str, Any]:
    """One JSON-mode completion. Monkeypatched in tests; never called without a key."""
    client = make_client(settings.openai_api_key, settings.openai_timeout_seconds)
    async with client:
        resp = await client.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            json={
                "model": OPENAI_CHAT_MODEL,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"].get("content") or "{}"
    parsed = json.loads(content)
    return parsed if isinstance(parsed, dict) else {}


def validate(raw: dict[str, Any], crop_types: list[str]) -> dict[str, Any]:
    """Keep only values that exist in the data contract; everything else → None."""
    out: dict[str, Any] = {k: None for k in FIELDS}
    fam = raw.get("practice_family")
    out["practice_family"] = fam if fam in PRACTICE_FAMILIES else None
    ind = raw.get("indicator")
    out["indicator"] = ind if ind in INDICATORS else None
    lat, lon = raw.get("lat"), raw.get("lon")
    if (
        isinstance(lat, (int, float))
        and isinstance(lon, (int, float))
        and not isinstance(lat, bool)
        and not isinstance(lon, bool)
        and LAT_BOUNDS[0] <= float(lat) <= LAT_BOUNDS[1]
        and LON_BOUNDS[0] <= float(lon) <= LON_BOUNDS[1]
    ):
        out["lat"], out["lon"] = float(lat), float(lon)
    place = raw.get("place_name")
    if isinstance(place, str) and place.strip():
        out["place_name"] = place.strip()[:120]
    crop = raw.get("crop_type")
    if isinstance(crop, str) and crop.strip():
        wanted = crop.strip().lower()
        for c in crop_types:
            if c.lower() == wanted:
                out["crop_type"] = c
                break
    out["is_followup"] = bool(raw.get("is_followup", False))
    out["wants_advice"] = bool(raw.get("wants_advice", True))
    return out


async def enrich_with_llm(
    slots: se.ChatSlots, message: str, language: str, settings: Any
) -> se.ChatSlots:
    """Fill what the rules missed from one validated LLM reading of the message."""
    crop_types = crop_type_vocabulary()
    try:
        raw = await call_openai_json(build_prompt(message, language, crop_types), settings)
    except Exception as exc:  # network, quota, malformed JSON — degrade to the rules
        logger.info("LLM slot extraction skipped: %s", exc)
        return slots
    data = validate(raw, crop_types)
    slots.llm_used = True
    slots.source = "llm"
    if data["practice_family"]:
        slots.practice_family = data["practice_family"]
        slots.confidence["practice_family"] = "medium"
    if data["indicator"]:
        slots.indicator = data["indicator"]
        slots.confidence["indicator"] = "medium"
    if data["lat"] is not None:
        slots.lat, slots.lon = data["lat"], data["lon"]
        slots.place_name = None
        slots.confidence["location"] = "high"
        slots.geocode_source = "coordinates"
    elif data["place_name"] and (slots.lat is None or slots.lon is None):
        hit = geocode_place(data["place_name"], allow_network=False)
        if hit:
            slots.lat, slots.lon = hit.lat, hit.lon
            slots.place_name = hit.name
            slots.confidence["location"] = "medium"
            slots.geocode_source = hit.source
            if "location" not in slots.inferred:
                slots.inferred.append("location")
    if data["crop_type"]:
        slots.crop_type = data["crop_type"]
    slots.is_followup = data["is_followup"]
    slots.wants_advice = data["wants_advice"] or not slots.is_followup
    return se.finalize_slots(slots, message)
