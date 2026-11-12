"""Structured retrieval over the ERA corpus index.

The retrieval query is NOT the user's free text — it is built from the
recommendation JSON the ML engine already produced (practice x resolved
context x indicator), which makes retrieval precise and keeps the RAG layer
strictly downstream of the evidence model.

Hybrid search: dense (Chroma, OpenAI embeddings) + lexical (BM25 over the
same chunks), fused with reciprocal-rank fusion (RRF). Returns chunks with
full provenance (era_code, doi, title, year) ready for cite-or-silent
generation and for the era_code -> training-rows linkage.

Two tiers, never mixed (P5a): the same class serves Tier 1 evidence
("era_corpus", the default) and Tier 2 guidance ("guidance_corpus") — pass
``collection=`` plus that tier's chunks file. Each instance builds its own
BM25 over its own chunks, so the hybrid machinery is shared but the corpora
stay strictly separate.

Tier 2b (E2): the ``guidelines`` collection (government guidelines, page-level
chunks) is a third, separate collection. :class:`TieredRetriever` fuses the
ranked lists of several tiers with the same RRF used inside each tier, and
every hit carries its ``tier`` tag. ``RAG_GUIDELINES_ENABLED=false`` (env or
``app/backend/.env``; default true) leaves the Tier 2 path exactly as before.

Masked retrieval (E4 Part 3): every ``retrieve`` call takes an optional
``mask`` (:class:`model.harness.mask.Mask`, the held-out groups of an evaluation
fold). The dense query carries a Chroma ``where`` filter on ``doi`` and ``era_code``,
the lexical candidates are filtered the same way, and every fused hit is checked once
more with ``mask.blocks_chunk`` (which also reads the ``study_ids`` list of the
re-indexed Tier 1), so a held-out study cannot surface through any path. Chunks that
carry no study metadata at all can never be masked; they are counted in
``retriever.unmaskable`` and reported by the harness.

Usage (library):
    from rag.retrieve import RagRetriever
    r = RagRetriever(index_dir=".../rag/index/store", chunks_path=".../rag/corpus/chunks.jsonl")
    hits = r.retrieve_for_recommendation(recommendation_json, k=8)
"""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

EMBED_MODEL = "text-embedding-3-small"
EMBED_URL = "https://api.openai.com/v1/embeddings"
COLLECTION = "era_corpus"
GUIDANCE_COLLECTION = "guidance_corpus"
GUIDELINES_COLLECTION = "guidelines"   # Tier 2b, government guidelines (E2)
RRF_K = 60          # standard reciprocal-rank-fusion constant
CANDIDATES = 40     # candidates per retriever before fusion


def _find_api_key() -> str:
    """OPENAI_API_KEY from the environment, else from app/backend/.env.

    Same fallback as ingest/build_index.py, so one key configuration serves
    the indexer, the retriever, and the backend alike.
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    env_path = Path(__file__).resolve().parents[1] / "app" / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _find_index_dir(default: Path) -> Path:
    """Index-store dir: RAG_INDEX_DIR (env, else app/backend/.env), else default.

    Needed because Chroma's SQLite cannot operate across the Windows<->WSL
    ``\\\\wsl.localhost`` bridge (locks fail for reads AND writes — measured
    21 Aug 2026), so the store may live outside the repo, on the native
    filesystem of the OS that runs Python. The backend already honors
    RAG_INDEX_DIR via app/config.py; this gives the eval scripts and the
    CLI (which use ``default_retriever()``) the same behaviour.
    """
    value = os.environ.get("RAG_INDEX_DIR", "").strip()
    if not value:
        env_path = Path(__file__).resolve().parents[1] / "app" / "backend" / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("RAG_INDEX_DIR="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return Path(value) if value else default


# Indicator-name synonyms appended to the query text (P5a, measured fix for
# the WUE terminology gap found in P3: relevant studies say "water
# productivity" where the dataset says "water use efficiency"). "SOM content"
# and "soil loss" get the corpus's own spellings for the same reason —
# abbreviation expanded, "erosion" vocabulary added. Purely additive: the
# original indicator name always stays in the query.
INDICATOR_SYNONYMS: dict[str, tuple[str, ...]] = {
    "water use efficiency": ("water productivity",),
    "SOM content": ("soil organic matter",),
    "soil loss": ("soil erosion",),
}


def build_query_text(
    recommendation: dict[str, Any],
    practice: str | None = None,
    expand: bool = True,
) -> str:
    """Compose the retrieval query from the engine's recommendation JSON.

    ``expand`` controls the indicator-synonym expansion documented above.
    It defaults to True, so the query the app sends is byte-identical to
    before this parameter existed; ``expand=False`` drops only the
    ``INDICATOR_SYNONYMS`` terms and is used by the evaluation harness to
    measure the expansion's contribution (``build_queries.py
    --no-query-expansion``).
    """
    q = recommendation.get("query", {})
    d = recommendation.get("details", {})
    ctx = d.get("context", {}) or {}
    top_practice = practice or (
        (recommendation.get("recommendations") or [{}])[0].get("practice", "")
    )
    indicator = q.get("indicator", "")
    parts = [
        top_practice,
        q.get("practice_family", ""),
        f"effect on {indicator}",
        *(INDICATOR_SYNONYMS.get(indicator, ()) if expand else ()),
        "Ethiopia",
        str(ctx.get("aez_belt") or ""),
    ]
    if q.get("crop_type"):
        parts.append(str(q["crop_type"]))
    if ctx.get("Rainfall"):
        parts.append(f"{round(float(ctx['Rainfall']))} mm annual rainfall")
    if ctx.get("slope") is not None:
        parts.append(f"{round(float(ctx['slope']))}% slope")
    return " ".join(p for p in parts if p).strip()


def index_hash(chunks_path: str | Path) -> str:
    """SHA-256 of a chunks file's ids and texts (the evaluation baseline's index identity)."""
    h = hashlib.sha256()
    for line in Path(chunks_path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            c = json.loads(line)
            h.update(c["chunk_id"].encode("utf-8"))
            h.update(b"\x1f")
            h.update(hashlib.sha256(c["text"].encode("utf-8")).digest())
            h.update(b"\n")
    return h.hexdigest()


class RagRetriever:
    def __init__(self, index_dir: str | Path, chunks_path: str | Path,
                 api_key: str | None = None, collection: str = COLLECTION):
        import chromadb  # deferred heavy import

        self._client = chromadb.PersistentClient(path=str(index_dir))
        self._col = self._client.get_collection(collection)
        self._chunks_path = Path(chunks_path)
        self._chunks = [
            json.loads(l)
            for l in Path(chunks_path).read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        self._by_id = {c["chunk_id"]: c for c in self._chunks}
        self._api_key = api_key or _find_api_key()
        self._session = requests.Session()
        self._bm25 = None  # built lazily
        #: chunks seen under a mask that carry no study metadata (never maskable): counted, reported
        self.unmaskable: dict[str, int] = {}
        self.collection_name = collection

    def index_hash(self) -> str:
        """Identity of this retriever's chunks (``index_hash`` of its chunks file)."""
        return index_hash(self._chunks_path)

    # ---------------------------------------------------------------- dense
    def _embed(self, text: str) -> list[float]:
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured (env var or app/backend/.env) — "
                "the dense retriever needs it to embed the query."
            )
        resp = self._session.post(
            EMBED_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": EMBED_MODEL, "input": [text]},
            timeout=60,
        )
        if resp.status_code == 401:
            raise RuntimeError(
                "OpenAI rejected the API key (401). Check OPENAI_API_KEY in "
                "app/backend/.env — it may be an old or revoked key."
            )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

    def _dense(self, query: str, n: int, mask: Any = None) -> list[str]:
        where = mask.where_clause() if mask is not None and not mask.is_empty else None
        kw: dict[str, Any] = {"query_embeddings": [self._embed(query)], "n_results": n, "include": []}
        if where:
            kw["where"] = where
        res = self._col.query(**kw)
        return res["ids"][0]

    # --------------------------------------------------------------- lexical
    def _ensure_bm25(self):
        if self._bm25 is None:
            from rank_bm25 import BM25Okapi

            self._tokenized = [c["text"].lower().split() for c in self._chunks]
            self._bm25 = BM25Okapi(self._tokenized)

    def _lexical(self, query: str, n: int, mask: Any = None) -> list[str]:
        self._ensure_bm25()
        scores = self._bm25.get_scores(query.lower().split())
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        out: list[str] = []
        for i in order:
            if scores[i] <= 0 or len(out) >= n:
                break
            if mask is not None and self._masked(self._chunks[i], mask):
                continue
            out.append(self._chunks[i]["chunk_id"])
        return out

    # ----------------------------------------------------------------- mask
    def _masked(self, chunk: dict[str, Any], mask: Any) -> bool:
        """True when the mask hides this chunk; counts chunks that cannot be masked at all."""
        if mask is None or mask.is_empty:
            return False
        if not mask.chunk_is_maskable(chunk):
            self.unmaskable[chunk["chunk_id"]] = self.unmaskable.get(chunk["chunk_id"], 0) + 1
            return False
        return bool(mask.blocks_chunk(chunk))

    # ----------------------------------------------------------------- fuse
    @staticmethod
    def _rrf(rank_lists: list[list[str]]) -> list[str]:
        scores: dict[str, float] = {}
        for ranks in rank_lists:
            for r, cid in enumerate(ranks):
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + r + 1)
        return sorted(scores, key=lambda c: -scores[c])

    # ------------------------------------------------------------------ API
    def retrieve(self, query: str, k: int = 8, mask: Any = None, dense: bool = True) -> list[dict[str, Any]]:
        """Hybrid retrieval; ``mask`` hides held-out studies (E4); ``dense=False`` is lexical only
        (fixture tests without an embedding key)."""
        masked = mask is not None and not mask.is_empty
        n = 2 * CANDIDATES if masked else CANDIDATES
        # without a mask the calls are byte-identical to before E4 (stubs with two arguments keep working)
        lists = [self._lexical(query, n, mask) if masked else self._lexical(query, n)]
        if dense:
            lists.insert(0, self._dense(query, n, mask) if masked else self._dense(query, n))
        fused = self._rrf(lists)
        out = []
        for cid in fused:
            if len(out) >= k:
                break
            c = self._by_id.get(cid)
            if not c or (mask is not None and self._masked(c, mask)):
                continue
            # tier tag on every hit (E2); Tier 1 chunks carry none on disk
            out.append(c if c.get("tier") else {**c, "tier": "evidence"})
        return out

    def retrieve_for_recommendation(self, recommendation: dict[str, Any],
                                    k: int = 8, per_practice: bool = True,
                                    mask: Any = None) -> list[dict[str, Any]]:
        """Retrieve evidence for the ranked practices in a recommendation.

        per_practice=True runs one query per recommended practice (deduped),
        so every ranked practice gets grounding, not just the top one.
        """
        practices = [r.get("practice") for r in recommendation.get("recommendations") or []]
        practices = [p for p in practices if p] or [None]
        if not per_practice:
            practices = practices[:1]
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        each = max(2, k // len(practices))
        for p in practices:
            hits = self.retrieve(build_query_text(recommendation, practice=p), k=each, mask=mask) if mask is not None \
                else self.retrieve(build_query_text(recommendation, practice=p), k=each)
            for c in hits:
                if c["chunk_id"] not in seen:
                    seen.add(c["chunk_id"])
                    out.append({**c, "for_practice": p})
        return out[:k]


class TieredRetriever:
    """Several tier retrievers behind one interface, fused by reciprocal-rank fusion.

    Each tier keeps its own collection and BM25 (the corpora are never mixed in
    one index); this class only fuses the per-tier ranked lists with the same
    RRF constant the tiers use internally, so a guideline page competes with a
    Tier 2 passage on rank, not on raw score. Hits keep their ``tier`` tag.
    """

    def __init__(self, retrievers: list[Any], per_tier: int = CANDIDATES) -> None:
        if not retrievers:
            raise ValueError("TieredRetriever needs at least one retriever")
        self.retrievers = list(retrievers)
        self.per_tier = per_tier

    def retrieve(self, query: str, k: int = 8, mask: Any = None) -> list[dict[str, Any]]:
        lists: list[list[str]] = []
        by_id: dict[str, dict[str, Any]] = {}
        for r in self.retrievers:
            n = max(k, min(self.per_tier, 3 * k))
            hits = r.retrieve(query, k=n, mask=mask) if mask is not None else r.retrieve(query, k=n)
            lists.append([h["chunk_id"] for h in hits])
            for h in hits:
                by_id.setdefault(h["chunk_id"], h)
        return [by_id[cid] for cid in RagRetriever._rrf(lists)[:k]]

    @property
    def unmaskable(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.retrievers:
            for cid, n in getattr(r, "unmaskable", {}).items():
                out[cid] = out.get(cid, 0) + n
        return out

    # same per-practice loop as a single tier (it only calls self.retrieve)
    retrieve_for_recommendation = RagRetriever.retrieve_for_recommendation


def _env_flag(name: str, default: bool = True) -> bool:
    """Boolean setting from the environment, else app/backend/.env, else ``default``."""
    value = os.environ.get(name, "").strip()
    if not value:
        env_path = Path(__file__).resolve().parents[1] / "app" / "backend" / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith(f"{name}="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not value:
        return default
    return value.lower() not in ("0", "false", "no", "off")


def guidelines_enabled() -> bool:
    """``RAG_GUIDELINES_ENABLED`` (default true)."""
    return _env_flag("RAG_GUIDELINES_ENABLED", True)


@lru_cache
def default_retriever() -> RagRetriever:
    """Retriever wired to the standard locations (RAG_INDEX_DIR honored)."""
    root = Path(__file__).resolve().parent
    return RagRetriever(index_dir=_find_index_dir(root / "index" / "store"),
                        chunks_path=root / "corpus" / "chunks.jsonl")


@lru_cache
def default_guidance_retriever() -> RagRetriever:
    """Tier-2 guidance retriever at the repo's standard locations.

    Raises if the guidance collection/chunks are not built yet — callers that
    want graceful degradation (explain_service) catch and no-op.
    """
    root = Path(__file__).resolve().parent
    return RagRetriever(index_dir=_find_index_dir(root / "index" / "store"),
                        chunks_path=root / "corpus" / "guidance" / "chunks.jsonl",
                        collection=GUIDANCE_COLLECTION)


@lru_cache
def default_guidelines_retriever() -> RagRetriever:
    """Tier 2b guidelines retriever at the repo's standard locations (raises if not built)."""
    root = Path(__file__).resolve().parent
    return RagRetriever(index_dir=_find_index_dir(root / "index" / "store"),
                        chunks_path=root / "corpus" / "guidelines" / "chunks.jsonl",
                        collection=GUIDELINES_COLLECTION)


def default_documented_retriever() -> Any:
    """Tier 2 guidance plus, when enabled and built, Tier 2b guidelines (tiered)."""
    tiers: list[Any] = [default_guidance_retriever()]
    if guidelines_enabled():
        try:
            tiers.append(default_guidelines_retriever())
        except Exception:  # not built: Tier 2 alone, as before
            pass
    return tiers[0] if len(tiers) == 1 else TieredRetriever(tiers)


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "soil bunds effect on soil loss Ethiopia Moist Dega slope"
    for c in default_retriever().retrieve(q, k=5):
        print(f"- [{c['era_code']}] {c.get('title','')[:70]} ({c.get('year')})")
        print(f"    {c['text'][:180]}...")
