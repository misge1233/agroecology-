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

Usage (library):
    from rag.retrieve import RagRetriever
    r = RagRetriever(index_dir=".../rag/index/store", chunks_path=".../rag/corpus/chunks.jsonl")
    hits = r.retrieve_for_recommendation(recommendation_json, k=8)
"""
from __future__ import annotations

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


def build_query_text(recommendation: dict[str, Any], practice: str | None = None) -> str:
    """Compose the retrieval query from the engine's recommendation JSON."""
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
        *INDICATOR_SYNONYMS.get(indicator, ()),
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


class RagRetriever:
    def __init__(self, index_dir: str | Path, chunks_path: str | Path,
                 api_key: str | None = None, collection: str = COLLECTION):
        import chromadb  # deferred heavy import

        self._client = chromadb.PersistentClient(path=str(index_dir))
        self._col = self._client.get_collection(collection)
        self._chunks = [
            json.loads(l)
            for l in Path(chunks_path).read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        self._by_id = {c["chunk_id"]: c for c in self._chunks}
        self._api_key = api_key or _find_api_key()
        self._session = requests.Session()
        self._bm25 = None  # built lazily

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

    def _dense(self, query: str, n: int) -> list[str]:
        res = self._col.query(query_embeddings=[self._embed(query)], n_results=n, include=[])
        return res["ids"][0]

    # --------------------------------------------------------------- lexical
    def _ensure_bm25(self):
        if self._bm25 is None:
            from rank_bm25 import BM25Okapi

            self._tokenized = [c["text"].lower().split() for c in self._chunks]
            self._bm25 = BM25Okapi(self._tokenized)

    def _lexical(self, query: str, n: int) -> list[str]:
        self._ensure_bm25()
        scores = self._bm25.get_scores(query.lower().split())
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:n]
        return [self._chunks[i]["chunk_id"] for i in order if scores[i] > 0]

    # ----------------------------------------------------------------- fuse
    @staticmethod
    def _rrf(rank_lists: list[list[str]]) -> list[str]:
        scores: dict[str, float] = {}
        for ranks in rank_lists:
            for r, cid in enumerate(ranks):
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + r + 1)
        return sorted(scores, key=lambda c: -scores[c])

    # ------------------------------------------------------------------ API
    def retrieve(self, query: str, k: int = 8) -> list[dict[str, Any]]:
        fused = self._rrf([self._dense(query, CANDIDATES), self._lexical(query, CANDIDATES)])
        out = []
        for cid in fused[:k]:
            c = self._by_id.get(cid)
            if c:
                out.append(c)
        return out

    def retrieve_for_recommendation(self, recommendation: dict[str, Any],
                                    k: int = 8, per_practice: bool = True) -> list[dict[str, Any]]:
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
            for c in self.retrieve(build_query_text(recommendation, practice=p), k=each):
                if c["chunk_id"] not in seen:
                    seen.add(c["chunk_id"])
                    out.append({**c, "for_practice": p})
        return out[:k]


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


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "soil bunds effect on soil loss Ethiopia Moist Dega slope"
    for c in default_retriever().retrieve(q, k=5):
        print(f"- [{c['era_code']}] {c.get('title','')[:70]} ({c.get('year')})")
        print(f"    {c['text'][:180]}...")
