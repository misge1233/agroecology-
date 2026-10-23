"""Crosswalk: the model's 7 indicators <-> WOCAT QT §6.1 impact variables.

This is the join that makes the P6c experiment possible — comparing the ML
model's predicted effect DIRECTION for a (practice, indicator) pair with the
direction practitioners reported for the matching WOCAT impact variable.

**Direction semantics are not redefined here.** ``recommend.DIRECTION`` in
``app/backend/recommend.py`` is the canonical statement of which way is
"better" for each indicator (+1 higher-is-better, -1 lower-is-better), and
:func:`model_direction` reads it:

* first by importing ``recommend`` normally;
* if that fails because the engine's heavy dependencies (rasterio, joblib,
  pandas) are not installed in the current environment, by parsing the
  ``DIRECTION`` literal out of ``recommend.py`` with :mod:`ast`.

Both paths read the same single source of truth, so the values can never
drift; :func:`direction_source` reports which path was used, and
``test_graph.py`` asserts the mapping covers exactly the engine's indicators.

Each mapping carries one documented rationale line. ``proxy=True`` marks a
mapping where the WOCAT variable is a stand-in rather than the same quantity.
"""
from __future__ import annotations

import ast
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from wocat_taxonomy import IMPACT_BY_NAME

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
RECOMMEND_PY = REPO_ROOT / "app" / "backend" / "recommend.py"

_DIRECTION: dict[str, int] | None = None
_DIRECTION_SOURCE: str = "unloaded"


def _direction_from_import() -> dict[str, int] | None:
    """Import ``recommend`` and return its ``DIRECTION`` map, or None."""
    backend = str(RECOMMEND_PY.parent)
    added = backend not in sys.path
    if added:
        sys.path.insert(0, backend)
    try:
        import recommend  # type: ignore[import-not-found]

        return dict(recommend.DIRECTION)
    except Exception as exc:  # heavy deps absent, or engine not importable
        logger.debug("recommend import unavailable (%s); parsing source", exc)
        return None
    finally:
        if added and backend in sys.path:
            sys.path.remove(backend)


def _direction_from_source() -> dict[str, int]:
    """Parse the ``DIRECTION`` literal out of ``recommend.py``.

    Used only when the engine cannot be imported. Still reads the canonical
    definition — nothing is duplicated into this module.
    """
    if not RECOMMEND_PY.exists():
        raise FileNotFoundError(
            f"cannot resolve indicator directions: {RECOMMEND_PY} is missing"
        )
    tree = ast.parse(RECOMMEND_PY.read_text(encoding="utf-8"), str(RECOMMEND_PY))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "DIRECTION" in names:
            value = ast.literal_eval(node.value)
            return {str(k): int(v) for k, v in value.items()}
    raise ValueError(f"no DIRECTION assignment found in {RECOMMEND_PY}")


def direction_map() -> dict[str, int]:
    """The engine's indicator -> (+1 | -1) map. Cached after first call."""
    global _DIRECTION, _DIRECTION_SOURCE
    if _DIRECTION is None:
        imported = _direction_from_import()
        if imported is not None:
            _DIRECTION, _DIRECTION_SOURCE = imported, "import recommend"
        else:
            _DIRECTION, _DIRECTION_SOURCE = _direction_from_source(), "ast parse of recommend.py"
    return dict(_DIRECTION)


def direction_source() -> str:
    """How the direction map was obtained ('import recommend' / 'ast parse ...')."""
    direction_map()
    return _DIRECTION_SOURCE


def model_direction(indicator: str) -> int:
    """+1 if higher is better for ``indicator``, -1 if lower is better."""
    directions = direction_map()
    if indicator not in directions:
        raise KeyError(f"unknown indicator: {indicator!r}")
    return directions[indicator]


@dataclass(frozen=True)
class IndicatorMapping:
    """One model indicator mapped onto WOCAT QT §6.1 impact variables."""

    indicator: str
    wocat_variable: str
    rationale: str
    proxy: bool = False
    secondary: tuple[str, ...] = ()

    @property
    def direction_good(self) -> int:
        """+1 / -1, read from ``recommend.DIRECTION`` — never redefined here."""
        return model_direction(self.indicator)


#: The 7 indicators of ``recommend.DIRECTION``, each with its primary WOCAT
#: QT §6.1 on-site impact variable and one rationale line.
INDICATOR_MAPPINGS: tuple[IndicatorMapping, ...] = (
    IndicatorMapping(
        "yield", "crop production",
        "Both measure harvested output of the cultivated crop; QT 'crop "
        "production' is the practitioner-rated counterpart of the dataset's "
        "with/without yield response ratio.",
    ),
    IndicatorMapping(
        "biomass yield", "fodder production",
        "Dataset biomass yield is predominantly above-ground vegetative "
        "biomass harvested or grazed as feed, which QT rates as 'fodder "
        "production'; 'biomass/ above-ground C' covers the standing-carbon "
        "reading of the same quantity.",
        secondary=("biomass/ above-ground C",),
    ),
    IndicatorMapping(
        "income", "farm income",
        "Both are the land user's net return from the plot or farm; QT asks "
        "for it from the land user's perspective, as the dataset's income "
        "observations do.",
    ),
    IndicatorMapping(
        "SOM content", "soil organic matter/ below-ground C",
        "Same quantity under both names — soil organic matter of the topsoil; "
        "QT bundles below-ground carbon into the one variable.",
    ),
    IndicatorMapping(
        "soil loss", "soil loss",
        "Identical quantity and name; QT rates it with its poles reversed "
        "(increased -> decreased), matching recommend.DIRECTION['soil loss'] = -1.",
    ),
    IndicatorMapping(
        "runoff", "surface runoff",
        "Identical quantity; QT 'surface runoff' is plot-scale overland flow, "
        "the same measurement the dataset's runoff rows report.",
    ),
    IndicatorMapping(
        "water use efficiency", "soil moisture",
        "PROXY: QT §6.1 has no water-use-efficiency variable. Soil moisture is "
        "the closest on-site state variable a practitioner rates, and in this "
        "evidence base WUE gains come mainly from retained soil water; "
        "'evaporation' captures the loss side of the same balance.",
        proxy=True,
        secondary=("evaporation",),
    ),
)

MAPPING_BY_INDICATOR: dict[str, IndicatorMapping] = {
    m.indicator: m for m in INDICATOR_MAPPINGS
}


def wocat_variables_for(indicator: str, include_secondary: bool = False) -> tuple[str, ...]:
    """QT §6.1 variable name(s) for a model indicator."""
    mapping = MAPPING_BY_INDICATOR[indicator]
    if include_secondary:
        return (mapping.wocat_variable, *mapping.secondary)
    return (mapping.wocat_variable,)


def indicator_for(wocat_variable: str) -> str | None:
    """Reverse lookup: QT §6.1 variable -> model indicator (primary only)."""
    for mapping in INDICATOR_MAPPINGS:
        if mapping.wocat_variable == wocat_variable:
            return mapping.indicator
    return None


def directions_agree(indicator: str, rating: str) -> bool | None:
    """Does a WOCAT rating point the same way the model calls 'better'?

    WOCAT ratings run from the variable's negative pole to its positive pole,
    and the positive pole is always the beneficial end — so a rating above
    'negligible' is beneficial regardless of which way the underlying
    quantity moves. Returns None for a negligible/unknown rating.

    This is the primitive the P6c direction-agreement experiment builds on;
    it reports agreement, it never alters a number.
    """
    from wocat_taxonomy import IMPACT_RATING_KEYS, normalize_rating

    key = normalize_rating(rating)
    if key is None or key == "negligible":
        return None
    beneficial = IMPACT_RATING_KEYS.index(key) > IMPACT_RATING_KEYS.index("negligible")
    # model_direction is consulted so an unknown indicator still raises here
    model_direction(indicator)
    return beneficial


def validate() -> list[str]:
    """Return a list of problems with the mapping (empty when consistent)."""
    problems: list[str] = []
    engine = set(direction_map())
    mapped = set(MAPPING_BY_INDICATOR)
    for missing in sorted(engine - mapped):
        problems.append(f"indicator {missing!r} has no WOCAT mapping")
    for extra in sorted(mapped - engine):
        problems.append(f"mapping {extra!r} is not an engine indicator")
    for mapping in INDICATOR_MAPPINGS:
        for name in (mapping.wocat_variable, *mapping.secondary):
            if name not in IMPACT_BY_NAME:
                problems.append(
                    f"{mapping.indicator!r} -> {name!r} is not a QT §6.1 variable"
                )
    return problems
