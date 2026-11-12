"""The fixed prompt of Methodology 2, its version and the output schema (E6 Part 3).

Prompt text and its version live only here; :func:`prompt_hash` of the system message,
the user template and the schema goes into every run's ``config.json``. The user message
holds the context in words and numbers, the objective and its direction, the crop, the
candidate ids with names, then the cards grouped by candidate, then passages and graph
facts when the variant includes them.

The model returns JSON (``ranking`` and ``items``); :func:`validate` checks that the
ranking is a permutation of the candidates, that every item is a candidate, and that
every cited card id was in the prompt. Numbers in ``reason`` are never read by code.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

PROMPT_VERSION = "m2-p1"
EFFECT_CLASSES = ("large_benefit", "benefit", "neutral", "harm", "unknown")
REASON_WORDS = 30

SYSTEM = """You are an agronomist ranking agricultural practices for one specific farm context in Ethiopia.

You receive the farm context, one objective (an outcome and whether higher or lower is better), the crop, the candidate practices with their ids, and, depending on the request, evidence cards from field studies, passages from studies and guidelines, and facts from a knowledge graph.

Each evidence card is one study's pooled comparison of a practice against its comparator at one site: the effect is oriented so that + means better for the objective; it shows the number of rows, a precision class, the site context and the source. Cards marked RELATED PRACTICE describe a different practice that shares a main component with the candidate.

Rules:
1. Rank every candidate id exactly once, best first for the stated objective in this context.
2. Judge from the cards, passages and facts given. Prefer evidence from sites similar to this context and with higher precision and more rows. Use general agronomic knowledge only where no evidence is given.
3. For each candidate give an effect class: large_benefit, benefit, neutral, harm, or unknown. Say unknown rather than guess when you have no basis for a judgement.
4. Cite the ids of the cards that support each judgement in card_ids. Never invent card ids; cite only ids shown in this request. Cite no card when none applies.
5. confidence is your confidence in the effect class, from 0 to 1.
6. reason: at most 30 words, plain language, and no numbers of any kind.
Return only the JSON object requested."""


def response_schema(candidates: list[str]) -> dict[str, Any]:
    """Strict JSON schema of the answer (candidate ids as an enum; card ids free text so that
    invented ids stay measurable)."""
    return {
        "name": "practice_ranking",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["ranking", "items"],
            "properties": {
                "ranking": {"type": "array", "items": {"type": "string", "enum": list(candidates)}},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "effect_class", "confidence", "card_ids", "reason"],
                        "properties": {
                            "id": {"type": "string", "enum": list(candidates)},
                            "effect_class": {"type": "string", "enum": list(EFFECT_CLASSES)},
                            "confidence": {"type": "number"},
                            "card_ids": {"type": "array", "items": {"type": "string"}},
                            "reason": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def prompt_hash() -> str:
    """Identity of the prompt: version, system message, the user template below and the schema shape."""
    blob = json.dumps({"version": PROMPT_VERSION, "system": SYSTEM, "template": user_message.__doc__,
                       "schema": response_schema(["<id>"])}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def user_message(context_text: str, objective: str, better: str, crop: str | None,
                 candidates: list[tuple[str, str]], cards: Mapping[str, list[str]] | None = None,
                 passages: list[dict[str, Any]] | None = None, facts: Mapping[str, str] | None = None) -> str:
    """FARM CONTEXT / OBJECTIVE / CROP / CANDIDATES / EVIDENCE CARDS (by candidate) /
    PASSAGES / GRAPH FACTS / TASK, in that order; sections absent from a variant are omitted."""
    L = [f"FARM CONTEXT: {context_text}", f"OBJECTIVE: {objective} ({better})", f"CROP: {crop or 'not specified'}", "",
         "CANDIDATES:"]
    L += [f"- {cid}: {name}" for cid, name in candidates]
    if cards is not None:
        L += ["", "EVIDENCE CARDS (grouped by candidate):"]
        for cid, _ in candidates:
            block = cards.get(cid) or []
            L.append(f"{cid}:")
            L += [f"  {t}" for t in block] if block else ["  (no cards)"]
    if passages:
        L += ["", "PASSAGES:"]
        L += [f"[{p['chunk_id']}] ({p['tier']}; {p['citation']}) for {p['candidate']}: {p['text']}" for p in passages]
    if facts is not None:
        L += ["", "GRAPH FACTS:"]
        L += [f"- {cid}: {facts.get(cid) or 'no facts'}" for cid, _ in candidates]
    L += ["", "TASK: rank all candidates for the objective in this context and answer in the JSON format."]
    return "\n".join(L)


def messages(user: str, error: str | None = None, previous: str | None = None) -> list[dict[str, str]]:
    """The chat messages; a retry appends the previous answer and the validation error."""
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    if error is not None:
        msgs += [{"role": "assistant", "content": previous or ""},
                 {"role": "user", "content": f"Your answer was invalid: {error}. Answer again, following every rule."}]
    return msgs


# ----------------------------------------------------------------- validation
class InvalidAnswer(ValueError):
    pass


def validate(answer: Any, candidates: list[str], prompt_card_ids: set[str]) -> dict[str, Any]:
    """The parsed answer when valid, else :class:`InvalidAnswer` with the reason.

    Invented card ids are a validation error (the model is told to cite only shown ids); the
    retry carries that error. The count of invented ids before validation is kept by the engine.
    """
    if not isinstance(answer, dict):
        raise InvalidAnswer("the answer is not a JSON object")
    ranking = answer.get("ranking")
    if not isinstance(ranking, list) or sorted(map(str, ranking)) != sorted(candidates) or len(set(ranking)) != len(candidates):
        raise InvalidAnswer(f"ranking must list every candidate exactly once: {', '.join(candidates)}")
    items = answer.get("items")
    if not isinstance(items, list):
        raise InvalidAnswer("items must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for it in items:
        if not isinstance(it, dict) or it.get("id") not in candidates:
            raise InvalidAnswer("every item id must be a candidate id")
        if it["id"] in by_id:
            raise InvalidAnswer(f"candidate {it['id']} has more than one item")
        if it.get("effect_class") not in EFFECT_CLASSES:
            raise InvalidAnswer(f"effect_class must be one of {', '.join(EFFECT_CLASSES)}")
        bad = [c for c in it.get("card_ids") or [] if c not in prompt_card_ids]
        if bad:
            raise InvalidAnswer(f"card ids not in the request: {', '.join(map(str, bad))}")
        by_id[it["id"]] = it
    missing = [c for c in candidates if c not in by_id]
    if missing:
        raise InvalidAnswer(f"items missing for: {', '.join(missing)}")
    return {"ranking": [str(r) for r in ranking], "items": by_id}
