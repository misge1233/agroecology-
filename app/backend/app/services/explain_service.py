"""Grounded explanation service — the RAG layer behind POST /explain.

Doctrine (docs/decisions/rag_design.md):
- Every number has a source (evidence fusion, docs/decisions/evidence_fusion.md):
  the model's estimate, a study-level effect computed from the dataset, a figure
  stated in a cited passage (same sentence), the context layers or a count. This
  layer explains; the LLM never invents or alters a number (guard v2).
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
many of those studies are retrievable in the corpus. Since U9 the
study-level effects (``mean_log_rr`` per study) are used, but only through
``fusion_service``: they enter the prompt as labelled, cited values of the
fused bundle and never as an unlabelled aggregate beside the model's
estimate (CLAUDE.md doctrine 1 as amended 1 Nov 2026). The graph is optional — absent store, absent networkx or a load
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
from app.i18n import reply_instruction, t, term

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
# Inline citation markers like [1], [12], the per-study passage labels [1a],
# [1b] (P9), guidance markers [G1] and practice-record markers [W1] —
# stripped before the numeric check so reference indices are never mistaken
# for invented quantities.
_CITE_MARKER_RE = re.compile(r"\[[GW]?\d+[a-z]?\]")

EXPLAIN_SYSTEM_PROMPT = (
    "You are the evidence-explanation layer of AE+ Transform, an evidence-fusion "
    "advisor for agroecological practices in Ethiopia. You are given (1) a "
    "recommendation JSON from a field-trial machine-learning model, (2) a FUSED "
    "EVIDENCE block that states, for each practice, the model estimate for this "
    "area and the effects measured by field studies (each labelled \"Reported in "
    "study [n]\"), and which of them leads, and (3) numbered evidence passages "
    "retrieved from the source studies.\n"
    "Your job: explain WHY the ranked practices fit this specific context "
    "(agro-ecology, rainfall, slope, crop) and HOW to apply them in practice.\n"
    "Strict rules:\n"
    "- Ground every claim in the numbered passages or the FUSED EVIDENCE block "
    "and cite inline as [n] (e.g. [1], [3]). Passages are numbered PER STUDY: "
    "several passages of one study share its number and are labelled [1a], "
    "[1b], ... — cite the study as [1]. If nothing supports a claim, omit it — "
    "do not fill gaps from general knowledge.\n"
    "- You are never a source of numbers. Use ONLY numbers that appear in the "
    "FUSED EVIDENCE block, the recommendation JSON (model outputs, the user's "
    "context) or verbatim in a passage — and a number quoted from a passage "
    "must sit in the SAME sentence as that passage's citation [n]. Never "
    "invent, alter, average or recompute an effect, percentage or count.\n"
    "- When a study leads, say \"field studies in similar areas found ...\"; "
    "when the model leads, say \"the model estimates for your area ...\". If "
    "the block says the evidence disagrees, say so plainly.\n"
    "- Do not put a study citation on a sentence that only states the user's "
    "own context (rainfall, slope, altitude) — those values describe the pin, "
    "not a study.\n"
    "- Never write \"proven\", \"guaranteed\" or \"will increase\"; write "
    "\"trials found\", \"about\", \"in similar areas\".\n"
    "- An EVIDENCE BASE block, when present, states how many studies and "
    "field observations stand behind each practice and where they were "
    "measured. Those are counts and provenance: you may quote them to say how "
    "well-evidenced a practice is.\n"
    "- If GUIDANCE passages (numbered [G1], [G2], ...) are provided, they may "
    "inform HOW to implement a practice (steps, timing, costs, failure "
    "modes) ONLY — cite them inline as [Gn]. They are never evidence for "
    "effect sizes or rankings, and any number quoted from a guidance passage "
    "must appear verbatim in it and be cited [Gn].\n"
    "- If PRACTICE RECORDS (numbered [W1], [W2], ...) are provided, they "
    "describe HOW and WHERE ELSE a practice is implemented — cite them "
    "inline as [Wn]; they are never evidence for effect sizes or rankings.\n"
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
    are not copied here: study-level effects reach the prompt and the UI only
    as labelled values of the fused evidence bundle (``fusion_service``), so
    an unlabelled aggregate never sits beside the model's estimate.

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


def evidence_base_sentence(practice: str, entry: dict[str, Any], language: str = "en") -> str:
    """One human sentence of counts and provenance — no effect magnitudes.

    Catalogued per language (U1); ``en`` is byte-identical to the pre-U1 text.
    Only three numbers ever appear (studies, observations, studies in the
    corpus) — exactly the three the guardrail whitelists.
    """
    n_studies = int(entry["n_studies"])
    n_obs = int(entry["n_obs"])
    belts = entry.get("aez_belts") or []
    belts_bit = (
        t(language, "eb.in_belts",
          belts=t(language, "eb.belts_join").join(term(language, "aez", b) for b in belts))
        if belts else ""
    )
    in_corpus = n_studies_in_corpus(entry)
    return t(
        language, "eb.sentence",
        practice=practice, n_studies=n_studies,
        studies_word=t(language, "eb.study" if n_studies == 1 else "eb.studies"),
        n_obs=n_obs,
        obs_word=t(language, "eb.observation" if n_obs == 1 else "eb.observations"),
        belts=belts_bit, in_corpus=in_corpus,
        is_are=t(language, "eb.is" if in_corpus == 1 else "eb.are"),
    )


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


def study_key(chunk: dict[str, Any], index: int) -> str:
    """The provenance key one chunk is grouped under: era_code for Tier 1,
    url/doi/title for Tier 2/3; two unidentifiable chunks never collapse."""
    return str(chunk.get("era_code") or chunk.get("url") or chunk.get("doi")
               or chunk.get("title") or f"chunk-{index}")


def group_chunks_by_study(chunks: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Chunks grouped per study/document in first-appearance order (P9).

    The n-th group is the study cited as ``[n]`` in the prompt, the n-th
    citation in :func:`shape_citations` and the n-th chip in the UI — one
    numbering for all three.
    """
    order: list[str] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for i, c in enumerate(chunks):
        key = study_key(c, i)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)
    return [(key, groups[key]) for key in order]


_TIER_PREFIX = {"evidence": "", "guidance": "G", "practice": "W"}


def shape_citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One citation per study (era_code), deduped across retrieved chunks.

    Retrieval returns chunks, several of which may come from the same study;
    the citation list is per-study provenance for the UI. The first chunk of
    a study (highest fused rank) supplies the snippet and practice;
    ``n_passages`` counts how many retrieved passages that study contributed.
    ``ref`` (P9) is the marker the explanation uses for this source — the
    1-based group index with the tier prefix ("3", "G1", "W2") — numbered per
    tier, in the same order as the prompt labels.
    """
    citations: list[dict[str, Any]] = []
    counters: dict[str, int] = {"evidence": 0, "guidance": 0, "practice": 0}
    for _, group in group_chunks_by_study(chunks):
        c = group[0]
        tier = c.get("tier") or "evidence"
        counters[tier] = counters.get(tier, 0) + 1
        text = (c.get("text") or "").strip()
        citations.append({
            "era_code": c.get("era_code"),
            "tier": tier,
            "doi": c.get("doi"),
            "url": c.get("url"),
            "title": c.get("title"),
            "year": _safe_int(c.get("year")),
            "journal": c.get("journal"),
            "practice": c.get("for_practice"),
            "snippet": text[:SNIPPET_CHARS],
            "n_passages": len(group),
            "ref": f"{_TIER_PREFIX.get(tier, '')}{counters[tier]}",
        })
    # C2/C3: CGSpace titles and handle pages for guidance (identity-preserving).
    from app.services.source_meta import enrich_citation
    return [enrich_citation(c) for c in citations]


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


# --------------------------------------------------------- guardrail v2 (U9)
_REF_RE = re.compile(r"\[([GW]?\d+)[a-z]?\]")
_SUBLABEL_RE = re.compile(r"\[([GW]?\d+)[a-z]\]")
_STUDY_MARK_RE = re.compile(r"\s?\[\d+\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?።])\s+")
# A number token, but not digits inside an identifier ("NN0123", "CSA_18", "G2").
_GUARD_NUM_RE = re.compile(r"(?<![A-Za-z_\d.])\d+(?:\.\d+)?")
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}\b)")
_UNIT_RE = re.compile(
    r"\s?(%|mm|cm|°\s?C|m\b|kg|g\b|t/ha|t\b|tonnes?|tons?|quintals?|q\b|ha\b|hectares?|litres?|liters?|l\b|days?\b)",
    re.I,
)


def normalise_markers(text: str) -> str:
    """``[1a]``/``[2b]`` → ``[1]``/``[2]``: one visible number per study (B4)."""
    return _SUBLABEL_RE.sub(r"[\1]", text)


def fused_allowed(
    recommendation: dict[str, Any],
    bundles: list[dict[str, Any]],
    evidence_base: dict[str, dict[str, Any]] | None = None,
) -> dict[str, set[float]]:
    """Numbers allowed ANYWHERE, by source (decision §5 a, b, d, e)."""
    allowed: dict[str, set[float]] = {"model": set(), "study": set(), "context": set(), "count": set()}
    details = recommendation.get("details") or {}
    query = recommendation.get("query") or {}
    for item in details.get("ranked") or []:
        _collect_numbers({k: v for k, v in item.items() if k != "n_evidence"}, allowed["model"])
        _collect_numbers(item.get("n_evidence"), allowed["count"])
    _collect_numbers([r.get("effect") for r in recommendation.get("recommendations") or []], allowed["model"])
    _collect_numbers(details.get("context") or {}, allowed["context"])
    _collect_numbers({"lat": query.get("lat"), "lon": query.get("lon")}, allowed["context"])
    for b in bundles:
        m = b.get("model") or {}
        _collect_numbers([m.get("value"), m.get("display")], allowed["model"])
        _collect_numbers([m.get("n_obs"), m.get("n_studies"), m.get("n_obs_in_zone")], allowed["count"])
        for obj in [b.get("headline") or {}, b.get("study") or {}, *((b.get("headline") or {}).get("range") or [])]:
            if obj.get("source") == "study":
                _collect_numbers([obj.get("value"), obj.get("display")], allowed["study"])
        study = b.get("study") or {}
        _collect_numbers([study.get("n_studies"), study.get("n_obs")], allowed["count"])
        for st in b.get("studies") or []:
            _collect_numbers([st["effect"]["value"], st["effect"]["display"]], allowed["study"])
            _collect_numbers([st.get("n_obs"), st.get("year")], allowed["count"])
    for entry in (evidence_base or {}).values():
        _collect_numbers([entry.get("n_studies"), entry.get("n_obs"), n_studies_in_corpus(entry)], allowed["count"])
    return allowed


def passage_numbers(chunks: list[dict[str, Any]], prefix: str = "") -> dict[str, set[float]]:
    """Per citation ref (``"1"``, ``"G2"``): the numbers its passages state (decision §5 c)."""
    out: dict[str, set[float]] = {}
    for i, (_, group) in enumerate(group_chunks_by_study(chunks), start=1):
        nums: set[float] = set()
        for c in group:
            for field in ("text", "title", "year"):
                _collect_numbers(_THOUSANDS_RE.sub("", str(c.get(field) or "")), nums)
        out[f"{prefix}{i}"] = nums
    return out


def _unit_after(text: str, end: int) -> str | None:
    m = _UNIT_RE.match(text, end)
    return m.group(1).replace(" ", "") if m else None


def guard_v2(
    text: str,
    allowed: dict[str, set[float]],
    passages: dict[str, set[float]],
) -> dict[str, Any]:
    """Numeric guard v2: every number must have a source; passage numbers must
    sit in the sentence that cites their passage.

    A sentence with an unsourced number is removed. A study marker on a
    sentence whose numbers are all the user's own context is dropped (B4).
    Returns ``{text, numbers, removed, kept, grounded}`` where ``numbers`` are
    provenance objects ``{value, unit, source, ref, display}``.
    """
    from app.services.numbers import number as num_obj

    text = normalise_markers(text)
    numbers: list[dict[str, Any]] = []
    removed = kept = 0
    out_lines: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            out_lines.append(line)
            continue
        sentences = _SENTENCE_SPLIT.split(line)
        kept_sentences: list[str] = []
        for sentence in sentences:
            refs = set(_REF_RE.findall(sentence))
            plain = _THOUSANDS_RE.sub("", _CITE_MARKER_RE.sub(" ", sentence))
            found: list[dict[str, Any]] = []
            ok = True
            for m in _GUARD_NUM_RE.finditer(plain):
                value = float(m.group(0))
                variants = _number_variants(value)
                unit = _unit_after(plain, m.end())
                source, ref = None, None
                # A small integer or a year is a count — unless a unit follows ("7 tonnes" is a quantity).
                if value.is_integer() and (0 <= value <= 10 or 1900 <= value <= 2100) and unit is None:
                    source = "count"
                else:
                    for src in ("study", "model", "context", "count"):
                        if variants & allowed.get(src, set()):
                            source = src
                            break
                    if source is None:
                        for r in sorted(refs):
                            if variants & passages.get(r, set()):
                                source, ref = "passage", r
                                break
                if source is None:
                    ok = False
                    logger.warning("Guard v2 removed a sentence with unsourced number %r.", m.group(0))
                    break
                found.append(num_obj(value, unit, source, ref))
            if not ok:
                removed += 1
                continue
            significant = [f for f in found if not (f["source"] == "count" and f["value"] <= 10)]
            if significant and all(f["source"] == "context" for f in significant):
                sentence = _STUDY_MARK_RE.sub("", sentence)  # context is the pin, not a study
            numbers.extend(found)
            kept_sentences.append(sentence)
            kept += 1
        if kept_sentences:
            out_lines.append(" ".join(kept_sentences))
    clean = "\n".join(out_lines).strip()
    grounded = bool(_REF_RE.search(clean)) and kept > 0 and removed <= kept
    return {"text": clean, "numbers": numbers, "removed": removed, "kept": kept, "grounded": grounded}


# ------------------------------------------------------------------- fallback
def build_fallback_text(
    recommendation: dict[str, Any],
    chunks: list[dict[str, Any]],
    evidence_base: dict[str, dict[str, Any]] | None = None,
    language: str = "en",
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
    raw_indicator = query.get("indicator")
    indicator = (
        term(language, "indicator", raw_indicator) if raw_indicator
        else t(language, "explain.default_indicator")
    )
    sentences: list[str] = []
    for rec in recommendation.get("recommendations") or []:
        practice = rec.get("practice") or t(language, "explain.default_practice")
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
        cites = t(language, "explain.fallback.cite_join").join(
            t(language, "explain.fallback.cite",
              title=c.get("title") or t(language, "explain.untitled_study"),
              era_code=c.get("era_code"))
            for c in cited[:2]
        )
        sentence = t(language, "explain.fallback.sentence",
                     practice=practice, effect=effect).rstrip()
        if cites:
            sentence += t(language, "explain.fallback.supported_by", cites=cites)
        sentences.append(sentence + ".")
        entry = (evidence_base or {}).get(practice)
        if entry:
            sentences.append(evidence_base_sentence(practice, entry, language))
    if not sentences:
        sentences.append(t(language, "explain.fallback.none", indicator=indicator))
    return " ".join(sentences)


# ------------------------------------------------------------------ LLM path
def _build_messages(
    recommendation: dict[str, Any],
    question: str | None,
    chunks: list[dict[str, Any]],
    guidance_chunks: list[dict[str, Any]] | None = None,
    evidence_base: dict[str, dict[str, Any]] | None = None,
    language: str = "en",
    fused_block: str | None = None,
) -> list[dict[str, str]]:
    passages = []
    for i, (_, group) in enumerate(group_chunks_by_study(chunks), start=1):
        for j, c in enumerate(group):
            # One number per STUDY; its passages are [1a], [1b], ... (P9).
            label = f"[{i}]" if len(group) == 1 else f"[{i}{chr(ord('a') + j)}]"
            header = f"{label} ({c.get('era_code')}) {c.get('title')} ({c.get('year')})"
            passages.append(f"{header}\n{(c.get('text') or '').strip()}")
    user = (
        "RECOMMENDATION JSON (authoritative model output; with the fused evidence block, the only source of effect "
        "numbers):\n```json\n"
        + json.dumps(recommendation, indent=2, default=str)
        + "\n```\n"
    )
    if fused_block:
        user += (
            "\nFUSED EVIDENCE (per practice: which evidence leads, the model estimate "
            "for this area and the effects reported by field studies — the only "
            "effect numbers you may state):\n" + fused_block + "\n"
        )
    if evidence_base:
        # Counts and provenance only.
        lines = "\n".join(
            evidence_base_sentence(practice, entry, language)
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
        "\nEVIDENCE PASSAGES (numbered per study; cite the study as [n]):\n\n"
        + "\n\n".join(passages)
    )
    if guidance_chunks:
        guidance_passages = []
        for i, (_, group) in enumerate(group_chunks_by_study(guidance_chunks), start=1):
            for j, c in enumerate(group):
                label = f"[G{i}]" if len(group) == 1 else f"[G{i}{chr(ord('a') + j)}]"
                header = f"{label} {c.get('title')} ({c.get('year')})"
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
        # Every other rule is unchanged; the language line is appended (U1 §D).
        {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT + "\n" + reply_instruction(language)},
        {"role": "user", "content": user},
    ]


def _call_llm(messages: list[dict[str, str]], json_mode: bool = False) -> str | None:
    """One OpenAI chat completion (no tools). Returns None on any failure."""
    settings = get_settings()
    payload: dict[str, Any] = {"model": EXPLAIN_MODEL, "messages": messages, "temperature": EXPLAIN_TEMPERATURE}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        response = httpx.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            json=payload,
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


# ------------------------------------------------- guidance quality + how-to (U9, C1)
_EN_STOPWORDS = frozenset(
    "the of and to in is for on that with are as be by this from or it at an which can was were "
    "have has their its into also more when should".split()
)
#: Places that make a guidance document off-region for Ethiopia unless it also
#: mentions Ethiopia or the wider African context.
_OFF_REGION_RE = re.compile(
    r"(?i)\b(andes|andean|peru|bolivia|ecuador|colombia|mexico|brazil|argentina|chile|guatemala|honduras|"
    r"india|bangladesh|nepal|pakistan|china|vietnam|laos|cambodia|philippines|indonesia|europe|spain)\b"
)
_ON_REGION_RE = re.compile(
    r"(?i)\b(ethiopia|ethiopian|africa|african|kenya|tanzania|uganda|rwanda|sahel|tigray|amhara|oromia|"
    r"sidama|horn of africa|east africa)\b"
)


def _looks_english(text: str) -> bool:
    words = re.findall(r"[a-záéíóúñ]+", text.lower())
    if len(words) < 20:
        return True  # too short to judge: let quality decide
    return sum(w in _EN_STOPWORDS for w in words) / len(words) >= 0.08


def usable_guidance(chunks: list[dict[str, Any]], min_quality: float | None = None) -> list[dict[str, Any]]:
    """Guidance passages fit to show (C1): no reference lists, front matter or
    boilerplate (``rag.ingest.quality``), English, on-region for Ethiopia, and
    relevant — the passage names a component of the practice it is attached to.
    """
    _ensure_repo_root_on_path()
    from rag.graph.component_keywords import COMPONENT_KEYWORDS, components_in_text
    from rag.graph.practice_components import decompose
    from rag.ingest.quality import chunk_quality

    floor = float(min_quality if min_quality is not None else get_settings().guidance_min_quality)
    keep: list[dict[str, Any]] = []
    for c in chunks:
        text = c.get("text") or ""
        if chunk_quality(text)["score"] < floor:
            continue
        if not _looks_english(text):
            continue
        if _OFF_REGION_RE.search(text) and not _ON_REGION_RE.search(text):
            continue
        practice = c.get("for_practice")
        if practice:
            try:
                wanted = set(decompose(practice))
            except Exception:
                wanted = set()
            # Relevance floor, applied only where the keyword table knows the
            # practice's components (an unmapped component cannot be matched).
            wanted &= set(COMPONENT_KEYWORDS)
            if wanted and not wanted & set(components_in_text(text)):
                continue  # the passage must be about this practice
        keep.append(c)
    return keep


HOWTO_PROMPT = (
    "You write implementation steps for extension workers. For EACH practice listed, write 3 to 6 "
    "short, numbered, practical steps (what to do, when, with what) using ONLY the numbered "
    "guidance passages. End every step with its citation [Gn]. If the passages give nothing "
    "practical for a practice, return an empty list for it. Use only numbers that appear verbatim "
    "in the cited passage, in the same step as its citation. Return JSON: "
    '{"steps": {"<practice exactly as given>": ["step text [G1]", ...]}}.'
)


def howto_steps(
    practices: list[str], guidance_chunks: list[dict[str, Any]], allowed: dict[str, set[float]], language: str,
) -> dict[str, list[str]]:
    """Synthesised, cited implementation steps per practice (C1); ``{}`` without key or passages."""
    if not practices or not guidance_chunks or not get_settings().openai_api_key:
        return {}
    passages = []
    for i, (_, group) in enumerate(group_chunks_by_study(guidance_chunks), start=1):
        body = "\n".join((c.get("text") or "").strip() for c in group)
        passages.append(f"[G{i}] {group[0].get('title')} (for {group[0].get('for_practice')})\n{body}")
    messages = [
        {"role": "system", "content": HOWTO_PROMPT + "\n" + reply_instruction(language)},
        {"role": "user", "content": "PRACTICES:\n" + "\n".join(f"- {p}" for p in practices)
         + "\n\nGUIDANCE PASSAGES:\n\n" + "\n\n".join(passages)},
    ]
    raw = _call_llm(messages, json_mode=True)
    if not raw:
        return {}
    try:
        data = json.loads(raw).get("steps") or {}
    except (ValueError, AttributeError):
        logger.warning("How-to steps were not valid JSON — none shown.")
        return {}
    guide_numbers = passage_numbers(guidance_chunks, "G")
    out: dict[str, list[str]] = {}
    for practice in practices:
        steps: list[str] = []
        for step in data.get(practice) or []:
            if not isinstance(step, str) or not re.search(r"\[G\d+\]", step):
                continue  # cite or stay silent
            guarded = guard_v2(re.sub(r"^\s*\d+[.)]\s*", "", step.strip()), allowed, guide_numbers)
            if guarded["removed"] == 0 and guarded["text"]:
                steps.append(guarded["text"])
        if steps:
            out[practice] = steps[:6]
    return out


# -------------------------------------------------------- fusion helpers (U9)
def _fuse(recommendation: dict[str, Any], graph_query: Any) -> list[dict[str, Any]]:
    """Evidence bundles for the recommendation's practices; ``[]`` when unavailable."""
    from app.services import fusion_service as fusion

    if not (recommendation.get("details") or {}).get("ranked"):
        return []
    try:
        return fusion.fuse(recommendation, graph_query=graph_query)
    except Exception as exc:  # optional layer — degrade to the pre-U9 explanation
        logger.warning("Evidence fusion unavailable for /explain (%s).", exc)
        return []


def study_registry(
    chunks: list[dict[str, Any]], bundles: list[dict[str, Any]], max_studies: int = 3,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """One numbering for passages AND the study effects of the bundles (B4).

    A study whose ERA code matches a retrieved passage group shares its
    number; any other cited study gets the next free number and a citation
    entry of its own. Returns ``(ref_of, extra_citations)``.
    """
    groups = [key for key, _ in group_chunks_by_study(chunks)]
    index = {key: i for i, key in enumerate(groups, start=1)}
    ref_of: dict[str, str] = {}
    extra: list[dict[str, Any]] = []
    for b in bundles:
        lead = set((b.get("study") or {}).get("refs") or [])
        shown = [s for s in b.get("studies") or [] if s["ref"] in lead] or (b.get("studies") or [])
        for st in shown[:max_studies]:
            if st["ref"] in ref_of:
                continue
            if st.get("era_code") and st["era_code"] in index:
                ref_of[st["ref"]] = str(index[st["era_code"]])
                continue
            n = len(index) + 1
            index[f"study:{st['study_no']}"] = n
            ref_of[st["ref"]] = str(n)
            extra.append({
                "era_code": st.get("era_code"), "tier": "evidence", "doi": st.get("doi"), "url": None,
                "title": st.get("title"), "year": _safe_int(st.get("year")), "journal": None,
                "practice": b["practice"], "snippet": "", "n_passages": 0, "ref": str(n),
                "study_no": st.get("study_no"), "data_source": st.get("data_source"),
            })
    from app.services.source_meta import enrich_citation
    extra = [enrich_citation(c) for c in extra]
    return ref_of, extra


def fused_block(bundles: list[dict[str, Any]], indicator: str, ref_of: dict[str, str]) -> str:
    """The FUSED EVIDENCE prompt block (English, labelled, cited)."""
    from app.services import fusion_service as fusion

    lines: list[str] = []
    for b in bundles:
        lead = "field studies" if b["lead_source"] == fusion.LEAD_STUDY else "the field-trial model"
        lines.append(f"- {b['practice']} (leading evidence: {lead}):")
        for line in fusion.evidence_lines(b, indicator, "en", lambda r: ref_of.get(r, "?")):
            lines.append(f"  {line}")
    return "\n".join(lines)


def summary_register(bundles: list[dict[str, Any]], indicator: str, language: str) -> str:
    """Plain register: one plain sentence per practice, no markers (A5)."""
    from app.services import fusion_service as fusion
    from app.services.practice_names import practice_name

    return "\n".join(
        fusion.summary_text(b, indicator, language, practice_name(b["practice"], language)) for b in bundles
    )


def build_fused_fallback(
    bundles: list[dict[str, Any]], chunks: list[dict[str, Any]], indicator: str, language: str,
    ref_of: dict[str, str], evidence_base: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Deterministic evidence register: labelled lines per practice + passage citations."""
    from app.services import fusion_service as fusion
    from app.services.practice_names import practice_name

    groups = group_chunks_by_study(chunks)
    blocks: list[str] = []
    for b in bundles:
        lines = [f"**{practice_name(b['practice'], language)}**"]
        lines += fusion.evidence_lines(b, indicator, language, lambda r: ref_of.get(r, r.split(":", 1)[1]))
        cites = [
            t(language, "explain.fallback.cite",
              title=g[0].get("title") or t(language, "explain.untitled_study"),
              era_code=g[0].get("era_code")) + f" [{i}]"
            for i, (_, g) in enumerate(groups, start=1) if g[0].get("for_practice") == b["practice"]
        ][:2]
        if cites:
            supported = t(language, "explain.fallback.supported_by",
                          cites=t(language, "explain.fallback.cite_join").join(cites)).strip().lstrip(",").strip()
            lines.append(supported[:1].upper() + supported[1:].rstrip(".") + ".")
        entry = (evidence_base or {}).get(b["practice"])
        if entry:
            lines.append(evidence_base_sentence(b["practice"], entry, language))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# ------------------------------------------------------------------- explain
def explain(
    recommendation: dict[str, Any],
    question: str | None = None,
    k: int = 8,
    retriever: Any = None,
    guidance_retriever: Any = None,
    graph_query: Any = None,
    language: str = "en",
) -> dict[str, Any]:
    """Produce a grounded explanation of a recommendation (evidence fusion, U9).

    Returns ``{"explanation", "summary", "numbers", "citations", "grounded",
    "llm_used", "evidence_base", "removed_sentences"}``:

    * ``explanation`` is the **evidence register** — labelled and cited; its
      numbers passed guard v2 (decision §5) sentence by sentence;
    * ``summary`` is the **plain register** — one sentence per practice built
      from the evidence bundles' headline values, no markers;
    * ``numbers`` are provenance objects for every number in ``explanation``.

    ``evidence_base`` is ``{}`` whenever the knowledge graph is not built.
    Without fusion bundles (no graph, or no ranked practices) the pre-U9
    deterministic texts are used unchanged.
    """
    gq = graph_query if graph_query is not None else get_graph_query()
    r = retriever if retriever is not None else get_retriever()
    chunks = r.retrieve_for_recommendation(recommendation, k=k)
    citations = shape_citations(chunks)
    evidence_base = build_evidence_base(recommendation, gq)
    indicator = str((recommendation.get("query") or {}).get("indicator") or "")
    bundles = _fuse(recommendation, gq) if gq is not None else []
    summary = summary_register(bundles, indicator, language) if bundles else ""
    ref_of, study_citations = study_registry(chunks, bundles)

    base = {"summary": summary, "evidence_base": evidence_base, "removed_sentences": 0, "howto": {}}
    if not chunks:
        # Cite or stay silent — with nothing retrieved we make no claims.
        return {**base, "explanation": t(language, "explain.no_chunks"), "numbers": [], "citations": [],
                "grounded": False, "llm_used": False}

    allowed = fused_allowed(recommendation, bundles, evidence_base)
    passages = passage_numbers(chunks)
    if get_settings().openai_api_key:
        g = (guidance_retriever if guidance_retriever is not None else get_guidance_retriever())
        guidance_chunks: list[dict[str, Any]] = []
        if g is not None:
            try:
                guidance_chunks = usable_guidance(g.retrieve_for_recommendation(recommendation, k=GUIDANCE_K))
            except Exception as exc:  # guidance is optional — degrade, don't fail
                logger.warning("Guidance retrieval failed (%s) — evidence only.", exc)
                guidance_chunks = []
        text = _call_llm(_build_messages(
            recommendation, question, chunks, guidance_chunks, evidence_base, language,
            fused_block=fused_block(bundles, indicator, ref_of) if bundles else None,
        ))
        if text:
            guarded = guard_v2(text, allowed, {**passages, **passage_numbers(guidance_chunks, "G")})
            if guarded["grounded"]:
                shown = [r.get("practice") for r in recommendation.get("recommendations") or [] if r.get("practice")]
                return {**base, "explanation": guarded["text"], "numbers": guarded["numbers"],
                        "removed_sentences": guarded["removed"],
                        "howto": howto_steps(shown, guidance_chunks, allowed, language),
                        "citations": citations + study_citations + shape_citations(guidance_chunks),
                        "grounded": True, "llm_used": True}
            logger.warning(
                "LLM explanation rejected by numeric guardrail v2 — returning deterministic fallback."
            )

    # No key, LLM failure, or guard rejection → deterministic template.
    if bundles:
        text = build_fused_fallback(bundles, chunks, indicator, language, ref_of, evidence_base)
        cited = citations + study_citations
    else:
        text = build_fallback_text(recommendation, chunks, evidence_base, language)
        cited = citations
    return {**base, "explanation": text, "numbers": guard_v2(text, allowed, passages)["numbers"],
            "citations": cited, "grounded": True, "llm_used": False}
