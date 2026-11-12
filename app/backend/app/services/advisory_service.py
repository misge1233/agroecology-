"""Evidence-tiered advisory — the service behind POST /advise (Phase P9).

One call does what the Advisor needs: it runs the canonical engine (wrap,
never fork), measures how much field-trial evidence stands behind the top of
the ranking, decides the **mode** and — when evidence is thin or absent —
proposes documented practices with provenance:

* ``model-led``     the ranking is well supported; the model's payload is
                    returned unchanged and no candidates are added;
* ``hybrid``        the engine ranked, but evidence is thin or from other
                    moisture zones; the ranking is kept, flagged, and a
                    knowledge shortlist is listed alongside;
* ``knowledge-led`` the engine cannot rank ("No field evidence" or an
                    unsupported pair); only documented practices are shown.

The model payload is the exact ``/recommend`` response (or ``None``);
nothing here adds, rounds or re-estimates a number (CLAUDE.md doctrine 1 as
amended in P9). Every collaborator is injectable for tests.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from app.config import get_settings
from app.i18n import t, term
from app.services import evidence_service as ev
from app.services import explain_service as es
from app.services import fusion_service as fusion
from app.services import recommender_service as svc

logger = logging.getLogger(__name__)


def classify_engine_error(exc: Exception) -> str | None:
    """``"no_evidence"`` / ``"unsupported"`` for the two rank-impossible errors, else None."""
    msg = str(exc)
    if msg.startswith(ev.NO_EVIDENCE_PREFIX):
        return "no_evidence"
    if ev.UNSUPPORTED_MARKER in msg:
        return "unsupported"
    return None


def advise(
    lat: float,
    lon: float,
    practice_family: str,
    indicator: str,
    crop_type: str | None = None,
    top_n: int = 3,
    language: str = "en",
    *,
    graph_query: Any = None,
    guidance_retriever: Any = None,
    recommend_fn: Callable[..., dict[str, Any]] | None = None,
    context_fn: Callable[[float, float], dict[str, Any]] | None = None,
    pool_fn: Callable[[str], list[str]] | None = None,
    indicators: list[str] | None = None,
    settings: Any = None,
    stats_fn: Callable[[], Any] | None = None,
    rmse_fn: Callable[[], dict[str, float]] | None = None,
    constraints: list[str] | None = None,
) -> dict[str, Any]:
    """The advisory for one request. Never raises for a rank-impossible pair."""
    s = settings or get_settings()
    recommend = recommend_fn or svc.recommend
    context_of = context_fn or svc.extract_context
    pool_of = pool_fn or (lambda family: svc.practices_by_family().get(family, []))
    all_indicators = list(indicators or svc.INDICATORS)

    model: dict[str, Any] | None = None
    engine_error: str | None = None
    try:
        # U9: score EVERY grounded practice (the engine returns pool[:top_n]),
        # so the fused ordering can choose the top N; the engine's numbers are
        # carried unchanged.
        model = recommend(
            lat=lat, lon=lon, practice_family=practice_family, indicator=indicator,
            crop_type=crop_type, top_n=ALL_PRACTICES,
        )
    except ValueError as exc:
        engine_error = classify_engine_error(exc)
        if engine_error is None:
            raise
        logger.info("advise: engine cannot rank (%s) — knowledge-led", engine_error)

    gq = graph_query if graph_query is not None else es.get_graph_query()
    practices: list[dict[str, Any]] = []
    grounded: set[str] = set()
    if model is not None:
        grounded = {r["practice"] for r in model["details"].get("ranked") or []}
        bundles = fusion.fuse(model, graph_query=gq, settings=s, stats_fn=stats_fn, rmse_fn=rmse_fn)
        ordered = fusion.order(bundles, str(s.advisory_ordering))
        _flag_request_fit(ordered, constraints or [], crop_type)
        practices = ordered[:top_n]
        # A6: when the user named a soil constraint and no shown practice
        # addresses it, the best-placed practice that does is added, flagged.
        if constraints and not any(b["matches_constraints"] for b in practices):
            pick = next((b for b in ordered[top_n:] if b["matches_constraints"]), None)
            if pick is not None:
                practices = [*practices, {**pick, "constraint_pick": True}]
        model = _reorder_model(model, [b["practice"] for b in practices])

    context = dict(((model or {}).get("details") or {}).get("context") or {}) if model else {}
    if not context:
        try:
            context = dict(context_of(lat, lon) or {})
        except Exception as exc:  # context is needed for the UI card; degrade
            logger.warning("advise: context resolution failed (%s)", exc)
            context = {}

    sufficiency = ev.evidence_sufficiency(
        model, practice_family, indicator, context, gq, engine_error=engine_error, settings=s,
    )
    mode = sufficiency.pop("mode")
    reasons = sufficiency.pop("reasons")

    candidates: list[dict[str, Any]] = []
    funnel: dict[str, Any] = {}
    if mode != ev.MODEL_LED:
        g = guidance_retriever if guidance_retriever is not None else es.get_guidance_retriever()
        ranked = [r.get("practice") for r in ((model or {}).get("details") or {}).get("ranked") or []]
        try:
            pool = list(pool_of(practice_family))
        except Exception as exc:
            logger.warning("advise: candidate pool unavailable (%s)", exc)
            pool = []
        candidates, funnel = ev.knowledge_candidates(
            practice_family=practice_family, indicator=indicator, context=context, pool=pool,
            indicators=all_indicators, graph_query=gq, guidance_retriever=g,
            seeds=[p for p in ranked if p][:3], crop_type=crop_type, language=language, settings=s,
            # U9 (B5): documented ∩ ranked = ∅. Practices with field evidence
            # for THIS objective belong to the ranking, never to the documented list.
            exclude_practices=grounded, shown_practices=set(p for p in ranked if p),
        )
        if mode == ev.KNOWLEDGE_LED and not candidates:
            reasons.append({"key": "mode.reason.no_candidates", "params": {}})

    return {
        "mode": mode,
        "reasons": reasons,
        "model": model,
        "practices": practices,
        "ordering": str(s.advisory_ordering),
        "fusion": fusion_settings(s),
        "constraints": list(constraints or []),
        "knowledge_candidates": candidates,
        "evidence_sufficiency": sufficiency,
        "context": context,
        "language": language,
        "funnel": funnel,
        # E5: with ADVISOR_ENGINE=m1_v2, the same request ranked by Methodology 1 v2 (additive;
        # null with the default engine or when the artifact cannot answer).
        "m1_v2": _m1_ranking(lat, lon, practice_family, indicator, crop_type, s),
    }


def _m1_ranking(lat: float, lon: float, practice_family: str, indicator: str, crop_type: str | None,
                settings: Any) -> list[dict[str, Any]] | None:
    from app.services import m1_service

    if not m1_service.enabled(settings):
        return None
    try:
        return m1_service.rank_for_family(lat, lon, practice_family, indicator, crop_type, settings=settings)
    except Exception as exc:  # noqa: BLE001 - degrade: the legacy advisory stands
        logger.warning("advise: m1_v2 ranking unavailable (%s)", exc)
        return None


#: Ask the engine for every grounded practice (families have at most a few dozen).
ALL_PRACTICES = 1000

#: Practice components that address a named soil constraint (A6).
CONSTRAINT_COMPONENTS: dict[str, set[str]] = {
    "acidic_soil": {"pH Control"},
    "salinity": set(),
    "waterlogging": set(),
}
#: Components that mean growing a different crop (flagged when the user named theirs).
REPLACES_CROP_COMPONENTS: set[str] = {"Drought Tolerant Crops"}


def _flag_request_fit(bundles: list[dict[str, Any]], constraints: list[str], crop_type: str | None) -> None:
    """Mark each bundle with the constraints it addresses and whether it replaces the user's crop."""
    for b in bundles:
        try:
            parts = set(ev._decompose(b["practice"]))
        except Exception:
            parts = set()
        b["matches_constraints"] = [c for c in constraints if parts & CONSTRAINT_COMPONENTS.get(c, set())]
        b["replaces_crop"] = bool(crop_type) and bool(parts & REPLACES_CROP_COMPONENTS)
        b.setdefault("constraint_pick", False)


def fusion_settings(settings: Any = None) -> dict[str, Any]:
    """The evidence-fusion knobs, as published by /metadata and echoed by /advise."""
    s = settings or get_settings()
    return {
        "ordering": str(s.advisory_ordering),
        "confidence_k_sd": float(s.confidence_k_sd),
        "disagree_pct": float(s.evidence_disagree_pct),
        "caution_pct": float(s.headline_caution_pct),
        "min_obs_in_zone": int(s.evidence_min_obs_in_zone),
    }


def _reorder_model(model: dict[str, Any], practices: list[str]) -> dict[str, Any]:
    """The engine payload restricted to ``practices`` in that order — items unchanged."""
    by_ranked = {r["practice"]: r for r in model["details"].get("ranked") or []}
    by_clean = {r["practice"]: r for r in model.get("recommendations") or []}
    out = dict(model)
    out["recommendations"] = [by_clean[p] for p in practices if p in by_clean]
    out["details"] = {**model["details"], "ranked": [by_ranked[p] for p in practices if p in by_ranked]}
    return out


# ------------------------------------------------------------- narratives
def reason_text(reason: dict[str, Any], language: str) -> str:
    """Render one reason (catalog key + params) in ``language``."""
    params = dict(reason.get("params") or {})
    if "practice" in params:
        # U9 (D11): display name in the reply language; the reason dict itself
        # (the data contract) keeps the frozen English practice string.
        from app.services.practice_names import practice_name

        params["practice"] = practice_name(str(params["practice"]), language)
    # U9 (D3): the right plural for every count ("1 study", "3 studies").
    if "n_studies" in params:
        params["studies_word"] = t(language, "kc.study" if int(params["n_studies"]) == 1 else "kc.studies")
    if "n_obs" in params:
        params["obs_word"] = t(language, "eb.observation" if int(params["n_obs"]) == 1 else "eb.observations")
    return t(language, reason["key"], **params)


def mode_label(mode: str, language: str) -> str:
    return t(language, {ev.MODEL_LED: "mode.model_led", ev.HYBRID: "mode.hybrid", ev.KNOWLEDGE_LED: "mode.knowledge_led"}[mode])


def hybrid_note(advisory: dict[str, Any], language: str) -> str:
    """Sentence appended to the model narrative in hybrid mode (empty otherwise)."""
    if advisory.get("mode") != ev.HYBRID:
        return ""
    n = len(advisory.get("knowledge_candidates") or [])
    if n == 0:
        return ""
    return t(language, "mode.hybrid_note", n=n,
             practices_word=t(language, "mode.practice" if n == 1 else "mode.practices"),
             is_are=t(language, "eb.is" if n == 1 else "eb.are"))


def knowledge_led_text(advisory: dict[str, Any], practice_family: str, indicator: str, language: str) -> str:
    """Deterministic chat answer for knowledge-led mode — counts and citations only."""
    challenge = practice_family if language == "en" else term(language, "family", practice_family)
    objective = indicator if language == "en" else term(language, "indicator", indicator)
    candidates = advisory.get("knowledge_candidates") or []
    if not candidates:
        return t(language, "mode.knowledge_led.none", challenge=challenge, objective=objective)
    lines = [t(language, "mode.knowledge_led.lead", challenge=challenge, objective=objective)]
    for cand in candidates:
        lines.append(t(language, "mode.knowledge_led.item", label=cand["label"], rationale=cand["rationale_text"]))
    return "\n".join(lines)
