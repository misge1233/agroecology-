"""Embed the corpus chunks and build the persistent vector index (Chroma).

Input : corpus/chunks.jsonl (from parse_and_chunk.py)
Output: a persistent Chroma collection ("era_corpus") under --index, with
        every chunk's text, embedding, and metadata (era_code, doi, title,
        year, journal, source).

Embeddings: OpenAI text-embedding-3-small via the REST API. The key is read
from OPENAI_API_KEY, or (fallback) from app/backend/.env at the repo root —
so one key configuration serves both the app and the indexer.

Resumable: chunks already present in the collection are skipped, so an
interrupted run continues where it left off.

--rebuild drops the collection first and re-embeds everything. REQUIRED after
the corpus changes (e.g. fetch_papers.py --retry-missing followed by
parse_and_chunk.py): chunk ids are reassigned per study, so a study upgraded
from abstract-only to full text reuses id <code>_000 with different text —
resumable mode would silently keep the stale embedding.

Two-tier corpora (P5a): --collection / --chunks parameterize the target, so
the same script builds Tier 1 ("era_corpus", the default) and Tier 2
("guidance_corpus" from corpus/guidance/chunks.jsonl). Building one
collection never touches the other.

Usage:
    python build_index.py --corpus ../corpus --index ../index/store
    python build_index.py --corpus ../corpus --index ../index/store --rebuild
    python build_index.py --chunks ../corpus/guidance/chunks.jsonl \
        --collection guidance_corpus --index ../index/store --rebuild
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import requests

EMBED_MODEL = "text-embedding-3-small"
EMBED_URL = "https://api.openai.com/v1/embeddings"
BATCH = 96
COLLECTION = "era_corpus"
# The embeddings API rejects inputs over 8,192 tokens. A ~380-word chunk is
# normally well under that, but pathological content (unbroken table/URL
# strings, non-Latin scripts where tokens ≈ characters) can blow past it —
# hit on the real GARDIAN corpus (P5a). The EMBEDDING input is clipped to
# this many characters (worst case ≈ 1 token/char, so 7000 < 8192); the
# STORED document text stays complete.
EMBED_MAX_CHARS = 7000


def find_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    # fallback: repo-root app/backend/.env (this file lives at rag/ingest/)
    env_path = Path(__file__).resolve().parents[2] / "app" / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key
    raise SystemExit("ERROR: set OPENAI_API_KEY (env var or app/backend/.env).")


def embed_batch(texts: list[str], api_key: str, session: requests.Session) -> list[list[float]]:
    for attempt in range(5):
        resp = session.post(
            EMBED_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": EMBED_MODEL, "input": texts},
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()["data"]
            return [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]
        if resp.status_code in (429, 500, 502, 503):
            wait = 2 ** attempt
            print(f"[retry] embeddings HTTP {resp.status_code}, waiting {wait}s")
            time.sleep(wait)
            continue
        raise SystemExit(f"Embeddings API error {resp.status_code}: {resp.text[:300]}")
    raise SystemExit("Embeddings API kept failing after retries.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default="../corpus")
    ap.add_argument("--index", default="../index/store")
    ap.add_argument("--chunks", default="",
                    help="chunks JSONL (default: <corpus>/chunks.jsonl)")
    ap.add_argument("--collection", default=COLLECTION,
                    help=f"target Chroma collection (default: {COLLECTION})")
    ap.add_argument("--rebuild", action="store_true",
                    help="drop the collection and re-embed all chunks "
                         "(required after the corpus changed)")
    args = ap.parse_args()

    import chromadb  # deferred: heavy import

    chunks_path = Path(args.chunks) if args.chunks else Path(args.corpus) / "chunks.jsonl"
    chunks = [json.loads(l) for l in chunks_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not chunks:
        raise SystemExit(f"No chunks found in {chunks_path} — run parse_and_chunk.py first.")

    client = chromadb.PersistentClient(path=str(Path(args.index)))
    if args.rebuild:
        try:
            client.delete_collection(args.collection)
            print(f"--rebuild: dropped existing collection '{args.collection}'.")
        except Exception:
            pass  # no existing collection — nothing to drop
    col = client.get_or_create_collection(args.collection, metadata={"hnsw:space": "cosine"})

    existing: set[str] = set()
    if col.count():
        got = col.get(include=[])  # ids only
        existing = set(got["ids"])
    todo = [c for c in chunks if c["chunk_id"] not in existing]
    print(f"{len(chunks)} chunks total, {len(existing)} already indexed, {len(todo)} to embed.")

    api_key = find_api_key()
    session = requests.Session()
    done = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        vecs = embed_batch(
            [c["text"][:EMBED_MAX_CHARS] for c in batch], api_key, session
        )
        col.add(
            ids=[c["chunk_id"] for c in batch],
            embeddings=vecs,
            documents=[c["text"] for c in batch],
            metadatas=[{
                "era_code": c.get("era_code") or "",   # "" for Tier-2 guidance
                "tier": c.get("tier") or "evidence",
                "doi": c.get("doi") or "",
                "title": c.get("title") or "",
                "year": int(c["year"]) if c.get("year") else 0,
                "journal": c.get("journal") or "",
                "url": c.get("url") or "",
                "source": c["source"],
            } for c in batch],
        )
        done += len(batch)
        print(f"  indexed {done}/{len(todo)}")

    print(f"Done. Collection '{args.collection}' now holds {col.count()} chunks at {args.index}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
