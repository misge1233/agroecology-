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
        model = recommend(
            lat=lat, lon=lon, practice_family=practice_family, indicator=indicator,
            crop_type=crop_type, top_n=top_n,
        )
    except ValueError as exc:
        engine_error = classify_engine_error(exc)
        if engine_error is None:
            raise
        logger.info("advise: engine cannot rank (%s) — knowledge-led", engine_error)

    context = dict(((model or {}).get("details") or {}).get("context") or {}) if model else {}
    if not context:
        try:
            context = dict(context_of(lat, lon) or {})
        except Exception as exc:  # context is needed for the UI card; degrade
            logger.warning("advise: context resolution failed (%s)", exc)
            context = {}

    gq = graph_query if graph_query is not None else es.get_graph_query()
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
        )
        if mode == ev.KNOWLEDGE_LED and not candidates:
            reasons.append({"key": "mode.reason.no_candidates", "params": {}})

    return {
        "mode": mode,
        "reasons": reasons,
        "model": model,
        "knowledge_candidates": candidates,
        "evidence_sufficiency": sufficiency,
        "context": context,
        "language": language,
        "funnel": funnel,
    }


# ------------------------------------------------------------- narratives
def reason_text(reason: dict[str, Any], language: str) -> str:
    """Render one reason (catalog key + params) in ``language``."""
    params = dict(reason.get("params") or {})
    if "practice" in params:
        params["practice"] = params["practice"]  # frozen data-contract string stays English
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
