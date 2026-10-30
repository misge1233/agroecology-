#!/usr/bin/env python3
"""prune_collection.py — remove low-quality chunks from a Chroma collection (P9).

Scores every chunk of ``--chunks`` with ``quality.chunk_quality`` and deletes
the ids below ``--min-quality`` from the collection in ``--index``; the
chunks file is rewritten without them (a ``.bak`` copy is kept). No
re-embedding happens — surviving rows are untouched.

Safety, as in ``index_tools.py``: a store is opened only if it already holds
``chroma.sqlite3`` (never create one by accident); the collection must exist;
``--dry-run`` (default) only prints the funnel; ``--apply`` performs the
deletion. The Tier-1 collection name is refused outright — ``era_corpus`` is
frozen and must never be pruned.

    python rag/ingest/prune_collection.py --index <store> --chunks rag/corpus/guidance/chunks.jsonl \
        --collection guidance_corpus --min-quality 0.55            # dry run: funnel only
    python rag/ingest/prune_collection.py ... --apply                 # delete + rewrite
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

try:
    from rag.ingest.quality import MIN_QUALITY, chunk_quality
except ImportError:  # run as a script from rag/ingest
    from quality import MIN_QUALITY, chunk_quality

FROZEN_COLLECTIONS = frozenset({"era_corpus"})
BATCH = 500


def funnel(chunks: list[dict], min_quality: float) -> tuple[list[str], Counter]:
    """Ids to remove and a flag histogram."""
    remove: list[str] = []
    flags: Counter = Counter()
    for c in chunks:
        q = chunk_quality(c.get("text") or "")
        if q["score"] < min_quality:
            remove.append(c["chunk_id"])
            for f in q["flags"]:
                flags[f] += 1
    return remove, flags


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", required=True, help="existing Chroma store directory")
    ap.add_argument("--chunks", required=True, help="chunks.jsonl of the collection")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--min-quality", type=float, default=MIN_QUALITY)
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    args = ap.parse_args(argv)

    if args.collection in FROZEN_COLLECTIONS:
        sys.exit(f"ERROR: '{args.collection}' is the frozen Tier-1 corpus — refusing to prune it.")
    index = Path(args.index)
    if not (index / "chroma.sqlite3").exists():
        sys.exit(f"ERROR: {index} is not an existing Chroma store (no chroma.sqlite3).")
    chunks_path = Path(args.chunks)
    chunks = [json.loads(l) for l in chunks_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    remove, flags = funnel(chunks, args.min_quality)
    keep = [c for c in chunks if c["chunk_id"] not in set(remove)]
    print(f"chunks: {len(chunks)} | below {args.min_quality}: {len(remove)} "
          f"({100 * len(remove) / max(1, len(chunks)):.1f}%) | keep: {len(keep)}")
    print("flags among removed:", dict(flags.most_common()))
    if not args.apply:
        print("dry run — pass --apply to delete from the collection and rewrite the chunks file.")
        return 0

    import chromadb  # deferred

    client = chromadb.PersistentClient(path=str(index))
    try:
        col = client.get_collection(args.collection)
    except Exception as exc:
        sys.exit(f"ERROR: collection '{args.collection}' not found in {index} ({exc}).")
    before = col.count()
    for i in range(0, len(remove), BATCH):
        col.delete(ids=remove[i : i + BATCH])
    after = col.count()
    backup = chunks_path.with_suffix(chunks_path.suffix + ".bak")
    shutil.copyfile(chunks_path, backup)
    with chunks_path.open("w", encoding="utf-8") as out:
        for c in keep:
            out.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"collection '{args.collection}': {before} -> {after} rows; chunks file rewritten "
          f"({len(keep)} rows), backup at {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
