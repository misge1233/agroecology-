"""Chat service — drives the canonical CSA advisor over SSE.

Pipeline (evidence-first):
1. Extract challenge / objective / location (incl. place-name geocoding).
2. If slots incomplete → ask only for what is missing (no invented practices).
3. If complete → call ``recommend()`` server-side, emit structured cards, then
   phrase a short narrative grounded in that evidence.
4. Follow-ups (why/how) reuse the prior recommendation; social acks skip tools.

The ML/agent logic is canonical in ``backend/groq_agent.py``; we reuse its
``SYSTEM_PROMPT`` for narrative phrasing and the offline ``CSAAdvisor`` fallback.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator

from app.config import get_settings
from app.services import recommender_service as svc
from app.services.openai_chat import (
    OPENAI_CHAT_COMPLETIONS_URL,
    OPENAI_CHAT_MODEL,
    build_messages,
    generate_turn,
    make_client,
)
from app.services.slot_extraction import (
    clarification_message,
    evidence_summary,
    extract_slots,
)

# Canonical agent building blocks.
from groq_agent import (  # noqa: E402
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


def _social_reply(has_prior: bool) -> str:
    if has_prior:
        return (
            "You're welcome — glad it helped. Ask anytime if you want to know why, "
            "how to apply it, or try a different location, crop, or goal."
        )
    return (
        "You're welcome. Share a map location, challenge area, and objective "
        "whenever you're ready and I'll recommend CSA practices."
    )


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


async def stream_chat(
    message: str,
    history: list[dict[str, str]],
    last_recommendation: dict[str, Any] | None = None,
    top_n: int = 1,
) -> AsyncIterator[str]:
    """SSE async generator. Emits slots / token / recommendation / done / error."""
    if _is_social_ack(message):
        async for chunk in _stream_text(_social_reply(bool(last_recommendation))):
            yield chunk
        return

    settings = get_settings()
    slots = extract_slots(
        message,
        history,
        last_recommendation,
        allow_network_geocode=False,
    )
    yield _evt({"type": "slots", "data": slots.to_event()})

    # Prior result still valid (no slot changes): follow-ups / chitchat / repeat asks.
    if last_recommendation and not _slots_changed(slots, last_recommendation):
        if slots.is_followup or not slots.wants_advice:
            async for chunk in _stream_followup(
                message, history, last_recommendation, settings
            ):
                yield chunk
            return
        # Same complete request again — reuse scored evidence, don't invent new practices.
        if slots.is_complete:
            rec = _trim_recommendation(last_recommendation, top_n)
            yield _evt({"type": "recommendation", "data": rec})
            narrative = await _narrative_for_recommendation(
                message, history, rec, settings
            )
            for piece in _chunk(narrative):
                yield _evt({"type": "token", "text": piece})
            yield _evt({"type": "done"})
            return

    if not slots.is_complete:
        # Never invent agronomic advice when evidence can't be scored yet.
        async for chunk in _stream_text(clarification_message(slots)):
            yield chunk
        return

    # Complete slots → score with the ML engine first (source of truth).
    try:
        recommendation = _trim_recommendation(
            _run_recommend_from_slots(slots, top_n), top_n
        )
    except Exception as exc:
        logger.exception("Recommend from slots failed: %s", exc)
        yield _evt({"type": "error", "message": _error_message(exc)})
        return

    yield _evt({"type": "recommendation", "data": recommendation})

    narrative = await _narrative_for_recommendation(
        message, history, recommendation, settings
    )
    for piece in _chunk(narrative):
        yield _evt({"type": "token", "text": piece})
    yield _evt({"type": "done"})


async def _stream_followup(
    message: str,
    history: list[dict[str, str]],
    last_recommendation: dict[str, Any],
    settings,
) -> AsyncIterator[str]:
    """Answer why/how from prior evidence — no new invented practices."""
    if not settings.openai_api_key:
        async for chunk in _stream_offline_followup(message, last_recommendation):
            yield chunk
        return
    try:
        client = make_client(settings.openai_api_key, settings.openai_timeout_seconds)
    except Exception:
        async for chunk in _stream_offline_followup(message, last_recommendation):
            yield chunk
        return

    system_instruction = SYSTEM_PROMPT + "\n\n" + _prior_recommendation_context(
        last_recommendation
    )
    system_instruction += (
        "\n\nThis is a FOLLOW-UP. Reuse the previous recommendation details. "
        "Do NOT invent new practices or numbers. Do NOT call recommend unless "
        "the user clearly changed location, challenge, objective, or crop."
    )
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
                    text = evidence_summary(last_recommendation)
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
            async for chunk in _stream_offline_followup(message, last_recommendation):
                yield chunk
    except Exception as exc:
        logger.exception("Follow-up stream failed: %s", exc)
        async for chunk in _stream_offline_followup(message, last_recommendation):
            yield chunk


async def _stream_offline_followup(
    message: str, last_recommendation: dict[str, Any]
) -> AsyncIterator[str]:
    from groq_agent import CSAAdvisor

    advisor = CSAAdvisor()
    advisor._last = last_recommendation
    reply = advisor._offline(message)
    reply = strip_leaked_tool_markup(reply or "") or evidence_summary(last_recommendation)
    async for chunk in _stream_text(reply):
        yield chunk


async def _narrative_for_recommendation(
    message: str,
    history: list[dict[str, str]],
    recommendation: dict[str, Any],
    settings,
) -> str:
    """Phrase the default answer from scored evidence; never free-invent practices."""
    fallback = evidence_summary(recommendation)
    if not settings.openai_api_key:
        return fallback
    try:
        client = make_client(settings.openai_api_key, settings.openai_timeout_seconds)
    except Exception:
        return fallback

    system_instruction = (
        SYSTEM_PROMPT
        + "\n\nCRITICAL: A recommendation was ALREADY computed by the server. "
        "Phrase the DEFAULT clean answer using ONLY this JSON. "
        "Do not call tools. Do not invent practices, percentages, or coordinates.\n"
        + json.dumps(recommendation, default=str)
    )
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
) -> dict[str, Any]:
    """Non-streaming turn — aggregates the SSE stream into a single JSON payload."""
    reply = ""
    recommendation: dict[str, Any] | None = None
    slots: dict[str, Any] | None = None
    error: str | None = None
    async for chunk in stream_chat(message, history, last_recommendation, top_n):
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
        elif t == "error":
            error = payload.get("message")
    return {
        "reply": reply,
        "recommendation": recommendation,
        "slots": slots,
        "error": error,
    }


def _error_message(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "outside ethiopia" in low or "outside" in low and "ethiopia" in low:
        return msg
    if "not supported" in low or "objective" in low:
        return msg
    if "429" in low or "rate limit" in low or "resource exhausted" in low:
        return (
            "The AI text service has reached its usage limit for now. Please wait a "
            "few minutes and try again, or use the form for instant recommendations."
        )
    return (
        "I couldn't score practices for that request. Check the location is in "
        "Ethiopia and that the challenge/objective pair is supported, then try again."
    )
