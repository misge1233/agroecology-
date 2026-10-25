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

Tier-1 EVIDENCE BASE (P6b-i): when the knowledge graph has been built
(``rag/graph/store/graph.json``), each recommended practice also carries a
count-and-provenance summary of the dataset rows behind it — how many
studies and field observations, in which AEZ belts and crop groups, and how
many of those studies are retrievable in the corpus. **Effect magnitudes
from the graph (``mean_log_rr``, ``median_log_rr``) are deliberately never
read**: the model owns every number, and a dataset aggregate can contradict
the model's prediction for this particular pin (CLAUDE.md doctrine 1, P6a
review). The graph is optional — absent store, absent networkx or a load
failure logs once and /explain behaves exactly as before.

The retrievers are injectable (``set_retriever`` / ``set_guidance_retriever``
or the ``retriever=`` / ``guidance_retriever=`` arguments of :func:`explain`)
so tests run without chromadb, the index, or the network. The graph query is
injectable the same way (``set_graph_query``).
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
    "- An EVIDENCE BASE block, when present, states how many studies and "
    "field observations stand behind each practice and where they were "
    "measured. Those are counts and provenance, NOT effect sizes: you may "
    "quote them to say how well-evidenced a practice is, but never present "
    "them as a magnitude of benefit.\n"
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


# --------------------------------------------------------------- graph layer
_graph_query: Any = None             # cache; injectable for tests
_graph_unavailable = False           # sticky "not built" flag


def set_graph_query(graph_query: Any) -> None:
    """Inject a GraphQuery (tests) or reset the cache (pass ``None``)."""
    global _graph_query, _graph_unavailable
    _graph_query = graph_query
    _graph_unavailable = False


def graph_is_ready() -> bool:
    """True when the knowledge-graph store exists on disk.

    Cheap filesystem check, mirroring :func:`is_ready` — no networkx import,
    no graph load.
    """
    return _graph_store_path().is_file()


def _graph_store_path():
    """``rag/graph/store/graph.json`` under the repo root."""
    return (
        get_settings().backend_root.parents[1]
        / "rag" / "graph" / "store" / "graph.json"
    )


def get_graph_query() -> Any:
    """Lazily load the knowledge graph, or ``None`` when it is unavailable.

    Graceful no-op by design (CLAUDE.md doctrine 5): a missing store, a
    missing networkx or a corrupt file logs once and disables the layer for
    the process — /explain then behaves exactly as it did before P6b-i.
    Never raises.
    """
    global _graph_query, _graph_unavailable
    if _graph_query is not None:
        return _graph_query
    if _graph_unavailable:
        return None
    store = _graph_store_path()
    if not store.is_file():
        _graph_unavailable = True
        logger.info("Knowledge graph not built (%s) — evidence base disabled.", store)
        return None
    try:
        _ensure_repo_root_on_path()
        from rag.graph.query import GraphQuery  # networkx — deferred

        _graph_query = GraphQuery.load(store)
        logger.info("Knowledge graph ready (%s).", store)
    except Exception as exc:  # optional layer — degrade, never fail
        _graph_unavailable = True
        logger.warning("Knowledge graph unavailable (%s) — evidence base disabled.", exc)
        return None
    return _graph_query


#: Corpus-coverage buckets always present in an evidence-base summary.
CORPUS_STATUSES = ("full_text", "abstract", "none")


def build_evidence_base(
    recommendation: dict[str, Any], graph_query: Any = None
) -> dict[str, dict[str, Any]]:
    """Counts and provenance per recommended practice, from the graph.

    Returns ``{practice: {n_studies, n_obs, aez_belts, crop_groups,
    corpus_status: {full_text, abstract, none}, studies: [...]}}`` — and
    **nothing else**. The graph's ``mean_log_rr`` / ``median_log_rr`` fields
    are not copied: the model owns effect magnitudes, so a dataset aggregate
    must never reach the prompt or the UI where it could contradict the
    prediction for this pin.

    Returns ``{}`` when the graph is unavailable or the indicator is missing.
    """
    gq = graph_query if graph_query is not None else get_graph_query()
    if gq is None:
        return {}
    indicator = (recommendation.get("query") or {}).get("indicator")
    if not indicator:
        return {}

    out: dict[str, dict[str, Any]] = {}
    for rec in recommendation.get("recommendations") or []:
        practice = rec.get("practice")
        if not practice or practice in out:
            continue
        try:
            summary = gq.evidence_summary(practice, indicator)
        except Exception as exc:  # one bad practice must not sink the response
            logger.warning("Evidence summary failed for %r (%s).", practice, exc)
            continue
        if not summary.get("found"):
            continue
        counts = summary.get("corpus_status") or {}
        out[practice] = {
            "n_studies": int(summary.get("n_studies") or 0),
            "n_obs": int(summary.get("n_obs") or 0),
            "aez_belts": list(summary.get("aez_belts") or []),
            "crop_groups": list(summary.get("crop_groups") or []),
            "corpus_status": {k: int(counts.get(k, 0)) for k in CORPUS_STATUSES},
            "studies": [
                {
                    "era_code": st.get("era_code"),
                    "title": st.get("title"),
                    "year": _safe_int(st.get("year")),
                    "doi": st.get("doi"),
                    "corpus_status": st.get("corpus_status"),
                }
                for st in (summary.get("studies") or [])
            ],
        }
    return out


def n_studies_in_corpus(entry: dict[str, Any]) -> int:
    """Studies behind a practice that contribute at least one corpus chunk."""
    counts = entry.get("corpus_status") or {}
    return int(counts.get("full_text", 0)) + int(counts.get("abstract", 0))


def evidence_base_sentence(practice: str, entry: dict[str, Any]) -> str:
    """One human sentence of counts and provenance — no effect magnitudes."""
    parts = [
        f"{practice}: backed by {entry['n_studies']} "
        f"{'study' if entry['n_studies'] == 1 else 'studies'} / "
        f"{entry['n_obs']} field "
        f"{'observation' if entry['n_obs'] == 1 else 'observations'}"
    ]
    if entry.get("aez_belts"):
        parts.append(f" in {', '.join(entry['aez_belts'])}")
    in_corpus = n_studies_in_corpus(entry)
    parts.append(
        f"; {in_corpus} of the studies "
        f"{'is' if in_corpus == 1 else 'are'} in the retrievable corpus"
    )
    return "".join(parts) + "."


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
    recommendation: dict[str, Any],
    chunks: list[dict[str, Any]],
    evidence_base: dict[str, dict[str, Any]] | None = None,
) -> set[float]:
    """Every number the LLM is allowed to state.

    Sources: the recommendation JSON (query/recommendations/details, all
    levels, rounded forms included) and each cited chunk's text plus its
    provenance metadata (title/year/era_code — e.g. '(Abera et al., 2019)').
    Callers pass evidence AND guidance chunks together — the numeric rule
    applies identically to both tiers. ``url`` is deliberately NOT harvested:
    URLs never appear in the prompt, so their digits (handle ids, dates)
    would whitelist numbers the LLM cannot legitimately be quoting.

    ``evidence_base`` EXTENDS the whitelist with exactly the three numbers
    the EVIDENCE BASE prompt sentence states per practice — ``n_studies``,
    ``n_obs`` and the number of studies in the corpus — and nothing else.
    Study titles/years, era codes and the per-bucket ``corpus_status``
    counts are NOT harvested: they never appear in the prompt (the UI shows
    them, the LLM does not see them), so admitting their digits would
    whitelist numbers the LLM cannot legitimately be quoting — the same
    rule that keeps URL digits out. The evidence base holds no effect
    magnitudes, so nothing it adds can whitelist an invented effect.
    """
    allowed: set[float] = set()
    _collect_numbers(recommendation, allowed)
    for c in chunks:
        for field in ("text", "title", "year", "era_code"):
            _collect_numbers(c.get(field), allowed)
    for entry in (evidence_base or {}).values():
        _collect_numbers(entry.get("n_studies"), allowed)
        _collect_numbers(entry.get("n_obs"), allowed)
        _collect_numbers(n_studies_in_corpus(entry), allowed)
    return allowed


def numbers_are_grounded(
    text: str,
    recommendation: dict[str, Any],
    chunks: list[dict[str, Any]],
    evidence_base: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """True iff every numeric token in ``text`` is grounded.

    A token passes if it (or a rounded form) appears in the recommendation
    JSON or a cited chunk, or is a trivially small integer 0–10 (list
    positions, "the 2 top practices", …). Citation markers [n] are stripped
    first. Any other number means the LLM invented a quantity — reject.
    """
    allowed = allowed_numbers(recommendation, chunks, evidence_base)
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
    recommendation: dict[str, Any],
    chunks: list[dict[str, Any]],
    evidence_base: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Deterministic, citation-grounded explanation — no generated content.

    One sentence per recommended practice: the engine's own effect string plus
    up to two retrieved sources (title + era_code). Used when the LLM is
    unavailable or its output fails the numeric guardrail.

    When an ``evidence_base`` entry exists for a practice, its counts-and-
    provenance sentence is appended — the same sentence the LLM prompt gets,
    so both paths state the same facts.
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
        entry = (evidence_base or {}).get(practice)
        if entry:
            sentences.append(evidence_base_sentence(practice, entry))
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
    evidence_base: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    passages = []
    for i, c in enumerate(chunks, start=1):
        header = f"[{i}] ({c.get('era_code')}) {c.get('title')} ({c.get('year')})"
        passages.append(f"{header}\n{(c.get('text') or '').strip()}")
    user = (
        "RECOMMENDATION JSON (authoritative — the only source of effect "
        "numbers):\n```json\n"
        + json.dumps(recommendation, indent=2, default=str)
        + "\n```\n"
    )
    if evidence_base:
        # Counts and provenance only — deliberately no effect magnitudes.
        lines = "\n".join(
            evidence_base_sentence(practice, entry)
            for practice, entry in evidence_base.items()
        )
        user += (
            "\nEVIDENCE BASE (how much field evidence stands behind each "
            "practice — counts and provenance only; these are NOT effect "
            "sizes and must not be described as such):\n"
            + lines
            + "\n"
        )
    user += (
        "\nEVIDENCE PASSAGES (cite as [n]):\n\n"
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
    graph_query: Any = None,
) -> dict[str, Any]:
    """Produce a grounded explanation of an engine recommendation.

    Returns ``{"explanation", "citations", "grounded", "llm_used",
    "evidence_base"}``. ``evidence_base`` is ``{}`` whenever the knowledge
    graph is not built — the field is always present, never null.
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
    evidence_base = build_evidence_base(recommendation, graph_query)

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
            "evidence_base": evidence_base,
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
            _build_messages(
                recommendation, question, chunks, guidance_chunks, evidence_base
            )
        )
        if text and numbers_are_grounded(
            text, recommendation, chunks + guidance_chunks, evidence_base
        ):
            return {
                "explanation": text,
                "citations": citations + shape_citations(guidance_chunks),
                "grounded": True,
                "llm_used": True,
                "evidence_base": evidence_base,
            }
        if text:
            logger.warning(
                "LLM explanation rejected by numeric guardrail — "
                "returning deterministic fallback."
            )

    # No key, LLM failure, or guardrail rejection → deterministic template
    # (evidence-only: the template cites studies, never guidance).
    return {
        "explanation": build_fallback_text(recommendation, chunks, evidence_base),
        "citations": citations,
        "grounded": True,
        "llm_used": False,
        "evidence_base": evidence_base,
    }
