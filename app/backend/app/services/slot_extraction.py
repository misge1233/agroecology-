"""Natural-language slot filling for CSA chat (challenge / objective / location).

This is the deterministic brain in front of the LLM: extract what the user already
said, geocode place names, infer clear challenge↔objective links, and say what is
still missing — so the model never invents practices or coordinates.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.geocode import GeocodeHit, geocode_text
from app.services.recommender_service import (
    INDICATORS,
    PRACTICE_FAMILIES,
    is_supported_family_indicator,
)

# Phrase → indicator (longer keys preferred).
INDICATOR_PHRASES: list[tuple[str, str]] = [
    ("increase crop yield", "yield"),
    ("increase yield", "yield"),
    ("raise yield", "yield"),
    ("higher yield", "yield"),
    ("crop yield", "yield"),
    ("biomass yield", "biomass yield"),
    ("increase biomass", "biomass yield"),
    ("fodder", "biomass yield"),
    ("forage", "biomass yield"),
    ("increase income", "income"),
    ("more income", "income"),
    ("profit", "income"),
    ("improve water use efficiency", "water use efficiency"),
    ("water use efficiency", "water use efficiency"),
    ("water efficiency", "water use efficiency"),
    ("use water better", "water use efficiency"),
    ("wue", "water use efficiency"),
    ("improve soil organic matter", "SOM content"),
    ("soil organic matter", "SOM content"),
    ("organic matter", "SOM content"),
    ("soil health", "SOM content"),
    ("reduce soil loss", "soil loss"),
    ("soil loss", "soil loss"),
    ("soil erosion", "soil loss"),
    ("cut erosion", "soil loss"),
    ("control erosion", "soil loss"),
    ("stop erosion", "soil loss"),
    ("prevent erosion", "soil loss"),
    ("erosion", "soil loss"),
    ("reduce runoff", "runoff"),
    ("runoff", "runoff"),
    ("yield", "yield"),
    ("income", "income"),
]

FAMILY_KEYWORDS: list[tuple[str, str]] = [
    ("erosion control and water management", "Erosion control and water management"),
    ("erosion control", "Erosion control and water management"),
    ("water management", "Erosion control and water management"),
    ("integrated soil fertility management", "Integrated soil fertility management"),
    ("soil fertility", "Integrated soil fertility management"),
    ("livestock production and management", "Livestock production and management"),
    ("livestock", "Livestock production and management"),
    ("agro-forestry and forest management", "Agro-forestry and forest management"),
    ("agroforestry", "Agro-forestry and forest management"),
    ("agro-forestry", "Agro-forestry and forest management"),
    ("forest management", "Agro-forestry and forest management"),
    ("crop production and management", "Crop production and management"),
    ("crop production", "Crop production and management"),
]

# Soft cues that strengthen a family guess (not enough alone for high confidence).
FAMILY_SOFT: dict[str, tuple[str, ...]] = {
    "Erosion control and water management": (
        "slope",
        "sloping",
        "sloped",
        "steep",
        "hillside",
        "gully",
        "bund",
        "terrace",
        "contour",
        "runoff",
        "erosion",
        "soil loss",
        "wash away",
        "washed away",
    ),
    "Integrated soil fertility management": (
        "fertil",
        "compost",
        "manure",
        "nutrient",
        "soil fertility",
    ),
    "Livestock production and management": (
        "livestock",
        "cattle",
        "goat",
        "sheep",
        "dairy",
        "herd",
        "fodder",
        "forage",
    ),
    "Agro-forestry and forest management": (
        "tree",
        "forest",
        "woodlot",
        "agroforest",
    ),
    "Crop production and management": (
        "planting",
        "sowing",
        "intercrop",
        "rotation",
        "mulch",
    ),
}

# When objective is clear, default challenge if user did not name one.
INDICATOR_DEFAULT_FAMILY: dict[str, str] = {
    "soil loss": "Erosion control and water management",
    "runoff": "Erosion control and water management",
    "water use efficiency": "Erosion control and water management",
    "SOM content": "Integrated soil fertility management",
    "biomass yield": "Livestock production and management",
    "income": "Crop production and management",
    "yield": "Crop production and management",
}

_COORD_PAIR_RE = re.compile(
    r"(?P<lat>-?\d{1,2}(?:\.\d+)?)\s*[,;\s]\s*(?P<lon>-?\d{1,2}(?:\.\d+)?)"
)
_FARM_AT_RE = re.compile(
    r"(?i)(?:farm|field|plot|location|pin)?\s*(?:is\s+)?(?:at|@)\s*"
    r"(?P<lat>-?\d{1,2}(?:\.\d+)?)\s*[,;]\s*(?P<lon>-?\d{1,2}(?:\.\d+)?)"
)
_CHALLENGE_PREFIX = re.compile(r"(?i)^my challenge is\s+(.+?)\.?\s*$")
_OBJECTIVE_PREFIX = re.compile(r"(?i)^my objective is to\s+(.+?)\.?\s*$")
_CROPS = (
    "maize",
    "teff",
    "wheat",
    "barley",
    "sorghum",
    "potato",
    "onion",
    "coffee",
    "bean",
    "chickpea",
    "lentil",
    "sesame",
    "rice",
)

_FOLLOWUP_RE = re.compile(
    r"(?i)\b(why|explain|how\s+sure|evidence|confidence|detail|because|"
    r"how\s+(?:do|to|can)|implement|apply|steps|alternativ|other\s+option|"
    r"instead|compare|better|else)\b"
)
_ADVICE_RE = re.compile(
    r"(?i)\b(recommend|suggest|what\s+(?:should|can)\s+i|help\s+me|"
    r"want\s+to|need\s+to|how\s+(?:do|can)\s+i|reduce|increase|improve|"
    r"practice|erosion|yield|soil|runoff|income|fodder)\b"
)


@dataclass
class ChatSlots:
    practice_family: str | None = None
    indicator: str | None = None
    lat: float | None = None
    lon: float | None = None
    place_name: str | None = None
    crop_type: str | None = None
    missing: list[str] = field(default_factory=list)
    inferred: list[str] = field(default_factory=list)
    confidence: dict[str, str] = field(default_factory=dict)
    is_followup: bool = False
    wants_advice: bool = False
    geocode_source: str | None = None

    @property
    def is_complete(self) -> bool:
        return (
            self.practice_family is not None
            and self.indicator is not None
            and self.lat is not None
            and self.lon is not None
        )

    def to_event(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_complete"] = self.is_complete
        return data


def _norm_match(text: str) -> str:
    """Lowercase and treat hyphens like spaces so 'water-use' == 'water use'."""
    t = (text or "").lower().replace("-", " ")
    t = re.sub(r"[/|,;:]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# UI labels (metadata) + short replies users paste after a clarifying ask.
_INDICATOR_LABELS: list[tuple[str, str]] = [
    ("increase crop yield", "yield"),
    ("increase biomass / fodder", "biomass yield"),
    ("increase biomass fodder", "biomass yield"),
    ("increase income", "income"),
    ("improve water use efficiency", "water use efficiency"),
    ("improve soil organic matter", "SOM content"),
    ("reduce soil loss / erosion", "soil loss"),
    ("reduce soil loss erosion", "soil loss"),
    ("reduce runoff", "runoff"),
]


def _indicator_from_text(text: str) -> tuple[str | None, str]:
    t = _norm_match(text)
    # Structured objective phrase: "My objective is to …"
    m = _OBJECTIVE_PREFIX.search(text.strip())
    if m:
        rest = _norm_match(m.group(1))
        for phrase, key in INDICATOR_PHRASES:
            if phrase in rest or rest == _norm_match(key):
                return key, "high"
        for label, key in _INDICATOR_LABELS:
            lab = _norm_match(label)
            if rest == lab or rest in lab or lab in rest:
                return key, "high"
        if rest in INDICATORS:
            return rest, "high"

    # Exact / near-exact short replies ("improve water-use efficiency").
    for label, key in _INDICATOR_LABELS:
        lab = _norm_match(label)
        if t == lab or t == _norm_match(key) or lab in t:
            return key, "high"

    best: tuple[int, str] | None = None
    for phrase, key in INDICATOR_PHRASES:
        p = _norm_match(phrase)
        if p and p in t:
            score = len(p)
            if best is None or score > best[0]:
                best = (score, key)
    if best:
        conf = "high" if best[0] >= 8 else "medium"
        return best[1], conf
    return None, "low"


def _family_from_text(text: str) -> tuple[str | None, str]:
    t = text.lower().strip()
    m = _CHALLENGE_PREFIX.search(t)
    if m:
        stated = m.group(1).strip()
        for fam in PRACTICE_FAMILIES:
            if fam.lower() == stated.lower():
                return fam, "high"
    for phrase, fam in FAMILY_KEYWORDS:
        if phrase in t:
            return fam, "high"
    # Soft keyword scoring.
    scores: dict[str, int] = {f: 0 for f in PRACTICE_FAMILIES}
    for fam, words in FAMILY_SOFT.items():
        for w in words:
            if w in t:
                scores[fam] += 1
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], PRACTICE_FAMILIES.index(kv[0])))
    if ranked[0][1] >= 2:
        return ranked[0][0], "medium"
    if ranked[0][1] == 1 and ranked[1][1] == 0:
        return ranked[0][0], "low"
    return None, "low"


def _coords_from_text(text: str) -> tuple[float, float] | None:
    m = _FARM_AT_RE.search(text) or _COORD_PAIR_RE.search(text)
    if not m:
        # Require at least one decimal so bare years aren't treated as coords.
        nums = re.findall(r"(-?\d+\.\d+)", text)
        if len(nums) >= 2:
            lat, lon = float(nums[0]), float(nums[1])
            if 3.3 <= lat <= 14.9 and 32.9 <= lon <= 48.2:
                return lat, lon
        return None
    lat, lon = float(m.group("lat")), float(m.group("lon"))
    if 3.3 <= lat <= 14.9 and 32.9 <= lon <= 48.2:
        return lat, lon
    return None


def _crop_from_text(text: str) -> str | None:
    t = text.lower()
    for c in _CROPS:
        if re.search(rf"\b{re.escape(c)}\b", t):
            return c.title()
    return None


def _resolve_family_indicator(
    family: str | None,
    indicator: str | None,
    family_conf: str | None,
    indicator_conf: str | None,
) -> tuple[str | None, str | None]:
    if not family or not indicator:
        return family, indicator
    if is_supported_family_indicator(family, indicator):
        return family, indicator
    # Prefer an explicit latest challenge/objective over a stale prior slot.
    rank = {"high": 3, "medium": 2, "inferred": 1, "prior": 0, "low": 0}
    f_rank = rank.get(family_conf or "", 0)
    i_rank = rank.get(indicator_conf or "", 0)
    if f_rank >= i_rank:
        return family, None
    return None, indicator


def extract_slots(
    message: str,
    history: list[dict[str, str]] | None = None,
    last_recommendation: dict[str, Any] | None = None,
    *,
    allow_network_geocode: bool = False,
) -> ChatSlots:
    """Merge NL extraction with prior query state."""
    history = history or []
    user_texts = [
        h.get("content") or ""
        for h in history
        if h.get("role") == "user" and (h.get("content") or "").strip()
    ]
    user_texts.append(message or "")
    corpus = "\n".join(user_texts)

    slots = ChatSlots()
    slots.is_followup = bool(_FOLLOWUP_RE.search(message or ""))
    slots.wants_advice = bool(_ADVICE_RE.search(message or "")) or not slots.is_followup

    # Seed from prior recommendation query.
    prior = (last_recommendation or {}).get("query") or {}
    if prior.get("practice_family") in PRACTICE_FAMILIES:
        slots.practice_family = prior["practice_family"]
        slots.confidence["practice_family"] = "prior"
    if prior.get("indicator") in INDICATORS:
        slots.indicator = prior["indicator"]
        slots.confidence["indicator"] = "prior"
    if isinstance(prior.get("lat"), (int, float)) and isinstance(prior.get("lon"), (int, float)):
        slots.lat = float(prior["lat"])
        slots.lon = float(prior["lon"])
        slots.confidence["location"] = "prior"
    if prior.get("crop_type"):
        slots.crop_type = str(prior["crop_type"])

    # Latest message overrides priors; earlier turns only fill gaps.
    latest_fam, latest_fconf = _family_from_text(message or "")
    if latest_fam:
        slots.practice_family = latest_fam
        slots.confidence["practice_family"] = latest_fconf
    latest_ind, latest_iconf = _indicator_from_text(message or "")
    if latest_ind:
        slots.indicator = latest_ind
        slots.confidence["indicator"] = latest_iconf
    latest_coords = _coords_from_text(message or "")
    if latest_coords:
        slots.lat, slots.lon = latest_coords
        slots.place_name = None
        slots.confidence["location"] = "high"
        slots.geocode_source = "coordinates"
    latest_crop = _crop_from_text(message or "")
    if latest_crop:
        slots.crop_type = latest_crop

    if slots.practice_family is None:
        fam, fconf = _family_from_text(corpus)
        if fam:
            slots.practice_family = fam
            slots.confidence["practice_family"] = fconf
    if slots.indicator is None:
        ind, iconf = _indicator_from_text(corpus)
        if ind:
            slots.indicator = ind
            slots.confidence["indicator"] = iconf
    if slots.lat is None:
        coords = _coords_from_text(corpus)
        if coords:
            slots.lat, slots.lon = coords
            slots.confidence["location"] = "high"
            slots.geocode_source = "coordinates"
    if slots.crop_type is None:
        crop = _crop_from_text(corpus)
        if crop:
            slots.crop_type = crop

    # Place-name geocoding when coords are still missing.
    if slots.lat is None or slots.lon is None:
        hit: GeocodeHit | None = geocode_text(
            message, allow_network=allow_network_geocode
        ) or geocode_text(corpus, allow_network=allow_network_geocode)
        if hit:
            slots.lat, slots.lon = hit.lat, hit.lon
            slots.place_name = hit.name
            slots.confidence["location"] = "high" if hit.source == "gazetteer" else "medium"
            slots.geocode_source = hit.source
            slots.inferred.append("location")

    # Infer challenge from a clear objective (+ soft terrain cues).
    if slots.indicator and not slots.practice_family:
        default_fam = INDICATOR_DEFAULT_FAMILY.get(slots.indicator)
        if default_fam:
            soft_ok = True
            if slots.indicator in {"soil loss", "runoff"}:
                soft_ok = any(
                    w in (message or "").lower()
                    for w in FAMILY_SOFT["Erosion control and water management"]
                ) or slots.confidence.get("indicator") == "high"
            if soft_ok and is_supported_family_indicator(default_fam, slots.indicator):
                slots.practice_family = default_fam
                slots.confidence["practice_family"] = "inferred"
                slots.inferred.append("practice_family")

    # Infer objective for erosion when the challenge is clear but objective isn't.
    if slots.practice_family and not slots.indicator:
        if slots.practice_family == "Erosion control and water management":
            t = (message or "").lower()
            if any(w in t for w in ("soil", "eros", "slope", "runoff", "wash")):
                slots.indicator = "soil loss" if "runoff" not in t else "runoff"
                slots.confidence["indicator"] = "inferred"
                slots.inferred.append("indicator")

    slots.practice_family, slots.indicator = _resolve_family_indicator(
        slots.practice_family,
        slots.indicator,
        slots.confidence.get("practice_family"),
        slots.confidence.get("indicator"),
    )
    # If family was dropped for incompatibility, try default family for indicator.
    if slots.indicator and not slots.practice_family:
        default_fam = INDICATOR_DEFAULT_FAMILY.get(slots.indicator)
        if default_fam and is_supported_family_indicator(default_fam, slots.indicator):
            slots.practice_family = default_fam
            slots.confidence["practice_family"] = "inferred"
            if "practice_family" not in slots.inferred:
                slots.inferred.append("practice_family")
    # If objective was dropped, ask (leave missing) rather than inventing one.

    missing: list[str] = []
    if not slots.practice_family:
        missing.append("challenge")
    if not slots.indicator:
        missing.append("objective")
    if slots.lat is None or slots.lon is None:
        missing.append("location")
    slots.missing = missing
    return slots


def clarification_message(slots: ChatSlots) -> str:
    """Short, smart ask for only what is still missing — never invent practices."""
    missing = slots.missing
    bits: list[str] = []

    if slots.place_name and "location" not in missing:
        bits.append(f"I placed your farm near **{slots.place_name}**")
    if slots.practice_family and "challenge" not in missing:
        short = slots.practice_family.replace(" and management", "")
        bits.append(f"challenge **{short}**")
    if slots.indicator and "objective" not in missing:
        bits.append(f"objective **{slots.indicator}**")

    understood = ""
    if bits:
        understood = "I understood " + ", ".join(bits) + ". "

    if missing == ["challenge", "objective", "location"]:
        return (
            "I can recommend evidence-based CSA practices once I know three things: "
            "your **challenge** (e.g. erosion control), your **objective** "
            "(e.g. reduce soil loss), and your **location** (map pin, coordinates, "
            "or a place name in Ethiopia)."
        )
    asks: list[str] = []
    if "challenge" in missing:
        asks.append(
            "which **challenge** fits best — crop production, livestock, soil fertility, "
            "erosion & water, or agro-forestry"
        )
    if "objective" in missing:
        if slots.practice_family == "Erosion control and water management":
            asks.append(
                "your **objective** — reduce soil loss / erosion, reduce runoff, "
                "or improve water-use efficiency"
            )
        else:
            asks.append(
                "your **objective** (e.g. increase yield, reduce soil loss, improve soil organic matter)"
            )
    if "location" in missing:
        asks.append(
            "your **location** — drop a map pin, share lat/long, or name a place in Ethiopia"
        )

    if len(asks) == 1:
        return understood + f"To rank practices from field evidence, please share {asks[0]}."
    if len(asks) == 2:
        return understood + f"Please share {asks[0]}, and {asks[1]}."
    return understood + "Please share " + "; ".join(asks) + "."


def evidence_summary(recommendation: dict[str, Any]) -> str:
    """Deterministic, context-led summary grounded only in recommend() output."""
    recs = recommendation.get("recommendations") or []
    if not recs:
        note = (recommendation.get("details") or {}).get("note") or ""
        return note or (
            "I couldn't find enough field evidence for that combination. "
            "Try a nearby location or a different objective."
        )
    q = recommendation.get("query") or {}
    ctx = (recommendation.get("details") or {}).get("context") or {}
    zone = ctx.get("aez_belt") or "your area"
    facts: list[str] = []
    rain = ctx.get("Rainfall")
    slope = ctx.get("slope")
    clay = ctx.get("soil_clay")
    if isinstance(rain, (int, float)):
        facts.append(f"~{rain:.0f} mm rainfall")
    if isinstance(slope, (int, float)):
        facts.append(f"slope ~{slope:.0f}%")
    if isinstance(clay, (int, float)):
        facts.append(f"clay ~{clay:.0f}%")
    fact_bit = f" ({', '.join(facts)})" if facts else ""
    place = ""
    # Prefer not inventing place names; zone is from rasters.
    lead = recs[0]
    others = ", ".join(r["practice"] for r in recs[1:])
    direction = q.get("goal_direction") or "improve"
    indicator = q.get("indicator") or "your goal"
    crop = q.get("crop_type")
    crop_bit = f" for your {crop}" if crop else ""
    text = (
        f"For your **{zone}** area{fact_bit}{crop_bit}, the evidence ranks "
        f"**{lead['practice']}** to {direction} {indicator}."
    )
    if others:
        text += f" Other strong options: {others}."
    conf = (recommendation.get("details") or {}).get("confidence")
    if conf == "low":
        text += " Evidence for this setting is limited — treat this as a starting point."
    return text

