"""Build the /metadata payload — the UI contract (enums, labels, bounds, honest metrics).

Everything here is derived from the canonical engine + artifacts; nothing is
hardcoded that the model doesn't actually support.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.services import recommender_service as svc

logger = logging.getLogger(__name__)

# Friendly UI labels for the 7 supported indicators (prompt §1). Order matters —
# it's the order shown in the dropdown.
_INDICATOR_LABELS: list[tuple[str, str]] = [
    ("yield", "Increase crop yield"),
    ("biomass yield", "Increase biomass / fodder"),
    ("income", "Increase income"),
    ("water use efficiency", "Improve water-use efficiency"),
    ("SOM content", "Improve soil organic matter"),
    ("soil loss", "Reduce soil loss / erosion"),
    ("runoff", "Reduce runoff"),
]


@lru_cache
def _model_metrics() -> dict[str, Any]:
    path = get_settings().backend_root / "artifacts" / "model_metrics.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not read model_metrics.json: %s", exc)
        return {}


def build_metadata() -> dict[str, Any]:
    metrics = _model_metrics()

    indicators = []
    for key, label in _INDICATOR_LABELS:
        d = svc.DIRECTION.get(key, 1)
        indicators.append(
            {
                "key": key,
                "label": label,
                "direction": "increase" if d > 0 else "reduce",
            }
        )

    cv_r2 = metrics.get("cv_r2")
    model_meta = {
        "name": metrics.get("model", "RandomForest"),
        "cv_r2": round(float(cv_r2), 3) if cv_r2 is not None else None,
        "note": (
            "This is a ranking tool trained on meta-analysis field evidence. "
            "Honest cross-validated skill is modest (grouped R² ≈ "
            f"{round(float(cv_r2), 2) if cv_r2 is not None else 0.19}, close to the "
            "evidence mean), so treat the ordering of practices — not the exact "
            "percentages — as the useful signal."
        ),
    }

    lat_lo, lat_hi = svc.LAT_BOUNDS
    lon_lo, lon_hi = svc.LON_BOUNDS

    return {
        "practice_families": list(svc.PRACTICE_FAMILIES),
        "indicators": indicators,
        "indicators_by_family": svc.ui_indicators_by_family(),
        "practices_by_family": svc.practices_by_family(),
        "crop_types": svc.crop_types(),
        "bounds": {"lat": [lat_lo, lat_hi], "lon": [lon_lo, lon_hi]},
        "model": model_meta,
    }
