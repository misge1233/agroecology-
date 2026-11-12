"""Knowledge context of Methodology 2: retrieved passages and graph facts (E6 Part 2).

**Passages** (variants ``m2_rag`` and ``m2_graph``): the masked
:class:`rag.retrieve.TieredRetriever` over Tier 1 (study passages), Tier 2 (guidance) and
the guidelines, with one query per candidate built from the practice, the objective and
the context in words; at most 2 passages per candidate and 4 per prompt (brief Part 5),
each trimmed to 120 tokens, with its tier and citation. Query embeddings are cached on
disk (``model/m2/cache/embeddings``) and counted in the cost ledger.

**Graph facts** (variant ``m2_graph``): from the masked graph view
(:meth:`rag.graph.query.GraphQuery.masked`), per candidate: its components, the
challenges it addresses, the catalogue entry's farming system (land use) and suitable
agroecological belts, its scale and limitations; at most 60 tokens per candidate.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from model.harness.mask import Mask
from model.m2 import CACHE_DIR

logger = logging.getLogger(__name__)

PASSAGES_PER_CANDIDATE = 2
MAX_PASSAGES = 4
PASSAGE_TOKENS = 120
FACT_TOKENS = 60


# ----------------------------------------------------------------- tokens
_ENC = None


def encoder() -> Any:
    global _ENC
    if _ENC is None:
        import tiktoken

        _ENC = tiktoken.get_encoding("o200k_base")  # the gpt-4o family encoding
    return _ENC


def n_tokens(text: str) -> int:
    return len(encoder().encode(text))


def trim_tokens(text: str, limit: int) -> str:
    toks = encoder().encode(text)
    if len(toks) <= limit:
        return text
    return encoder().decode(toks[:limit]).rstrip() + " ..."


# ----------------------------------------------------------------- passages
def cached_embedder(embed: Callable[[str], list[float]], cache_dir: Path, on_call: Callable[[str], None] | None = None
                    ) -> Callable[[str], list[float]]:
    """Wrap a retriever's ``_embed`` with a disk cache keyed by the text's hash."""
    cache_dir.mkdir(parents=True, exist_ok=True)

    def _cached(text: str) -> list[float]:
        p = cache_dir / (hashlib.sha256(text.encode("utf-8")).hexdigest()[:32] + ".json")
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        for attempt in range(5):  # transient connection drops are retried; other errors raise
            try:
                vec = embed(text)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 4 or "Connection" not in type(exc).__name__ + str(exc):
                    raise
                logger.warning("embedding connection error (%s); retrying", type(exc).__name__)
                time.sleep(2.0 * (attempt + 1))
        p.write_text(json.dumps(vec), encoding="utf-8")
        if on_call:
            on_call(text)
        return vec

    return _cached


def default_tiered_retriever(on_embed: Callable[[str], None] | None = None, cache_dir: Path = CACHE_DIR / "embeddings") -> Any:
    """Tier 1 + Tier 2 + guidelines behind one masked :class:`TieredRetriever`, embeddings cached."""
    from rag.retrieve import (TieredRetriever, default_guidance_retriever, default_guidelines_retriever,
                              default_retriever)

    tiers = [default_retriever()]
    for make in (default_guidance_retriever, default_guidelines_retriever):
        try:
            tiers.append(make())
        except Exception as exc:  # noqa: BLE001 - a missing tier degrades, it is reported
            logger.warning("retrieval tier unavailable: %s", exc)
    for t in tiers:
        if not getattr(t, "_m2_cached", False):
            t._embed = cached_embedder(t._embed, cache_dir, on_embed)
            t._m2_cached = True
    return TieredRetriever(tiers)


def passage_query(practice_name: str, outcome_name: str, better: str, context_words: str) -> str:
    return f"{practice_name} effect on {outcome_name} ({better}) Ethiopia {context_words}"


def passage_citation(chunk: Mapping[str, Any]) -> str:
    title = str(chunk.get("title") or chunk.get("doc_title") or "").strip()
    year = chunk.get("year")
    src = chunk.get("era_code") or chunk.get("doc_id") or chunk.get("publisher") or ""
    bits = [b for b in (title[:80], str(int(year)) if isinstance(year, (int, float)) and year == year else "", str(src)) if b]
    doi = f" doi:{chunk['doi']}" if chunk.get("doi") else ""
    return "; ".join(bits) + doi


class PassageSource:
    """Masked passages per candidate with an in-process result cache (query text x mask)."""

    def __init__(self, retriever: Any, cache_dir: Path | None = None) -> None:
        self.retriever = retriever
        self._memo: dict[tuple[str, str], list[dict[str, Any]]] = {}
        #: retrieval results on disk (query text x mask): approximate dense search can swap
        #: passages with tied fused scores between processes; reruns read the stored order
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None

    def _retrieve(self, q: str, mkey: str, mask: Mask, k: int) -> list[dict[str, Any]]:
        p = None
        if self.cache_dir is not None:
            p = self.cache_dir / (hashlib.sha256(f"{q}\x1f{mkey}\x1f{k}".encode("utf-8")).hexdigest()[:32] + ".json")
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        hits = self.retriever.retrieve(q, k=k, mask=mask)
        if p is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
            keep = ("chunk_id", "tier", "text", "title", "doc_title", "year", "era_code", "doc_id", "publisher", "doi", "study_ids")
            p.write_text(json.dumps([{k_: h.get(k_) for k_ in keep} for h in hits], default=str), encoding="utf-8")
        return hits

    def for_candidates(self, queries: dict[str, str], mask: Mask, per_candidate: int = PASSAGES_PER_CANDIDATE,
                       max_total: int = MAX_PASSAGES) -> list[dict[str, Any]]:
        """``[{candidate, chunk_id, tier, citation, text}]``: round robin over candidates, deduplicated."""
        per: dict[str, list[dict[str, Any]]] = {}
        mkey = mask.to_json()
        for cand, q in queries.items():
            key = (q, mkey)
            if key not in self._memo:
                self._memo[key] = self._retrieve(q, mkey, mask, per_candidate)
            per[cand] = self._memo[key][:per_candidate]
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for rank in range(per_candidate):
            for cand in queries:
                hits = per.get(cand, [])
                if rank < len(hits) and len(out) < max_total and hits[rank]["chunk_id"] not in seen:
                    h = hits[rank]
                    seen.add(h["chunk_id"])
                    out.append({"candidate": cand, "chunk_id": h["chunk_id"], "tier": h.get("tier", "evidence"),
                                "citation": passage_citation(h), "text": trim_tokens(" ".join(str(h.get("text", "")).split()), PASSAGE_TOKENS),
                                "doi": h.get("doi"), "era_code": h.get("era_code"), "study_ids": h.get("study_ids")})
        return out

    @property
    def unmaskable(self) -> dict[str, int]:
        return getattr(self.retriever, "unmaskable", {})


# ----------------------------------------------------------------- graph facts
def graph_facts(view: Any, practice_id: str, limit: int = FACT_TOKENS) -> str:
    """Components, challenges, catalogue farming system, suitable belts, scale and limitations."""
    from rag.graph.query import _practice_node
    from rag.graph.schema import EdgeType

    nid = _practice_node(view, practice_id)
    if nid is None:
        return ""
    comps = [d.split(":", 1)[1] for d, _ in view._out(nid, EdgeType.COMPOSED_OF)]
    chall = sorted({str(view._attrs(d).get("name_en") or d.split(":", 1)[1]) for d, _ in view._out(nid, EdgeType.ADDRESSES_PROBLEM)})
    parts = []
    if comps:
        parts.append("components: " + ", ".join(comps))
    if chall:
        parts.append("addresses: " + "; ".join(chall))
    cats = view.documents_for_practice(practice_id)["catalogue"]
    if cats:
        c = cats[0]
        cid = "CatalogueEntry:" + c["catalogue_id"]
        belts = sorted({d.split(":", 1)[1] for d, _ in view._out(cid, EdgeType.SUITABLE_IN)})
        if c.get("farming_system"):
            parts.append(f"land use: {c['farming_system']}")
        if belts:
            parts.append("suitable belts: " + ", ".join(belts))
        if c.get("scale"):
            parts.append(f"scale: {c['scale']}")
        if c.get("limitations"):
            parts.append(f"limitations: {c['limitations']}")
    return trim_tokens(" | ".join(parts), limit) if parts else ""


class GraphFacts:
    """Facts per candidate from the masked graph view of the current fold."""

    def __init__(self, graph: Any = None) -> None:
        self._graph = graph
        self.view: Any = None

    def fit(self, mask: Mask) -> "GraphFacts":
        if self._graph is None:
            from rag.graph.query import GraphQuery

            self._graph = GraphQuery.load()
        self.view = self._graph.masked(mask)
        return self

    def facts(self, candidates: list[str]) -> dict[str, str]:
        assert self.view is not None, "fit first"
        return {c: graph_facts(self.view, c) for c in candidates}
