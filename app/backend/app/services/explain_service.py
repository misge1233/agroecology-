"""Grounded explanation service — the RAG layer behind POST /explain.

Doctrine (docs/decisions/rag_design.md):
- The ML model owns every number. This layer explains a recommendation the
  engine already produced; it never invents or alters effect sizes.
- Cite or stay silent: LLM output must be grounded in retrieved ERA chunks and
  pass a numeric guardrail; otherwise we fall back to a deterministic template
  built from the retrieved citations (no free-form agronomy).
- Wrap, never fork: retrieval is ``rag.retrieve.RagRetriever`` (repo root),
  imported lazily by putting the repo root on ``sys.path`` — the same pattern
  ``recommender_service`` uses for the canonical engine.

Two tiers, never mixed (P5a): Tier-1 ``era_corpus`` evidence passages carry
the effect numbers and citations [n]; Tier-2 ``guidance_corpus`` passages
(GARDIAN implementation guidance) may inform HOW-to advice only, cited as
[Gn]. The numeric guardrail applies identically to both tiers. Guidance is
optional — if its collection is not built, /explain works exactly as before.

The retrievers are injectable (``set_retriever`` / ``set_guidance_retriever``
or the ``retriever=`` / ``guidance_retriever=`` arguments of :func:`explain`)
so tests run without chromadb, the index, or the network.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# Same provider/model family as the chat adapter (app/services/openai_chat.py);
# no tools are exposed here — /explain is generation over fixed evidence only.
EXPLAIN_MODEL = "gpt-4o-mini"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
EXPLAIN_TEMPERATURE = 0.2

SNIPPET_CHARS = 240  # citation snippet length (~240 chars of chunk text)
GUIDANCE_K = 4       # Tier-2 guidance passages retrieved per explanation

# Numeric tokens: integers and decimals ("12", "8.38", the "3" in "3-small").
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
# Inline citation markers like [1], [12], and guidance markers [G1], [G3] —
# stripped before the numeric check so reference indices are never mistaken
# for invented quantities.
_CITE_MARKER_RE = re.compile(r"\[G?\d+\]")

EXPLAIN_SYSTEM_PROMPT = (
    "You are the evidence-explanation layer of AgroAdvisor-ET, an advisor for "
    "climate-smart agriculture in Ethiopia. You are given (1) a recommendation "
    "JSON produced by a machine-learning model trained on ERA meta-analysis "
    "field evidence, and (2) numbered evidence passages retrieved from the "
    "source studies behind that training data.\n"
    "Your job: explain WHY the ranked practices fit this specific context "
    "(agro-ecology, rainfall, slope, crop) and HOW to apply them in practice.\n"
    "Strict rules:\n"
    "- Ground every claim in the numbered passages and cite them inline as "
    "[n] (e.g. [1], [3]). If the passages do not support a claim, omit the "
    "claim entirely — do not fill gaps from general knowledge.\n"
    "- Use ONLY numbers that appear in the recommendation JSON or are quoted "
    "verbatim from a cited passage. Never invent, alter, or recompute effect "
    "sizes, percentages, or study counts.\n"
    "- The model's ranking and effect estimates are authoritative; you explain "
    "them, you do not second-guess them.\n"
    "- If GUIDANCE passages (numbered [G1], [G2], ...) are provided, they may "
    "inform HOW to implement a practice (steps, timing, costs, failure "
    "modes) ONLY — cite them inline as [Gn]. They are never evidence for "
    "effect sizes or rankings, and any number quoted from a guidance passage "
    "must appear verbatim in it and be cited [Gn].\n"
    "- Be concise and practical (short paragraphs or bullets, plain language "
    "for extension workers)."
)


# ------------------------------------------------------------------ retriever
_retriever: Any = None  # module-level cache; injectable for tests
_guidance_retriever: Any = None      # Tier-2 cache; injectable for tests
_guidance_unavailable = False        # sticky "not built" flag (reset via setter)


def _ensure_repo_root_on_path() -> None:
    """Make ``rag.retrieve`` importable (repo root = backend_root.parents[1])."""
    repo_root = get_settings().backend_root.parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def set_retriever(retriever: Any) -> None:
    """Inject a retriever (tests) or reset the cached one (pass ``None``)."""
    global _retriever
    _retriever = retriever


def set_guidance_retriever(retriever: Any) -> None:
    """Inject a Tier-2 retriever (tests) or reset the cache (pass ``None``)."""
    global _guidance_retriever, _guidance_unavailable
    _guidance_retriever = retriever
    _guidance_unavailable = False


def get_retriever() -> Any:
    """Lazily build the real RagRetriever over the repo's Chroma index."""
    global _retriever
    if _retriever is None:
        _ensure_repo_root_on_path()
        from rag.retrieve import RagRetriever  # heavy (chromadb) — deferred

        settings = get_settings()
        _retriever = RagRetriever(
            index_dir=settings.resolved_rag_index_dir,
            chunks_path=settings.resolved_rag_chunks_path,
            api_key=settings.openai_api_key or None,
        )
        logger.info(
            "RagRetriever ready (index=%s, chunks=%s).",
            settings.resolved_rag_index_dir,
            settings.resolved_rag_chunks_path,
        )
    return _retriever


def get_guidance_retriever() -> Any:
    """Tier-2 guidance retriever, or ``None`` when the corpus is not built.

    Graceful no-op by design: a missing guidance chunks file or collection
    logs once and disables the tier for the process — /explain then behaves
    exactly as it did before P5a. Never raises.
    """
    global _guidance_retriever, _guidance_unavailable
    if _guidance_retriever is not None:
        return _guidance_retriever
    if _guidance_unavailable:
        return None
    settings = get_settings()
    chunks_path = settings.resolved_rag_guidance_chunks_path
    if not chunks_path.is_file():
        _guidance_unavailable = True
        logger.info(
            "Guidance corpus not built (%s missing) — Tier-2 disabled.",
            chunks_path,
        )
        return None
    try:
        _ensure_repo_root_on_path()
        from rag.retrieve import GUIDANCE_COLLECTION, RagRetriever

        _guidance_retriever = RagRetriever(
            index_dir=settings.resolved_rag_index_dir,
            chunks_path=chunks_path,
            api_key=settings.openai_api_key or None,
            collection=GUIDANCE_COLLECTION,
        )
        logger.info("Guidance retriever ready (chunks=%s).", chunks_path)
    except Exception as exc:
        _guidance_unavailable = True
        logger.warning("Guidance retriever unavailable (%s) — Tier-2 disabled.", exc)
        return None
    return _guidance_retriever


def is_ready() -> bool:
    """Cheap filesystem check — no chromadb import, no index open.

    Requires the Chroma persistence file, not just the directory — a partial
    ``build_index.py`` run can leave an empty dir behind.
    """
    settings = get_settings()
    index_dir = settings.resolved_rag_index_dir
    return (
        index_dir.is_dir()
        and (index_dir / "chroma.sqlite3").is_file()
        and settings.resolved_rag_chunks_path.is_file()
    )


# ------------------------------------------------------------------ citations
def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def shape_citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One citation per study (era_code), deduped across retrieved chunks.

    Retrieval returns chunks, several of which may come from the same study;
    the citation list is per-study provenance for the UI. The first chunk of
    a study (highest fused rank) supplies the snippet and practice;
    ``n_passages`` counts how many retrieved passages that study contributed.
    """
    citations: list[dict[str, Any]] = []
    by_study: dict[Any, dict[str, Any]] = {}
    for i, c in enumerate(chunks):
        # era_code is the join key; guidance chunks (era_code=None) dedupe per
        # document via url/doi/title instead; never collapse two unknowns.
        key = (c.get("era_code") or c.get("url") or c.get("doi")
               or c.get("title") or f"chunk-{i}")
        if key in by_study:
            by_study[key]["n_passages"] += 1
            continue
        text = (c.get("text") or "").strip()
        citation = {
            "era_code": c.get("era_code"),
            "tier": c.get("tier") or "evidence",
            "doi": c.get("doi"),
            "url": c.get("url"),
            "title": c.get("title"),
            "year": _safe_int(c.get("year")),
            "journal": c.get("journal"),
            "practice": c.get("for_practice"),
            "snippet": text[:SNIPPET_CHARS],
            "n_passages": 1,
        }
        by_study[key] = citation
        citations.append(citation)
    return citations


# ------------------------------------------------------------------ guardrail
def _number_variants(value: float) -> set[float]:
    """A number plus its rounded forms, so '12' matches 12.3 from the JSON."""
    v = float(value)
    return {v, abs(v), round(v), round(v, 1), round(v, 2), round(abs(v))}


def _collect_numbers(obj: Any, out: set[float]) -> None:
    """Recursively harvest every numeric value / numeric substring in ``obj``."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.update(_number_variants(obj))
    elif isinstance(obj, str):
        for tok in _NUM_RE.findall(obj):
            out.update(_number_variants(float(tok)))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _collect_numbers(k, out)
            _collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out)


def allowed_numbers(
    recommendation: dict[str, Any], chunks: list[dict[str, Any]]
) -> set[float]:
    """Every number the LLM is allowed to state.

    Sources: the recommendation JSON (query/recommendations/details, all
    levels, rounded forms included) and each cited chunk's text plus its
    provenance metadata (title/year/era_code — e.g. '(Abera et al., 2019)').
    Callers pass evidence AND guidance chunks together — the numeric rule
    applies identically to both tiers. ``url`` is deliberately NOT harvested:
    URLs never appear in the prompt, so their digits (handle ids, dates)
    would whitelist numbers the LLM cannot legitimately be quoting.
    """
    allowed: set[float] = set()
    _collect_numbers(recommendation, allowed)
    for c in chunks:
        for field in ("text", "title", "year", "era_code"):
            _collect_numbers(c.get(field), allowed)
    return allowed


def numbers_are_grounded(
    text: str, recommendation: dict[str, Any], chunks: list[dict[str, Any]]
) -> bool:
    """True iff every numeric token in ``text`` is grounded.

    A token passes if it (or a rounded form) appears in the recommendation
    JSON or a cited chunk, or is a trivially small integer 0–10 (list
    positions, "the 2 top practices", …). Citation markers [n] are stripped
    first. Any other number means the LLM invented a quantity — reject.
    """
    allowed = allowed_numbers(recommendation, chunks)
    stripped = _CITE_MARKER_RE.sub(" ", text)
    for tok in _NUM_RE.findall(stripped):
        value = float(tok)
        if value.is_integer() and 0 <= value <= 10:
            continue
        if not _number_variants(value) & allowed:
            logger.warning("Numeric guardrail tripped on ungrounded token %r.", tok)
            return False
    return True


# ------------------------------------------------------------------- fallback
def build_fallback_text(
    recommendation: dict[str, Any], chunks: list[dict[str, Any]]
) -> str:
    """Deterministic, citation-grounded explanation — no generated content.

    One sentence per recommended practice: the engine's own effect string plus
    up to two retrieved sources (title + era_code). Used when the LLM is
    unavailable or its output fails the numeric guardrail.
    """
    query = recommendation.get("query") or {}
    indicator = query.get("indicator") or "the selected objective"
    sentences: list[str] = []
    for rec in recommendation.get("recommendations") or []:
        practice = rec.get("practice") or "This practice"
        effect = rec.get("effect") or ""
        # Prefer chunks retrieved for this practice; fall back to the pool.
        matched = [c for c in chunks if c.get("for_practice") == practice] or chunks
        seen_studies: set[Any] = set()
        cited: list[dict[str, Any]] = []
        for c in matched:  # one mention per study, not per chunk
            key = c.get("era_code") or c.get("doi") or c.get("title")
            if key in seen_studies:
                continue
            seen_studies.add(key)
            cited.append(c)
        cites = ", ".join(
            f"“{(c.get('title') or 'Untitled study')}” ({c.get('era_code')})"
            for c in cited[:2]
        )
        sentence = f"{practice}: the model estimates {effect}".rstrip()
        if cites:
            sentence += f", supported by evidence from {cites}"
        sentences.append(sentence + ".")
    if not sentences:
        sentences.append(
            f"No practices were recommended for {indicator} in this context."
        )
    return " ".join(sentences)


# ------------------------------------------------------------------ LLM path
def _build_messages(
    recommendation: dict[str, Any],
    question: str | None,
    chunks: list[dict[str, Any]],
    guidance_chunks: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    passages = []
    for i, c in enumerate(chunks, start=1):
        header = f"[{i}] ({c.get('era_code')}) {c.get('title')} ({c.get('year')})"
        passages.append(f"{header}\n{(c.get('text') or '').strip()}")
    user = (
        "RECOMMENDATION JSON (authoritative — the only source of effect "
        "numbers):\n```json\n"
        + json.dumps(recommendation, indent=2, default=str)
        + "\n```\n\nEVIDENCE PASSAGES (cite as [n]):\n\n"
        + "\n\n".join(passages)
    )
    if guidance_chunks:
        guidance_passages = []
        for i, c in enumerate(guidance_chunks, start=1):
            header = f"[G{i}] {c.get('title')} ({c.get('year')})"
            guidance_passages.append(f"{header}\n{(c.get('text') or '').strip()}")
        user += (
            "\n\nGUIDANCE PASSAGES (cite as [G1], [G2], ...) — practical "
            "implementation guidance only. Use them for HOW-to advice "
            "(steps, timing, costs, failure modes), never as evidence for "
            "effect sizes or rankings; any number you quote from them must "
            "be cited [Gn]:\n\n"
            + "\n\n".join(guidance_passages)
        )
    if question:
        user += (
            "\n\nUSER QUESTION (answer it, grounded in the same passages and "
            f"JSON): {question}"
        )
    else:
        user += (
            "\n\nExplain why these practices are recommended for this "
            "location and how to apply them."
        )
    return [
        {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _call_llm(messages: list[dict[str, str]]) -> str | None:
    """One OpenAI chat completion (no tools). Returns None on any failure."""
    settings = get_settings()
    try:
        response = httpx.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            json={
                "model": EXPLAIN_MODEL,
                "messages": messages,
                "temperature": EXPLAIN_TEMPERATURE,
            },
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            timeout=settings.openai_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        return (body["choices"][0]["message"].get("content") or "").strip() or None
    except Exception as exc:  # network / auth / shape — degrade, don't 500
        logger.warning("Explain LLM call failed (%s) — using fallback.", exc)
        return None


# ------------------------------------------------------------------- explain
def explain(
    recommendation: dict[str, Any],
    question: str | None = None,
    k: int = 8,
    retriever: Any = None,
    guidance_retriever: Any = None,
) -> dict[str, Any]:
    """Produce a grounded explanation of an engine recommendation.

    Returns ``{"explanation", "citations", "grounded", "llm_used"}``.
    ``grounded`` is True only when at least one evidence chunk backs the text;
    ``llm_used`` is True only when LLM output passed the numeric guardrail.

    Two tiers: evidence retrieval (k chunks from ``era_corpus``) is unchanged;
    guidance retrieval (GUIDANCE_K chunks from ``guidance_corpus``) is an
    optional layer for HOW-to advice — absent corpus or retrieval failure
    degrades to evidence-only, never an error. Guidance citations are only
    returned on the LLM path (the deterministic fallback never cites [Gn]).
    """
    r = retriever if retriever is not None else get_retriever()
    chunks = r.retrieve_for_recommendation(recommendation, k=k)
    citations = shape_citations(chunks)

    if not chunks:
        # Cite or stay silent — with nothing retrieved we make no claims.
        return {
            "explanation": (
                "No evidence passages were retrieved for this recommendation, "
                "so no grounded explanation can be generated. The model's "
                "ranked practices and effect estimates above still stand."
            ),
            "citations": [],
            "grounded": False,
            "llm_used": False,
        }

    if get_settings().openai_api_key:
        # Guidance only feeds the LLM prompt (the deterministic fallback
        # never cites [Gn]), so it is retrieved only on this path.
        g = (guidance_retriever if guidance_retriever is not None
             else get_guidance_retriever())
        guidance_chunks: list[dict[str, Any]] = []
        if g is not None:
            try:
                guidance_chunks = g.retrieve_for_recommendation(
                    recommendation, k=GUIDANCE_K
                )
            except Exception as exc:  # guidance is optional — degrade, don't fail
                logger.warning("Guidance retrieval failed (%s) — evidence only.", exc)
                guidance_chunks = []
        text = _call_llm(
            _build_messages(recommendation, question, chunks, guidance_chunks)
        )
        if text and numbers_are_grounded(
            text, recommendation, chunks + guidance_chunks
        ):
            return {
                "explanation": text,
                "citations": citations + shape_citations(guidance_chunks),
                "grounded": True,
                "llm_used": True,
            }
        if text:
            logger.warning(
                "LLM explanation rejected by numeric guardrail — "
                "returning deterministic fallback."
            )

    # No key, LLM failure, or guardrail rejection → deterministic template
    # (evidence-only: the template cites studies, never guidance).
    return {
        "explanation": build_fallback_text(recommendation, chunks),
        "citations": citations,
        "grounded": True,
        "llm_used": False,
    }
