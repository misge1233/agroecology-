"""Resolve Ethiopian place names to lat/lon for the chat slot pipeline.

Primary path: curated local gazetteer (offline, fast, deterministic).
Optional fallback: OpenStreetMap Nominatim (network), Ethiopia-biased.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

import httpx

from app.services.recommender_service import LAT_BOUNDS, LON_BOUNDS

logger = logging.getLogger(__name__)

# Curated town/city centres (approx.). Aliases normalize spelling variants.
# Coordinates are WGS84; values chosen for farm-context pin placement (town centre).
_GAZETTEER: dict[str, tuple[float, float]] = {
    "addis ababa": (9.03, 38.74),
    "adama": (8.54, 39.27),
    "nazret": (8.54, 39.27),
    "nazareth": (8.54, 39.27),
    "bahir dar": (11.59, 37.39),
    "bahirdar": (11.59, 37.39),
    "hawassa": (7.05, 38.48),
    "awassa": (7.05, 38.48),
    "mekelle": (13.50, 39.47),
    "mekele": (13.50, 39.47),
    "gondar": (12.60, 37.47),
    "gonder": (12.60, 37.47),
    "dire dawa": (9.60, 41.87),
    "jimma": (7.67, 36.83),
    "debre birhan": (9.6795, 39.5326),
    "debre berhan": (9.6795, 39.5326),
    "debre birhan town": (9.6795, 39.5326),
    "debre markos": (10.35, 37.73),
    "debre tabor": (11.85, 38.02),
    "dessie": (11.13, 39.63),
    "desie": (11.13, 39.63),
    "kombolcha": (11.08, 39.74),
    "shashamane": (7.20, 38.60),
    "shashemene": (7.20, 38.60),
    "arba minch": (6.03, 37.55),
    "harar": (9.31, 42.12),
    "harari": (9.31, 42.12),
    "jijiga": (9.35, 42.80),
    "asosa": (10.07, 34.53),
    "assosa": (10.07, 34.53),
    "gambela": (8.25, 34.58),
    "gambella": (8.25, 34.58),
    "semera": (11.79, 41.01),
    "axum": (14.12, 38.72),
    "aksum": (14.12, 38.72),
    "lalibela": (12.03, 39.04),
    "bishoftu": (8.75, 38.98),
    "debre zeit": (8.75, 38.98),
    "hosea": (7.55, 37.85),
    "hosanna": (7.55, 37.85),
    "hosaina": (7.55, 37.85),
    "wolaita sodo": (6.85, 37.75),
    "sodo": (6.85, 37.75),
    "nekemte": (9.08, 36.55),
    "ambo": (8.98, 37.85),
    "ziway": (7.93, 38.72),
    "butejira": (8.12, 38.38),
    "butajira": (8.12, 38.38),
    "dilla": (6.41, 38.31),
    "yirgalem": (6.75, 38.41),
    "woldia": (11.83, 39.60),
    "woldiya": (11.83, 39.60),
    "debark": (13.16, 37.90),
    "metu": (8.30, 35.58),
    "mizan teferi": (6.99, 35.58),
    "mizan": (6.99, 35.58),
}

_PLACE_HINT_RE = re.compile(
    r"(?i)\b(?:near|around|in|at|outside|close\s+to|by)\s+"
    r"([A-Za-z][A-Za-z\s\-']{1,40})"
)


@dataclass(frozen=True)
class GeocodeHit:
    name: str
    lat: float
    lon: float
    source: str  # "gazetteer" | "nominatim"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _in_ethiopia(lat: float, lon: float) -> bool:
    return LAT_BOUNDS[0] <= lat <= LAT_BOUNDS[1] and LON_BOUNDS[0] <= lon <= LON_BOUNDS[1]


def lookup_gazetteer(place: str) -> GeocodeHit | None:
    key = _norm(place)
    if not key:
        return None
    if key in _GAZETTEER:
        lat, lon = _GAZETTEER[key]
        return GeocodeHit(name=place.strip(), lat=lat, lon=lon, source="gazetteer")
    # Longest alias contained in the query, or query contained in alias.
    best: tuple[int, str, tuple[float, float]] | None = None
    for alias, coords in _GAZETTEER.items():
        if alias in key or key in alias:
            score = len(alias)
            if best is None or score > best[0]:
                best = (score, alias, coords)
    if best:
        _, alias, (lat, lon) = best
        return GeocodeHit(name=alias.title(), lat=lat, lon=lon, source="gazetteer")
    return None


def extract_place_candidates(text: str) -> list[str]:
    """Pull likely place-name phrases from free text (Ethiopia farm context)."""
    if not text:
        return []
    candidates: list[str] = []
    for m in _PLACE_HINT_RE.finditer(text):
        chunk = m.group(1).strip(" .,;:!?'\"")
        # Stop at common trailing clauses.
        chunk = re.split(
            r"(?i)\b(?:and|with|to|for|because|where|which|that|i\s+want|please)\b",
            chunk,
            maxsplit=1,
        )[0].strip(" .,;:")
        if len(chunk) >= 3:
            candidates.append(chunk)
    # Also scan for known aliases appearing anywhere in the text.
    normed = _norm(text)
    for alias in sorted(_GAZETTEER.keys(), key=len, reverse=True):
        if alias in normed:
            candidates.append(alias)
            break
    # Deduplicate preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        k = _norm(c)
        if k and k not in seen:
            seen.add(k)
            out.append(c)
    return out


def geocode_place(place: str, *, allow_network: bool = False) -> GeocodeHit | None:
    hit = lookup_gazetteer(place)
    if hit:
        return hit
    if not allow_network:
        return None
    return _nominatim(place)


def geocode_text(text: str, *, allow_network: bool = False) -> GeocodeHit | None:
    """Find a place name in free text and resolve to coordinates."""
    # Prefer longest gazetteer match in the whole text first (deterministic).
    normed = _norm(text)
    best: tuple[int, GeocodeHit] | None = None
    for alias, (lat, lon) in _GAZETTEER.items():
        if alias in normed:
            score = len(alias)
            if best is None or score > best[0]:
                best = (
                    score,
                    GeocodeHit(name=alias.title(), lat=lat, lon=lon, source="gazetteer"),
                )
    if best:
        return best[1]

    for cand in extract_place_candidates(text):
        hit = geocode_place(cand, allow_network=allow_network)
        if hit:
            return hit
    return None


def _nominatim(place: str) -> GeocodeHit | None:
    q = (place or "").strip()
    if len(q) < 3:
        return None
    try:
        with httpx.Client(timeout=6.0, headers={"User-Agent": "agroecology-ai/1.0"}) as client:
            resp = client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": q,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "et",
                },
            )
            resp.raise_for_status()
            rows = resp.json()
    except Exception as exc:
        logger.info("Nominatim geocode failed for %r: %s", q, exc)
        return None
    if not rows:
        return None
    try:
        lat = float(rows[0]["lat"])
        lon = float(rows[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not _in_ethiopia(lat, lon):
        return None
    display = rows[0].get("display_name") or q
    short = display.split(",")[0].strip()
    return GeocodeHit(name=short, lat=lat, lon=lon, source="nominatim")
