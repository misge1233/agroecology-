"""Map the engine's resolved context onto the WOCAT QT context classes.

``recommend.extract_context(lat, lon)`` returns the raster stack's values at
one pin — continuous quantities such as ``Rainfall`` in mm and ``slope`` in
percent. The knowledge graph stores WOCAT's *categorical* QT §5.1-§5.3
classes. This module is the bridge, so ``/explain`` can ask
``query.similar_context_technologies()`` for Technologies documented in a
comparable context (P6b-ii, once the WOCAT export lands).

Design rules:

* **Never guess.** An input that is missing, non-numeric, NaN or outside a
  physically sensible range yields *no key at all* rather than a nearest
  band. A caller gets a partial context, never a fabricated one.
* **Every output is validated** against
  ``wocat_taxonomy.CONTEXT_CLASSES``, so a typo cannot invent a class.
* **Contiguous bands.** The questionnaire prints its bands with one-unit
  gaps (``< 250 mm`` then ``251-500 mm``; ``flat (0-2%)`` then
  ``gentle (3-5%)``) because it expects integer answers. Raster values are
  continuous, so the gaps are closed upward: a value is placed in the first
  band whose **upper bound it does not exceed (inclusive)**. 250.0 mm is
  therefore ``< 250 mm`` and 250.1 mm is ``251-500 mm``; the same rule puts
  clay 18.0 % in coarse/light and 18.1 % in medium, and an LGP of 75.0 days
  in arid and 75.1 in semi-arid (see the band tables and the edge tests).

Band sources, all cited:

* rainfall, slope, altitude — QT §5.1-§5.2 verbatim.
* **soil texture from clay %** — the QT asks for a texture class, not a clay
  percentage, so a rule is needed. USDA-style topsoil bands are used:
  **≤ 18 % clay = coarse/light, 18-35 % = medium, > 35 % = fine/heavy**
  (FAO/USDA texture-class grouping as used in the Harmonized World Soil
  Database topsoil texture classes 1/2/3). This is an approximation: the
  USDA triangle also uses sand and silt, which the stack does not carry at
  serving time, so a sandy clay loam may be called medium here.
* **agro-climatic zone from LGP** — the QT's own definition, transcribed in
  ``wocat_taxonomy.AGROCLIMATIC_ZONE_LGP``: humid > 270 days, sub-humid
  180-269, semi-arid 75-179, arid < 74. Those printed bands leave 74-75 and
  269-270 undefined; they are closed upward the same way, giving
  **≤ 75 arid, 75-180 semi-arid, 180-270 sub-humid, > 270 humid** (the P6b-i
  brief's wording; boundaries inclusive on the upper side as above).

Not mapped, deliberately:

* ``temp_mean_annual`` — the QT has no temperature context class.
* ``soil_depth`` and ``topsoil_om`` — the serving stack carries neither.
  ``soil_soc`` is soil organic *carbon*; converting it to organic *matter*
  needs the Van Bemmelen factor (~1.724), an assumption this module will not
  make silently. If the owner wants it, it is a two-line addition and a
  decision to record.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Callable

from .wocat_taxonomy import CONTEXT_CLASSES

logger = logging.getLogger(__name__)

#: Engine context key -> the ContextClass kind it feeds.
SOURCE_KEYS: dict[str, str] = {
    "Rainfall": "rainfall_band",
    "slope": "slope_class",
    "Altitude_r": "altitude_zone",
    "soil_clay": "soil_texture",
    "lgp_days": "agroclimatic_zone",
}

#: Engine keys that intentionally map to nothing (see the module docstring).
UNMAPPED_KEYS: tuple[str, ...] = (
    "temp_mean_annual", "precip_seasonality", "land_cover", "soil_ph",
    "soil_soc", "aez_belt",
)

# (inclusive upper bound, QT label) — the last entry's bound is +inf.
_RAINFALL_BANDS: tuple[tuple[float, str], ...] = (
    (250, "< 250 mm"),
    (500, "251-500 mm"),
    (750, "501-750 mm"),
    (1000, "751-1,000 mm"),
    (1500, "1,001-1,500 mm"),
    (2000, "1,501-2,000 mm"),
    (3000, "2,001-3,000 mm"),
    (4000, "3,001-4,000 mm"),
    (math.inf, "> 4,000 mm"),
)
_SLOPE_BANDS: tuple[tuple[float, str], ...] = (
    (2, "flat (0-2%)"),
    (5, "gentle (3-5%)"),
    (10, "moderate (6-10%)"),
    (15, "rolling (11-15%)"),
    (30, "hilly (16-30%)"),
    (60, "steep (31-60%)"),
    (math.inf, "very steep (> 60%)"),
)
_ALTITUDE_BANDS: tuple[tuple[float, str], ...] = (
    (100, "< 100 m a.s.l."),
    (500, "101-500 m a.s.l."),
    (1000, "501-1,000 m a.s.l."),
    (1500, "1,001-1,500 m a.s.l."),
    (2000, "1,501-2,000 m a.s.l."),
    (2500, "2,001-2,500 m a.s.l."),
    (3000, "2,501-3,000 m a.s.l."),
    (4000, "3,001-4,000 m a.s.l."),
    (math.inf, "> 4,000 m a.s.l."),
)
_CLAY_BANDS: tuple[tuple[float, str], ...] = (
    (18, "coarse/ light (sandy)"),
    (35, "medium (loamy, silty)"),
    (math.inf, "fine/ heavy (clay)"),
)
_LGP_BANDS: tuple[tuple[float, str], ...] = (
    (75, "arid"),
    (180, "semi-arid"),
    (270, "sub-humid"),
    (math.inf, "humid"),
)

#: Physically sensible input ranges. Outside these the value is a nodata
#: sentinel or a unit mix-up, not a measurement — so no class is emitted.
_VALID_RANGE: dict[str, tuple[float, float]] = {
    "rainfall_band": (0.0, 20000.0),
    "slope_class": (0.0, 90.0),
    "altitude_zone": (-500.0, 9000.0),     # Danakil is below sea level
    "soil_texture": (0.0, 100.0),          # clay is a percentage
    "agroclimatic_zone": (0.0, 366.0),     # length of growing period, days
}


def _as_float(value: Any) -> float | None:
    """Finite float, or None for None/NaN/blank/non-numeric input."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _band(value: Any, bands: tuple[tuple[float, str], ...], kind: str) -> str | None:
    """Place ``value`` in the first band whose upper bound it does not exceed."""
    number = _as_float(value)
    if number is None:
        return None
    low, high = _VALID_RANGE[kind]
    if not low <= number <= high:
        logger.debug("%s: %r is outside the plausible range %s-%s — not mapped",
                     kind, value, low, high)
        return None
    for upper, label in bands:
        if number <= upper:
            return label
    return None  # pragma: no cover - the last bound is +inf


def rainfall_band(mm: Any) -> str | None:
    """Mean annual rainfall in mm -> QT §5.1 rainfall band."""
    return _band(mm, _RAINFALL_BANDS, "rainfall_band")


def slope_class(percent: Any) -> str | None:
    """Slope in percent -> QT §5.2 slope class."""
    return _band(percent, _SLOPE_BANDS, "slope_class")


def altitude_zone(metres: Any) -> str | None:
    """Elevation in metres a.s.l. -> QT §5.2 altitudinal zone."""
    return _band(metres, _ALTITUDE_BANDS, "altitude_zone")


def soil_texture_from_clay(clay_percent: Any) -> str | None:
    """Topsoil clay % -> QT §5.3 texture class (USDA-style grouping)."""
    return _band(clay_percent, _CLAY_BANDS, "soil_texture")


def agroclimatic_zone_from_lgp(days: Any) -> str | None:
    """Length of growing period in days -> QT §5.1 agro-climatic zone."""
    return _band(days, _LGP_BANDS, "agroclimatic_zone")


#: kind -> the function that produces it.
MAPPERS: dict[str, Callable[[Any], str | None]] = {
    "rainfall_band": rainfall_band,
    "slope_class": slope_class,
    "altitude_zone": altitude_zone,
    "soil_texture": soil_texture_from_clay,
    "agroclimatic_zone": agroclimatic_zone_from_lgp,
}


def context_to_classes(ctx: dict[str, Any] | None) -> dict[str, str]:
    """Engine context -> ``{ContextClass kind: QT label}``.

    ``ctx`` is what ``recommend.extract_context`` returns. Keys that cannot
    be mapped — absent, nodata, out of range, or with no QT counterpart —
    are simply omitted.

    >>> context_to_classes({"Rainfall": 1947.0, "slope": 4.0})
    {'rainfall_band': '1,501-2,000 mm', 'slope_class': 'gentle (3-5%)'}
    >>> context_to_classes({"Rainfall": None, "temp_mean_annual": 19.0})
    {}
    """
    out: dict[str, str] = {}
    for source_key, kind in SOURCE_KEYS.items():
        if ctx is None or source_key not in ctx:
            continue
        label = MAPPERS[kind](ctx[source_key])
        if label is None:
            continue
        if label not in CONTEXT_CLASSES[kind]:  # pragma: no cover - guards typos
            raise ValueError(
                f"{kind}: {label!r} is not a QT class — the band table and "
                "wocat_taxonomy.CONTEXT_CLASSES have drifted apart"
            )
        out[kind] = label
    return out
