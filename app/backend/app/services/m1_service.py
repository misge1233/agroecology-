"""Methodology 1 v2 behind the API (E5 Part 4): ``ADVISOR_ENGINE=m1_v2``.

Loads the artifact written by ``model/m1/train.py`` (``M1_ARTIFACT_DIR/m1_v2.joblib``)
once, ranks the candidate practices of any registry challenge and objective for a site,
maps the engine's ``lead_source`` to the fusion labels the API already uses
(``model`` = model-led, ``study`` = study-led, ``documented``) and returns the effect
estimate with its conformal 80 % interval as additive fields. The default engine
(``legacy``) never touches this module: the frozen ``csa_model.joblib`` path is unchanged.

Fail fast, degrade gracefully: with ``ADVISOR_ENGINE=m1_v2`` a missing artifact aborts
startup with the command that builds it; with ``legacy`` ``POST /rank`` answers 503.
"""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from app.config import get_settings
from app.services import recommender_service as svc
from app.services import registry_service

logger = logging.getLogger(__name__)

ARTIFACT = "m1_v2.joblib"
#: engine lead source -> the API's PracticeEvidence lead label and the fusion wording
LEAD_LABEL = {"model": "model", "matched_studies": "study", "prior": "documented"}
FUSION_WORDING = {"model": "model-led", "study": "study-led", "documented": "documented"}
_LOCK = threading.Lock()
_ENGINE: Any = None
_LOADED_FROM: Path | None = None


class EngineUnavailable(RuntimeError):
    """``ADVISOR_ENGINE`` is not ``m1_v2`` (POST /rank answers 503)."""


def enabled(settings: Any = None) -> bool:
    """M1 v2 serves the numbers with ``ADVISOR_ENGINE=m1_v2`` and with ``m3`` (E7: the gate only
    changes the order of thin-evidence requests; every number stays M1 v2's)."""
    return engine_name(settings) in ("m1_v2", "m3")


def engine_name(settings: Any = None) -> str:
    """``legacy``, ``m1_v2`` or ``m3`` (anything else serves as ``legacy``)."""
    v = str((settings or get_settings()).advisor_engine).strip().lower()
    return v if v in ("m1_v2", "m3") else "legacy"


def artifact_path(settings: Any = None) -> Path:
    s = settings or get_settings()
    p = Path(s.m1_artifact_dir)
    if not p.is_absolute():
        p = (s.backend_root / p).resolve()
    return p / ARTIFACT


def load(settings: Any = None) -> Any:
    """The fitted ``M1Engine`` (cached); raises ``RuntimeError`` when the artifact is missing."""
    global _ENGINE, _LOADED_FROM
    path = artifact_path(settings)
    with _LOCK:
        if _ENGINE is not None and _LOADED_FROM == path:
            return _ENGINE
        if not path.exists():
            raise RuntimeError(
                f"ADVISOR_ENGINE=m1_v2 but the artifact {path} is missing. Build it with "
                "`python -m model.m1.train --release ET/2026.1`, or set ADVISOR_ENGINE=legacy."
            )
        repo_root = get_settings().backend_root.parents[1]
        if str(repo_root) not in sys.path:  # the pickled classes live in model/m1 and model/engines
            sys.path.insert(0, str(repo_root))
        import joblib

        _ENGINE = joblib.load(path)
        _LOADED_FROM = path
        logger.info("Advisory engine m1_v2 loaded from %s", path)
        return _ENGINE


def reset() -> None:
    """Drop the cached engine (tests)."""
    global _ENGINE, _LOADED_FROM
    with _LOCK:
        _ENGINE, _LOADED_FROM = None, None


def warmup(settings: Any = None) -> None:
    """Load the artifact at startup when the engine is enabled (fail fast)."""
    if enabled(settings):
        load(settings)


def info(settings: Any = None) -> dict[str, Any]:
    """What /metadata reports about the advisory engine."""
    s = settings or get_settings()
    out: dict[str, Any] = {"engine": engine_name(s), "artifact": None, "built_utc": None,
                           "release": None}
    if enabled(s):
        path = artifact_path(s)
        out["artifact"] = str(path)
        cfg = path.parent / "config.json"
        if cfg.exists():
            try:
                import json

                c = json.loads(cfg.read_text(encoding="utf-8"))
                out["built_utc"], out["release"] = c.get("built_utc"), c.get("release")
            except Exception:  # noqa: BLE001 - informational only
                pass
    return out


# ----------------------------------------------------------------- candidates and context
def registry_lookup(challenge_id: str, outcome_id: str, country: str = "ET") -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """``(challenge, objective, candidate practice ids)`` from the registry; raises ``LookupError``."""
    reg = registry_service.get_registry(country)
    challenge = next((c for c in reg.get("challenges", []) if c.get("id") == challenge_id), None)
    if challenge is None:
        raise LookupError(f"unknown challenge {challenge_id!r} for {country}")
    objective = next((o for o in challenge.get("objectives", []) if o.get("id") == outcome_id), None)
    if objective is None:
        raise LookupError(f"objective {outcome_id!r} is not an objective of challenge {challenge_id!r}")
    cands = [p["id"] for p in reg.get("practices", []) if challenge_id in (p.get("challenges") or [])]
    if not cands:
        cands = [p["id"] for p in reg.get("practices", []) if int(p.get("n_rows") or 0) > 0]
    return challenge, objective, sorted(cands)


def practice_ids_by_label(country: str = "ET") -> dict[str, str]:
    """Lower-cased practice label (the frozen ``CSA_practices`` names are the registry's
    ``name_en``) and the id itself -> registry practice id (E7 Part D)."""
    reg = registry_service.get_registry(country)
    out: dict[str, str] = {}
    for p in reg.get("practices", []):
        out[str(p.get("name_en", "")).strip().lower()] = p["id"]
        out[str(p["id"]).strip().lower()] = p["id"]
    return out


def direction_of_indicator(indicator: str, country: str = "ET") -> int:
    """+1 when higher is better for the legacy indicator's canonical outcome, -1 when lower is."""
    from rag.graph.query import LEGACY_INDICATOR_OF

    outcome_id = next((o for o, ind in LEGACY_INDICATOR_OF.items() if ind == indicator), None)
    reg = registry_service.get_registry(country)
    for c in reg.get("challenges", []):
        for o in c.get("objectives", []):
            if o.get("id") == outcome_id and o.get("direction") is not None:
                return -1 if int(o["direction"]) < 0 else 1
    return 1


def candidates_for_family(practice_family: str, country: str = "ET") -> list[str]:
    """Registry practice ids of one frozen practice family (the /advise additive list)."""
    reg = registry_service.get_registry(country)
    return sorted(p["id"] for p in reg.get("practices", []) if p.get("family") == practice_family)


def context_of(lat: float, lon: float) -> dict[str, Any]:
    """The engine's context for a point: the release layers when the geodata release is active
    (``ctx_<layer>`` plus the legacy names), else the legacy 11 fields."""
    legacy = svc.extract_context(lat, lon)
    ctx = dict(legacy)
    ext = legacy.get("extended") or {}
    for k, v in ext.items():
        ctx[f"ctx_{k}"] = v
    if ext:
        for legacy_name, layer in (("Rainfall", "precip_annual"), ("Altitude_r", "elevation"), ("temp_mean_annual", "temp_mean_annual"),
                                   ("precip_seasonality", "precip_seasonality"), ("slope", "slope"), ("soil_clay", "soil_clay"),
                                   ("lgp_days", "lgp_days"), ("soil_ph", "soil_ph"), ("soil_soc", "soil_soc")):
            ctx.setdefault(f"ctx_{layer}", legacy.get(legacy_name))
        ctx["ctx_land_cover"] = legacy.get("land_cover")
    ctx.pop("extended", None)
    return ctx


# ----------------------------------------------------------------- ranking
def rank(lat: float, lon: float, challenge_id: str, outcome_id: str, crop_type: str | None = None,
         top_n: int = 5, country: str = "ET", *, engine: Any = None, context_fn: Callable[[float, float], dict[str, Any]] | None = None,
         settings: Any = None) -> dict[str, Any]:
    """Rank the registry candidates of ``(challenge, objective)`` for a site with M1 v2."""
    s = settings or get_settings()
    if not enabled(s):
        raise EngineUnavailable("ADVISOR_ENGINE is 'legacy'; set ADVISOR_ENGINE=m1_v2 to serve POST /rank.")
    eng = engine if engine is not None else load(s)
    challenge, objective, cands = registry_lookup(challenge_id, outcome_id, country)
    ctx = (context_fn or context_of)(lat, lon)
    items, ordering = _rank_items(eng, ctx, cands, outcome_id, objective.get("objective_group"), crop_type, s)
    direction = int(objective.get("direction") or 1)
    return {"engine": engine_name(s), "country": country, "challenge_id": challenge_id, "outcome_id": outcome_id,
            "objective_group": objective.get("objective_group"), "direction": direction,
            "context": {k: v for k, v in ctx.items() if not k.startswith("ctx_")}, "n_candidates": len(cands),
            "items": items[:top_n], "release": ctx.get("release"), "ordering": ordering}


def _rank_items(eng: Any, ctx: dict[str, Any], cands: list[str], outcome_id: str, objective_group: str | None,
                crop_type: str | None, settings: Any = None) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """M1 v2's items in display order and, with ``ADVISOR_ENGINE=m3``, the gate's ordering record."""
    ordering = None
    if engine_name(settings) == "m3":
        from app.services import m3_service

        raw, ordering = m3_service.ranker(settings, m1_engine=eng).rank(ctx, list(cands), outcome_id, objective_group,
                                                                         crop_type, {"loc_precision": "site"})
    else:
        raw = eng.rank(ctx, list(cands), outcome_id, objective_group, crop_type, {"loc_precision": "site"}, qkey="api")
    items = []
    for r in sorted(raw, key=lambda r: -r["score"]):
        lead = LEAD_LABEL.get(r["lead_source"], "documented")
        items.append({"practice_id": r["practice_id"], "score": r["score"], "est_lrr": r["est_lrr"],
                      "lo": r["lo"], "hi": r["hi"], "lead_source": lead, "lead_label": FUSION_WORDING[lead],
                      "citations": list(r.get("citations") or []), "components": r.get("components") or {}})
    return items, ordering


def rank_for_family(lat: float, lon: float, practice_family: str, indicator: str, crop_type: str | None = None,
                    country: str = "ET", *, engine: Any = None, context_fn: Callable[[float, float], dict[str, Any]] | None = None,
                    settings: Any = None) -> list[dict[str, Any]] | None:
    """The additive ``m1_v2`` list of /advise: the family's registry practices ranked for the
    legacy indicator's canonical outcome. ``None`` when the engine is not enabled."""
    out = rank_for_family_with_ordering(lat, lon, practice_family, indicator, crop_type, country, engine=engine,
                                        context_fn=context_fn, settings=settings)
    return None if out is None else out[0]


def rank_for_family_with_ordering(lat: float, lon: float, practice_family: str, indicator: str, crop_type: str | None = None,
                                  country: str = "ET", *, engine: Any = None,
                                  context_fn: Callable[[float, float], dict[str, Any]] | None = None,
                                  settings: Any = None) -> tuple[list[dict[str, Any]], dict[str, Any] | None] | None:
    """:func:`rank_for_family` with the ``m3`` gate's ordering record (``None`` on the other engines)."""
    s = settings or get_settings()
    if not enabled(s):
        return None
    from rag.graph.query import LEGACY_INDICATOR_OF

    outcome_id = next((o for o, ind in LEGACY_INDICATOR_OF.items() if ind == indicator), None)
    if outcome_id is None:
        return None
    eng = engine if engine is not None else load(s)
    cands = candidates_for_family(practice_family, country)
    if not cands:
        return [], None
    reg = registry_service.get_registry(country)
    group = next((o.get("objective_group") for c in reg.get("challenges", []) for o in c.get("objectives", []) if o.get("id") == outcome_id), None)
    ctx = (context_fn or context_of)(lat, lon)
    return _rank_items(eng, ctx, cands, outcome_id, group, crop_type, s)
