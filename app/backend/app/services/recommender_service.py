"""Thin service wrapper around the canonical recommender engine.

``backend/recommend.py`` and ``backend/groq_agent.py`` are the source of truth for
the ML logic. We do **not** duplicate or fork them — we put ``backend/`` on
``sys.path`` and import them, load the model once at startup, and expose small,
typed helpers to the routers.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# Make the canonical engine importable (it lives at backend/ root and resolves its
# own artifacts/, dataset/, layers/ paths relative to its own file location).
_BACKEND_ROOT = get_settings().backend_root
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import recommend as _engine  # noqa: E402  (canonical logic — wrap, don't fork)
from recommend import recommend as _recommend  # noqa: E402

# Re-export the canonical enums / direction map so the whole app has one source.
DIRECTION: dict[str, int] = dict(_engine.DIRECTION)
INDICATORS: list[str] = list(DIRECTION.keys())

PRACTICE_FAMILIES: list[str] = [
    "Crop production and management",
    "Livestock production and management",
    "Integrated soil fertility management",
    "Erosion control and water management",
    "Agro-forestry and forest management",
]

# Ethiopia geographic bounds (see prompt §1).
LAT_BOUNDS: tuple[float, float] = (3.3, 14.9)
LON_BOUNDS: tuple[float, float] = (32.9, 48.2)

_READY = False


def _required_paths() -> list[Path]:
    """Every file the engine needs to run — used for fail-fast startup validation."""
    root = _BACKEND_ROOT
    paths = [
        root / "artifacts" / "csa_model.joblib",
        root / "dataset" / "CSA_ERA_final_model_ready.csv",
        root / "aez_belt_lookup.csv",
    ]
    layer_names = list(_engine.STACK.keys()) + ["aez_belt"]
    paths += [root / "layers" / f"{name}.tif" for name in layer_names]
    return paths


def warmup() -> None:
    """Validate artifacts exist and warm the model + dataset caches.

    Raises RuntimeError with a clear message if anything required is missing so
    the process fails fast at startup rather than on the first request.
    """
    global _READY
    missing = [str(p) for p in _required_paths() if not p.exists()]
    if missing:
        raise RuntimeError(
            "Recommender engine cannot start — missing required files:\n  - "
            + "\n  - ".join(missing)
        )
    # Load model + dataset + aez lookup once (module-level cache inside recommend.py).
    _engine._load()
    _READY = True
    logger.info("Recommender engine warmed up (model + dataset + rasters ready).")


def is_ready() -> bool:
    return _READY


def crop_types() -> list[str]:
    """Sorted unique crop_type values from the dataset (for the UI typeahead)."""
    _engine._load()
    df = _engine._DF
    vals = {str(v).strip() for v in df["crop_type"].dropna().unique() if str(v).strip()}
    return sorted(vals, key=str.lower)


def indicators_by_family(min_observations: int = 1) -> dict[str, list[str]]:
    """Indicator keys per practice family, ordered by field-evidence count (desc).

    Raw meta-analysis coverage — may include pairings that are misleading in the
    UI (e.g. crop-yield studies filed under livestock). Prefer
    ``ui_indicators_by_family()`` for metadata and validation.
    """
    _engine._load()
    df = _engine._DF
    out: dict[str, list[str]] = {}
    for fam in PRACTICE_FAMILIES:
        sub = df[df["practice_family"] == fam]
        if sub.empty:
            out[fam] = []
            continue
        counts = sub.groupby("Indicator").size()
        keys = [
            k
            for k in INDICATORS
            if k in counts.index and int(counts[k]) >= min_observations
        ]
        keys.sort(key=lambda k: (-int(counts[k]), INDICATORS.index(k)))
        out[fam] = keys
    return out


# Objectives to hide per family after reviewing CSA_ERA evidence (see dataset audit).
# Livestock + "yield" / WUE mostly rank crop irrigation bundles, not herd outcomes.
FAMILY_UI_INDICATOR_EXCLUDE: dict[str, frozenset[str]] = {
    "Livestock production and management": frozenset(
        {"yield", "water use efficiency", "SOM content"}
    ),
    "Erosion control and water management": frozenset({"income"}),
    "Agro-forestry and forest management": frozenset({"income"}),
}


def ui_indicators_by_family() -> dict[str, list[str]]:
    """Evidence-ordered indicators safe to offer in UI and accept on /recommend."""
    raw = indicators_by_family()
    out: dict[str, list[str]] = {}
    for fam in PRACTICE_FAMILIES:
        drop = FAMILY_UI_INDICATOR_EXCLUDE.get(fam, frozenset())
        out[fam] = [k for k in raw.get(fam, []) if k not in drop]
    return out


def is_supported_family_indicator(practice_family: str, indicator: str) -> bool:
    return indicator in ui_indicators_by_family().get(practice_family, [])


def assert_supported_family_indicator(practice_family: str, indicator: str) -> None:
    allowed = ui_indicators_by_family().get(practice_family, [])
    if indicator not in allowed:
        raise ValueError(
            f"The objective '{indicator}' is not supported for challenge "
            f"'{practice_family}'. Supported objectives: {', '.join(allowed) or '(none)'}."
        )


def practices_by_family() -> dict[str, list[str]]:
    """Unique CSA_practices in the training data for each practice_family (ranking pool)."""
    _engine._load()
    df = _engine._DF
    out: dict[str, list[str]] = {}
    for fam in PRACTICE_FAMILIES:
        names = sorted(df.loc[df["practice_family"] == fam, "CSA_practices"].unique())
        out[fam] = [str(n) for n in names]
    return out


def _assert_recommendations_in_family(result: dict[str, Any], practice_family: str) -> None:
    allowed = set(practices_by_family().get(practice_family, []))
    for rec in result.get("recommendations") or []:
        pr = rec.get("practice")
        if pr and pr not in allowed:
            raise RuntimeError(
                f"Recommendation '{pr}' is outside practice_family '{practice_family}'."
            )


def extract_context(lat: float, lon: float) -> dict[str, Any]:
    """Resolve the agro-ecological context (aez_belt + stack features) for a point."""
    _engine._load()
    return _engine.extract_context(lat, lon)


def recommend(
    lat: float,
    lon: float,
    practice_family: str,
    indicator: str,
    crop_type: str | None = None,
    top_n: int = 3,
) -> dict[str, Any]:
    """Call the canonical engine. Returns the two-tier dict (query/recommendations/details)."""
    assert_supported_family_indicator(practice_family, indicator)
    result = _recommend(
        lat=lat,
        lon=lon,
        practice_family=practice_family,
        indicator=indicator,
        crop_type=crop_type,
        top_n=top_n,
    )
    _assert_recommendations_in_family(result, practice_family)
    return result
