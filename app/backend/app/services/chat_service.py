"""Chat service — drives the canonical CSA advisor over SSE.

Pipeline (evidence-first):
1. Extract challenge / objective / location (incl. place-name geocoding).
2. If slots incomplete → ask only for what is missing (no invented practices).
3. If complete → call ``recommend()`` server-side, emit structured cards, then
   phrase a short narrative grounded in that evidence.
4. Follow-ups (why/how) reuse the prior recommendation; social acks skip tools.

The ML/agent logic is canonical in ``backend/advisor_agent.py``; we reuse its
``SYSTEM_PROMPT`` for narrative phrasing and the offline ``AgroAdvisor`` fallback.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator

from app.config import get_settings
from app.services import advisory_service as advisory
from app.services import intent_llm
from app.services import recommender_service as svc
from app.services.openai_chat import (
    OPENAI_CHAT_COMPLETIONS_URL,
    OPENAI_CHAT_MODEL,
    build_messages,
    generate_turn,
    make_client,
)
from app.i18n import reply_instruction, t
from app.services.slot_extraction import (
    clarification_message,
    evidence_summary,
    extract_slots,
)

# Canonical agent building blocks.
from advisor_agent import (  # noqa: E402
    SYSTEM_PROMPT,
    _is_social_ack,
)

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 4

# Llama-family models sometimes paste tool calls as plain text instead of using
# the API tool_calls channel. Strip those so users never see the markup.
_LEAKED_TOOL_RE = re.compile(
    r"(?is)"
    r"(?:<function[=:]?\s*recommend[^>]*>.*?</function>)|"
    r"(?:\(function\s*=\s*recommend\s*>.*?</function>)|"
    r"(?:function\s*=\s*recommend\s*>?\s*\{.*?\}(?:\s*</function>)?)"
)

_PRACTICE_CLAIM_RE = re.compile(
    r"(?i)\b(i(?:'d| would)?\s+recommend|you\s+should|try\s+implementing|"
    r"implementing\s+\w+|contour farming|cover crops|terraces?)\b"
)


def _evt(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _query_key(rec: dict | None) -> str | None:
    if not rec:
        return None
    return json.dumps(rec.get("query"), sort_keys=True, default=str)


def _chunk(text: str, step: int = 24):
    for i in range(0, len(text), step):
        yield text[i : i + step]


def strip_leaked_tool_markup(text: str) -> str:
    """Remove raw function-call blobs that models sometimes emit as content."""
    if not text:
        return text
    cleaned = _LEAKED_TOOL_RE.sub("", text)
    cleaned = re.sub(
        r'(?is)\{\s*"lat"\s*:\s*-?\d+(?:\.\d+)?\s*,\s*"lon"\s*:.*?\}',
        "",
        cleaned,
    )
    cleaned = re.sub(r'^[\s"\'()]+|[\s"\'()]+$', "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _prior_recommendation_context(rec: dict[str, Any]) -> str:
    return (
        "Previous recommendation (reuse for follow-ups; call recommend ONLY if the "
        "user changes location, practice_family, indicator, or crop):\n"
        + json.dumps(rec, default=str)
    )


def _social_reply(has_prior: bool, language: str = "en") -> str:
    """Thanks/ok/bye reply — catalogued per language (U1)."""
    return t(language, "social.with_prior" if has_prior else "social.no_prior")


async def _stream_text(text: str) -> AsyncIterator[str]:
    for piece in _chunk(text):
        yield _evt({"type": "token", "text": piece})
    yield _evt({"type": "done"})


def _trim_recommendation(rec: dict[str, Any], top_n: int) -> dict[str, Any]:
    """Keep API/UI aligned when the model returns more practices than requested."""
    if top_n < 1:
        return rec
    recs = rec.get("recommendations") or []
    ranked = (rec.get("details") or {}).get("ranked") or []
    if len(recs) <= top_n and len(ranked) <= top_n:
        return rec
    out = dict(rec)
    out["recommendations"] = recs[:top_n]
    details = dict(rec.get("details") or {})
    details["ranked"] = ranked[:top_n]
    out["details"] = details
    return out


def _slots_changed(slots, last_recommendation: dict[str, Any] | None) -> bool:
    if not last_recommendation:
        return True
    q = last_recommendation.get("query") or {}
    if slots.practice_family and slots.practice_family != q.get("practice_family"):
        return True
    if slots.indicator and slots.indicator != q.get("indicator"):
        return True
    if slots.crop_type and slots.crop_type != q.get("crop_type"):
        return True
    if slots.lat is not None and slots.lon is not None:
        try:
            if abs(float(slots.lat) - float(q["lat"])) > 1e-4:
                return True
            if abs(float(slots.lon) - float(q["lon"])) > 1e-4:
                return True
        except (KeyError, TypeError, ValueError):
            return True
    return False


def _run_recommend_from_slots(slots, top_n: int) -> dict[str, Any]:
    assert slots.is_complete
    return svc.recommend(
        lat=float(slots.lat),
        lon=float(slots.lon),
        practice_family=slots.practice_family,
        indicator=slots.indicator,
        crop_type=slots.crop_type,
        top_n=top_n,
    )


def _advise_from_slots(slots, top_n: int, language: str) -> dict[str, Any]:
    """The evidence-tiered advisory (P9) for a complete slot set — wraps recommend()."""
    assert slots.is_complete
    return advisory.advise(
        lat=float(slots.lat),
        lon=float(slots.lon),
        practice_family=slots.practice_family,
        indicator=slots.indicator,
        crop_type=slots.crop_type,
        top_n=top_n,
        language=language,
    )


def _advisory_event(result: dict[str, Any], slots: Any) -> dict[str, Any]:
    """The SSE ``advisory`` payload: everything but the model payload (sent as ``recommendation``).

    ``query`` repeats the resolved slots so the UI can deep-link a knowledge-led
    turn (which carries no ``recommendation.query``) to the Advisor.
    """
    return {
        "mode": result["mode"],
        "reasons": result["reasons"],
        "knowledge_candidates": result["knowledge_candidates"],
        "evidence_sufficiency": result["evidence_sufficiency"],
        "context": result.get("context") or {},
        "query": {
            "lat": float(slots.lat),
            "lon": float(slots.lon),
            "practice_family": slots.practice_family,
            "indicator": slots.indicator,
            "crop_type": slots.crop_type,
        },
    }


async def stream_chat(
    message: str,
    history: list[dict[str, str]],
    last_recommendation: dict[str, Any] | None = None,
    top_n: int = 1,
    language: str = "en",
    hint: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """SSE async generator. Emits slots / token / recommendation / done / error.

    ``language`` (U1) selects the catalog for every deterministic text and adds
    a "Reply in …" line to the LLM prompts. ``hint`` (U2) carries the
    structured values behind a quick-reply chip; Amharic / Afaan Oromoo free
    text goes through one validated LLM reading when a key is configured and
    otherwise steers the user to the chips / Advisor.
    """
    if _is_social_ack(message):
        async for chunk in _stream_text(_social_reply(bool(last_recommendation), language)):
            yield chunk
        return

    settings = get_settings()
    slots = extract_slots(
        message,
        history,
        last_recommendation,
        allow_network_geocode=False,
        hint=hint,
    )
    steer_to_advisor = False
    if intent_llm.needs_llm(message, language, slots):
        if settings.openai_api_key:
            slots = await intent_llm.enrich_with_llm(slots, message, language, settings)
        else:
            steer_to_advisor = True
    yield _evt({"type": "slots", "data": slots.to_event()})

    # Prior result still valid (no slot changes): follow-ups / chitchat / repeat asks.
    if last_recommendation and not _slots_changed(slots, last_recommendation):
        if slots.is_followup or not slots.wants_advice:
            async for chunk in _stream_followup(message, history, last_recommendation, settings, language):
                yield chunk
            return
        # Same complete request again — reuse scored evidence, don't invent new practices.
        if slots.is_complete:
            rec = _trim_recommendation(last_recommendation, top_n)
            yield _evt({"type": "recommendation", "data": rec})
            narrative = await _narrative_for_recommendation(message, history, rec, settings, language)
            for piece in _chunk(narrative):
                yield _evt({"type": "token", "text": piece})
            yield _evt({"type": "done"})
            return

    if not slots.is_complete:
        # Never invent agronomic advice when evidence can't be scored yet.
        text = clarification_message(slots, language)
        if steer_to_advisor:
            text = t(language, "clarify.use_advisor") + "\n\n" + text
        async for chunk in _stream_text(text):
            yield chunk
        return

    # Complete slots → score with the ML engine first (source of truth). P9:
    # through the evidence-tiered advisory, so a thin or empty evidence base
    # becomes a labelled mode with documented practices, not an error.
    try:
        result = _advise_from_slots(slots, top_n, language)
    except Exception as exc:
        logger.exception("Advise from slots failed: %s", exc)
        yield _evt({"type": "error", "message": _error_message(exc, language)})
        return

    yield _evt({"type": "advisory", "data": _advisory_event(result, slots)})

    if result.get("model"):
        recommendation = _trim_recommendation(result["model"], top_n)
        yield _evt({"type": "recommendation", "data": recommendation})
        narrative = await _narrative_for_recommendation(message, history, recommendation, settings, language)
        # Model-led: byte-identical to the pre-P9 narrative. Hybrid: one sentence more.
        narrative += advisory.hybrid_note(result, language)
    else:
        narrative = advisory.knowledge_led_text(
            result, slots.practice_family, slots.indicator, language
        )
    for piece in _chunk(narrative):
        yield _evt({"type": "token", "text": piece})
    yield _evt({"type": "done"})


def followup_system_instruction(last_recommendation: dict[str, Any], language: str = "en") -> str:
    """System prompt for a why/how follow-up (pure; tested in test_i18n.py)."""
    system_instruction = SYSTEM_PROMPT + "\n\n" + _prior_recommendation_context(
        last_recommendation
    )
    system_instruction += (
        "\n\nThis is a FOLLOW-UP. Reuse the previous recommendation details. "
        "Do NOT invent new practices or numbers. Do NOT call recommend unless "
        "the user clearly changed location, challenge, objective, or crop."
    )
    return system_instruction + "\n\n" + reply_instruction(language)


async def _stream_followup(
    message: str,
    history: list[dict[str, str]],
    last_recommendation: dict[str, Any],
    settings,
    language: str = "en",
) -> AsyncIterator[str]:
    """Answer why/how from prior evidence — no new invented practices."""
    if not settings.openai_api_key:
        async for chunk in _stream_offline_followup(message, last_recommendation, language):
            yield chunk
        return
    try:
        client = make_client(settings.openai_api_key, settings.openai_timeout_seconds)
    except Exception:
        async for chunk in _stream_offline_followup(message, last_recommendation, language):
            yield chunk
        return

    system_instruction = followup_system_instruction(last_recommendation, language)
    messages = build_messages(history, message, system_instruction)
    try:
        async with client:
            # tool_choice auto but we discard any tool call and fall back to summary
            for _ in range(_MAX_TOOL_ROUNDS):
                messages, text, function_calls = await generate_turn(
                    client, model=OPENAI_CHAT_MODEL, messages=messages
                )
                if function_calls:
                    # Ignore tool calls on pure follow-ups — keep evidence fixed.
                    text = evidence_summary(last_recommendation, language)
                    for piece in _chunk(text):
                        yield _evt({"type": "token", "text": piece})
                    yield _evt({"type": "done"})
                    return
                if text:
                    text = strip_leaked_tool_markup(text)
                    if text:
                        for piece in _chunk(text):
                            yield _evt({"type": "token", "text": piece})
                    yield _evt({"type": "done"})
                    return
            async for chunk in _stream_offline_followup(message, last_recommendation, language):
                yield chunk
    except Exception as exc:
        logger.exception("Follow-up stream failed: %s", exc)
        async for chunk in _stream_offline_followup(message, last_recommendation, language):
            yield chunk


async def _stream_offline_followup(
    message: str, last_recommendation: dict[str, Any], language: str = "en"
) -> AsyncIterator[str]:
    """Rule-based follow-up without an LLM.

    The canonical ``AgroAdvisor._offline`` heuristics phrase English prose and
    are not forked for other languages (CLAUDE.md doctrine 3); for ``am``/``om``
    the deterministic, catalogued evidence summary is returned instead.
    """
    if language != "en":
        async for chunk in _stream_text(evidence_summary(last_recommendation, language)):
            yield chunk
        return
    from advisor_agent import AgroAdvisor

    advisor = AgroAdvisor()
    advisor._last = last_recommendation
    reply = advisor._offline(message)
    reply = strip_leaked_tool_markup(reply or "") or evidence_summary(last_recommendation)
    async for chunk in _stream_text(reply):
        yield chunk


def narrative_system_instruction(recommendation: dict[str, Any], language: str = "en") -> str:
    """System prompt for phrasing a server-computed recommendation (pure; tested)."""
    return (
        SYSTEM_PROMPT
        + "\n\nCRITICAL: A recommendation was ALREADY computed by the server. "
        "Phrase the DEFAULT clean answer using ONLY this JSON. "
        "Do not call tools. Do not invent practices, percentages, or coordinates.\n"
        + json.dumps(recommendation, default=str)
        + "\n\n" + reply_instruction(language)
    )


async def _narrative_for_recommendation(
    message: str,
    history: list[dict[str, str]],
    recommendation: dict[str, Any],
    settings,
    language: str = "en",
) -> str:
    """Phrase the default answer from scored evidence; never free-invent practices."""
    fallback = evidence_summary(recommendation, language)
    if not settings.openai_api_key:
        return fallback
    try:
        client = make_client(settings.openai_api_key, settings.openai_timeout_seconds)
    except Exception:
        return fallback

    system_instruction = narrative_system_instruction(recommendation, language)
    messages = build_messages(history, message, system_instruction)
    # Remove tools from this narrative turn by using a lightweight completion.
    try:
        async with client:
            payload = {
                "model": OPENAI_CHAT_MODEL,
                "messages": messages,
                "temperature": 0.3,
            }
            resp = await client.post(OPENAI_CHAT_COMPLETIONS_URL, json=payload)
            resp.raise_for_status()
            text = (resp.json()["choices"][0]["message"].get("content") or "").strip()
            text = strip_leaked_tool_markup(text)
            if not text:
                return fallback
            # If the model still invents advice that doesn't mention a scored practice,
            # prefer the deterministic summary.
            practices = [
                (r.get("practice") or "").lower()
                for r in recommendation.get("recommendations") or []
            ]
            practices = [p for p in practices if p]
            if practices and not any(p in text.lower() for p in practices):
                if _PRACTICE_CLAIM_RE.search(text):
                    return fallback
            return text
    except Exception as exc:
        logger.info("Narrative phrasing fell back to template: %s", exc)
        return fallback


async def run_chat(
    message: str,
    history: list[dict[str, str]],
    last_recommendation: dict[str, Any] | None = None,
    top_n: int = 1,
    language: str = "en",
    hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Non-streaming turn — aggregates the SSE stream into a single JSON payload."""
    reply = ""
    recommendation: dict[str, Any] | None = None
    slots: dict[str, Any] | None = None
    advisory_data: dict[str, Any] | None = None
    error: str | None = None
    async for chunk in stream_chat(message, history, last_recommendation, top_n, language, hint):
        raw = chunk[len("data: ") :].strip()
        if not raw:
            continue
        payload = json.loads(raw)
        t = payload.get("type")
        if t == "token":
            reply += payload.get("text", "")
        elif t == "recommendation":
            recommendation = payload.get("data")
        elif t == "slots":
            slots = payload.get("data")
        elif t == "advisory":
            advisory_data = payload.get("data")
        elif t == "error":
            error = payload.get("message")
    return {
        "reply": reply,
        "recommendation": recommendation,
        "slots": slots,
        "advisory": advisory_data,
        "error": error,
    }


def _error_message(exc: Exception, language: str = "en") -> str:
    """User-facing error text. Engine validation errors pass through verbatim
    (they are the data contract's own English wording); the two generic
    messages come from the catalog."""
    msg = str(exc)
    low = msg.lower()
    if "outside ethiopia" in low or "outside" in low and "ethiopia" in low:
        return msg
    if "not supported" in low or "objective" in low:
        return msg
    if "429" in low or "rate limit" in low or "resource exhausted" in low:
        return t(language, "error.rate_limit")
    return t(language, "error.generic")
