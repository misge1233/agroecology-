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
from app import i18n
from app.services import evidence_service, explain_service, speech_service
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


def _practice_records_available() -> bool:
    """Whether the knowledge graph can propose documented practice records (P9)."""
    gq = explain_service.get_graph_query()
    return bool(gq is not None and gq.has_practice_records())


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
        # True when the RAG evidence index exists on disk (POST /explain usable).
        "rag_ready": explain_service.is_ready(),
        # True when the knowledge graph is built — gates the evidence-base
        # line in the UI's Evidence panel.
        "graph_ready": explain_service.graph_is_ready(),
        # True when server-side voice (POST /speech/*) is configured (U6).
        "speech_ready": speech_service.is_ready(get_settings())
        or bool(speech_service.local_languages(get_settings())),
        # UI languages the API answers in (U1).
        "languages": list(i18n.LANGUAGES),
        # Size of the evidence base (counts only) for the home trust strip (U1).
        "evidence": svc.evidence_counts(),
        # P9: how the advisory decides its mode and which knowledge sources exist.
        "advisory": {
            "thresholds": evidence_service.thresholds(get_settings()),
            "modes": list(evidence_service.MODES),
            "sources": {
                "graph": explain_service.graph_is_ready(),
                "guidance": get_settings().resolved_rag_guidance_chunks_path.is_file(),
                # True once the graph holds non-synthetic WOCAT records (P6b-ii
                # ingests the real ones; P6b-i fixtures count when loaded).
                "practice_records": _practice_records_available(),
            },
        },
    }
