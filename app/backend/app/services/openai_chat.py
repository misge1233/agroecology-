"""OpenAI chat completions adapter for the advisor chat (manual function calling)."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from advisor_agent import TOOLS, run_tool

logger = logging.getLogger(__name__)

# OpenAI: set OPENAI_API_KEY in backend/.env only; model/URL fixed here for the allow-list.
OPENAI_CHAT_MODEL = "gpt-4o-mini"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


def make_client(api_key: str, timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout_seconds,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )


def build_messages(
    history: list[dict[str, str]],
    message: str,
    system_instruction: str,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_instruction},
    ]
    for h in history:
        role = h.get("role")
        text = (h.get("content") or "").strip()
        if not text:
            continue
        if role == "user":
            messages.append({"role": "user", "content": text})
        elif role == "assistant":
            messages.append({"role": "assistant", "content": text})
    messages.append({"role": "user", "content": message})
    return messages


def _parse_tool_args(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        logger.warning("Could not parse tool arguments: %s", raw[:200])
        return {}


async def generate_turn(
    client: httpx.AsyncClient,
    *,
    model: str,
    messages: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    str | None,
    list[tuple[str, str, dict[str, Any]]],
]:
    """One OpenAI round. Returns updated messages, assistant text, tool calls (id, name, args)."""
    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.3,
    }
    response = await client.post(OPENAI_CHAT_COMPLETIONS_URL, json=payload)
    response.raise_for_status()
    body = response.json()
    choice = body["choices"][0]["message"]
    messages = [*messages, choice]

    tool_calls = choice.get("tool_calls") or []
    if tool_calls:
        parsed: list[tuple[str, str, dict[str, Any]]] = []
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            args = _parse_tool_args(fn.get("arguments"))
            parsed.append((tc.get("id") or "", name, args))
        return messages, None, parsed

    text = (choice.get("content") or "").strip() or None
    return messages, text, []


async def append_tool_results(
    messages: list[dict[str, Any]],
    function_calls: list[tuple[str, str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Execute tools and append tool role messages; return successful recommend payloads."""
    recommendations: list[dict[str, Any]] = []
    for tool_call_id, name, args in function_calls:
        try:
            result = run_tool(name, args)
        except Exception as exc:
            result = {"error": str(exc)}
        if isinstance(result, dict) and "error" not in result and "recommendations" in result:
            recommendations.append(result)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(result, default=str),
            }
        )
    return recommendations, messages
