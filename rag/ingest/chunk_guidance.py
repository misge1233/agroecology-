"""Chunk the Tier-2 guidance corpus (Phase P5a).

Wraps — never forks — the Tier-1 chunker: the chunking algorithm is imported
from ``parse_and_chunk`` (same ~380-word windows, paragraph packing, overlap),
applied to the GARDIAN documents fetched by ``fetch_gardian.py``.

Chunk-level relevance filter (review decision, 21 Aug 2026): GARDIAN
documents are WHOLE reports/books (median ~14k words, max ~376k — measured
on the real fetch), so chunking them wholesale would produce ~130k chunks
and swamp both the index and the in-memory BM25. Therefore:

1. A chunk is kept only if it mentions at least one practice keyword
   (``FAMILY_KEYWORDS`` — the same vocabulary that admitted the document).
2. Each document contributes at most ``--max-chunks-per-doc`` (default 25)
   chunks — the ones with the most DISTINCT keywords (ties: more total
   keyword hits, then earlier position). Measured necessity: one 376k-word
   crop-genepool book alone otherwise yields ~1,500 keyword-matching chunks.
Both rules are Tier-2 only; Tier-1 chunking is untouched.

Input : corpus/guidance/manifest.jsonl + corpus/guidance/texts/*.txt
Output: corpus/guidance/chunks.jsonl — same chunk schema as Tier 1 PLUS:
        - ``tier: "guidance"`` on every chunk
        - ``era_code: null`` ALWAYS (guidance docs are not ERA studies; the
          Tier-1 linkage is never faked)
        - ``url`` (source link for the UI chips)
        - ``kw_distinct`` (diagnostic: distinct practice keywords in chunk)
        - chunk ids prefixed ``G_`` so the two tiers' id spaces stay
          disjoint; the numeric suffix is the chunk's ORIGINAL position in
          the document (gaps = filtered chunks), so provenance is preserved.

Usage:
    python chunk_guidance.py --corpus ../corpus/guidance
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:  # package import (repo root on path) or sibling-script import
    from rag.ingest.parse_and_chunk import chunk_text
    from rag.ingest.fetch_gardian import FAMILY_KEYWORDS
except ImportError:
    from parse_and_chunk import chunk_text
    from fetch_gardian import FAMILY_KEYWORDS

CHUNK_ID_PREFIX = "G_"
TIER = "guidance"
ALL_KEYWORDS: tuple[str, ...] = tuple(
    kw for kws in FAMILY_KEYWORDS.values() for kw in kws
)
DEFAULT_MAX_CHUNKS_PER_DOC = 25


def keyword_stats(piece: str) -> tuple[int, int]:
    """(distinct practice keywords, total keyword hits) in one chunk."""
    lowered = piece.lower()
    distinct = total = 0
    for kw in ALL_KEYWORDS:
        n = lowered.count(kw)
        if n:
            distinct += 1
            total += n
    return distinct, total


def guidance_chunks(
    rec: dict,
    text: str,
    min_words: int,
    max_per_doc: int = DEFAULT_MAX_CHUNKS_PER_DOC,
) -> list[dict]:
    """Chunk records for one guidance document (pure — testable).

    Keeps only practice-keyword-bearing chunks, at most ``max_per_doc`` per
    document (ranked by distinct keywords, then total hits, then earlier
    position); output is in document order with original position ids.
    """
    candidates: list[tuple[int, int, int, str]] = []  # (pos, distinct, hits, text)
    for i, piece in enumerate(chunk_text(text)):
        if len(piece.split()) < min_words:
            continue
        distinct, hits = keyword_stats(piece)
        if distinct == 0:
            continue  # chunk-level relevance filter
        candidates.append((i, distinct, hits, piece))

    if max_per_doc and len(candidates) > max_per_doc:
        candidates = sorted(
            candidates, key=lambda c: (-c[1], -c[2], c[0])
        )[:max_per_doc]
    candidates.sort(key=lambda c: c[0])  # document order for output

    return [
        {
            "chunk_id": f"{CHUNK_ID_PREFIX}{rec['doc_id']}_{pos:03d}",
            "era_code": None,               # never fake Tier-1 linkage
            "tier": TIER,
            "doi": rec.get("doi"),
            "title": rec.get("title"),
            "year": rec.get("year"),
            "journal": None,                # guidance docs are not journal papers
            "url": rec.get("url"),
            "source": "gardian",
            "kw_distinct": distinct,
            "text": piece,
        }
        for pos, distinct, hits, piece in candidates
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", default="../corpus/guidance",
                    help="guidance corpus dir (manifest.jsonl, texts/)")
    ap.add_argument("--min-words", type=int, default=40,
                    help="drop chunks shorter than this (same as Tier 1)")
    ap.add_argument("--max-chunks-per-doc", type=int,
                    default=DEFAULT_MAX_CHUNKS_PER_DOC,
                    help="cap per document, best keyword chunks kept "
                         "(0 = uncapped)")
    args = ap.parse_args()

    corpus = Path(args.corpus)
    manifest = [
        json.loads(l)
        for l in (corpus / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    out_path = corpus / "chunks.jsonl"
    n_chunks = n_docs = n_missing = n_docs_empty = n_docs_capped = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for rec in manifest:
            text_path = corpus / rec["text_file"]
            if not text_path.exists():
                print(f"[warn] {rec['doc_id']}: text file missing — skipped")
                n_missing += 1
                continue
            text = text_path.read_text(encoding="utf-8")
            chunks = guidance_chunks(
                rec, text, args.min_words, args.max_chunks_per_doc
            )
            if args.max_chunks_per_doc and len(chunks) == args.max_chunks_per_doc:
                n_docs_capped += 1
            for chunk in chunks:
                out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            n_chunks += len(chunks)
            n_docs += 1 if chunks else 0
            n_docs_empty += 0 if chunks else 1

    print(f"Done: {n_chunks} guidance chunks from {n_docs} documents "
          f"({n_docs_empty} docs with no keyword-bearing chunk, "
          f"{n_docs_capped} docs hit the {args.max_chunks_per_doc}-chunk cap, "
          f"{n_missing} missing text files) -> {out_path}")
    print("Next: build_index.py --chunks corpus/guidance/chunks.jsonl "
          "--collection guidance_corpus --rebuild")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
