#!/usr/bin/env python3
"""index_tools.py — maintenance utilities for the Chroma store(s).

Subcommands (run from the repo root, backend venv active):

  list             collections + chunk counts in a store
  copy-collection  copy ONE collection (ids, embeddings, documents, metadatas)
                   from a source store into a destination store — no
                   re-embedding, source opened read-only in spirit (never
                   modified by this tool)
  export-chunks    reconstruct a ``chunks.jsonl`` (the retriever's BM25 input)
                   from a collection, in manifest/document order
  compare          check that a collection is identical in two stores
                   (ids, documents, metadata, embeddings)

Why this exists (reviewer, 23 Oct 2026): the Tier-2 guidance artefacts
(``rag/corpus/guidance/chunks.jsonl`` + the ``guidance_corpus`` collection)
were built on 21 Aug 2026 in a working copy that was later lost; only the
full Chroma store survived (395 MB, both collections). Chroma keeps every
chunk's text and metadata, so the chunks file is recoverable byte-for-byte
except for the diagnostic ``kw_distinct`` field (set to null here; nothing
downstream reads it). Tier 1 (``era_corpus``, P3-evaluated) is never touched:
the guidance collection is transplanted INTO the canonical store.

Safety: a store path is opened only if it already contains ``chroma.sqlite3``
— ``chromadb.PersistentClient`` silently creates an empty store otherwise,
which is exactly how an empty store got created on 23 Oct.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

BATCH = 500
_EMPTY_META = {"era_code": "", "doi": "", "title": "", "journal": "", "url": ""}


# ------------------------------------------------------------------ helpers
def open_store(path: str | Path, *, create: bool = False):
    """Open a Chroma persistent store; refuse to create one by accident."""
    import chromadb  # local import: keep the CLI importable without chromadb

    p = Path(path)
    if not create and not (p / "chroma.sqlite3").exists():
        sys.exit(f"ERROR: {p} is not an existing Chroma store (no chroma.sqlite3) "
                 "— refusing to create an empty one.")
    return chromadb.PersistentClient(path=str(p))


def collection_names(client) -> list[str]:
    return [getattr(c, "name", c) for c in client.list_collections()]


def iter_rows(col, *, with_embeddings: bool) -> Iterator[dict[str, Any]]:
    """Yield {id, document, metadata[, embedding]} for every row, paginated."""
    include = ["documents", "metadatas"] + (["embeddings"] if with_embeddings else [])
    offset = 0
    while True:
        got = col.get(include=include, limit=BATCH, offset=offset)
        ids = got.get("ids") or []
        if not ids:
            return
        docs = got.get("documents") or [None] * len(ids)
        metas = got.get("metadatas") or [None] * len(ids)
        embs = got.get("embeddings") if with_embeddings else None
        for i, cid in enumerate(ids):
            row: dict[str, Any] = {"id": cid, "document": docs[i], "metadata": metas[i] or {}}
            if with_embeddings:
                e = embs[i]
                row["embedding"] = e.tolist() if hasattr(e, "tolist") else list(e)
            yield row
        offset += len(ids)
        if len(ids) < BATCH:
            return


def chunk_pos(chunk_id: str) -> int:
    """``G_<doc_id>_<pos>`` / ``<era_code>_<pos>`` -> pos (int); -1 if absent."""
    tail = chunk_id.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else -1


def chunk_doc(chunk_id: str) -> str:
    head = chunk_id.rsplit("_", 1)[0]
    return head[2:] if head.startswith("G_") else head


# ------------------------------------------------------------------ commands
def cmd_list(args) -> int:
    client = open_store(args.index)
    names = collection_names(client)
    if not names:
        print(f"{args.index}: no collections")
    for n in names:
        print(f"{args.index}: {n} = {client.get_collection(n).count()} chunks")
    return 0


def cmd_copy(args) -> int:
    src = open_store(args.src)
    dst = open_store(args.dst)
    if args.collection not in collection_names(src):
        sys.exit(f"ERROR: collection '{args.collection}' not in {args.src}")
    scol = src.get_collection(args.collection)
    existing = collection_names(dst)
    if args.collection in existing:
        if not args.replace:
            sys.exit(f"ERROR: '{args.collection}' already exists in {args.dst} "
                     f"({dst.get_collection(args.collection).count()} chunks); "
                     "pass --replace to drop and recopy.")
        dst.delete_collection(args.collection)
    dcol = dst.create_collection(args.collection, metadata={"hnsw:space": "cosine"})
    total = scol.count()
    print(f"copying '{args.collection}': {total} chunks {args.src} -> {args.dst}")
    batch: list[dict[str, Any]] = []
    done = 0

    def flush() -> None:
        nonlocal done
        if not batch:
            return
        dcol.add(
            ids=[r["id"] for r in batch],
            embeddings=[r["embedding"] for r in batch],
            documents=[r["document"] for r in batch],
            metadatas=[r["metadata"] for r in batch],
        )
        done += len(batch)
        print(f"  {done}/{total}")
        batch.clear()

    for row in iter_rows(scol, with_embeddings=True):
        batch.append(row)
        if len(batch) >= BATCH:
            flush()
    flush()
    n = dcol.count()
    print(f"done: '{args.collection}' now holds {n} chunks in {args.dst}"
          + ("" if n == total else f"  ** MISMATCH: expected {total} **"))
    return 0 if n == total else 1


def cmd_export(args) -> int:
    client = open_store(args.index)
    if args.collection not in collection_names(client):
        sys.exit(f"ERROR: collection '{args.collection}' not in {args.index}")
    col = client.get_collection(args.collection)
    rows = list(iter_rows(col, with_embeddings=False))
    print(f"read {len(rows)} chunks from '{args.collection}'")

    # document order: manifest order when given, else by document key
    order: dict[str, int] = {}
    if args.manifest:
        for i, line in enumerate(Path(args.manifest).read_text(encoding="utf-8").splitlines()):
            if line.strip():
                rec = json.loads(line)
                key = rec.get("doc_id") or rec.get("era_code")
                if key:
                    order[key] = i
    missing = {chunk_doc(r["id"]) for r in rows} - set(order) if order else set()
    if missing:
        print(f"  note: {len(missing)} document ids not in the manifest — sorted last")
    rows.sort(key=lambda r: (order.get(chunk_doc(r["id"]), 10**9), chunk_doc(r["id"]),
                             chunk_pos(r["id"])))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            m = {**_EMPTY_META, **r["metadata"]}
            rec = {
                "chunk_id": r["id"],
                "era_code": m["era_code"] or None,
                "tier": m.get("tier") or "evidence",
                "doi": m["doi"] or None,
                "title": m["title"] or None,
                "year": int(m["year"]) if m.get("year") else None,
                "journal": m["journal"] or None,
                "url": m["url"] or None,
                "source": m.get("source"),
                "kw_distinct": None,   # diagnostic only; not recoverable, unused downstream
                "text": r["document"],
            }
            if rec["tier"] == "evidence":
                rec.pop("url", None)  # Tier-1 chunks never carried url/kw fields
                rec.pop("kw_distinct", None)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tiers: dict[str, int] = {}
    for r in rows:
        t = r["metadata"].get("tier") or "evidence"
        tiers[t] = tiers.get(t, 0) + 1
    print(f"wrote {len(rows)} chunks -> {out}  (by tier: {tiers})")
    return 0


def cmd_compare(args) -> int:
    a = open_store(args.index_a)
    b = open_store(args.index_b)
    for client, path in ((a, args.index_a), (b, args.index_b)):
        if args.collection not in collection_names(client):
            sys.exit(f"ERROR: collection '{args.collection}' not in {path}")
    ra = {r["id"]: r for r in iter_rows(a.get_collection(args.collection), with_embeddings=True)}
    rb = {r["id"]: r for r in iter_rows(b.get_collection(args.collection), with_embeddings=True)}
    only_a, only_b = set(ra) - set(rb), set(rb) - set(ra)
    common = set(ra) & set(rb)
    doc_diff = sum(1 for i in common if ra[i]["document"] != rb[i]["document"])
    meta_diff = sum(1 for i in common if ra[i]["metadata"] != rb[i]["metadata"])
    max_abs = 0.0
    emb_identical = 0
    for i in common:
        ea, eb = ra[i]["embedding"], rb[i]["embedding"]
        if len(ea) != len(eb):
            max_abs = float("inf")
            continue
        d = max((abs(x - y) for x, y in zip(ea, eb)), default=0.0)
        max_abs = max(max_abs, d)
        if d == 0.0:
            emb_identical += 1
    print(f"collection '{args.collection}': A={len(ra)} B={len(rb)} common={len(common)} "
          f"only_A={len(only_a)} only_B={len(only_b)}")
    print(f"  documents differing: {doc_diff}; metadata differing: {meta_diff}")
    print(f"  embeddings bit-identical: {emb_identical}/{len(common)}; max |diff| = {max_abs:.3e}")
    same_rows = not only_a and not only_b and doc_diff == 0 and meta_diff == 0
    if same_rows and max_abs < 1e-6:
        verdict = "IDENTICAL (embedding differences, if any, are float32 storage round-off)"
    elif same_rows and max_abs < 1e-2:
        verdict = "SAME TEXT, DIFFERENT EMBEDDINGS (re-embedded: rankings may shift marginally)"
    else:
        verdict = "DIFFERENT"
    print("VERDICT:", verdict)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list"); p.add_argument("--index", required=True); p.set_defaults(fn=cmd_list)

    p = sub.add_parser("copy-collection")
    p.add_argument("--src", required=True); p.add_argument("--dst", required=True)
    p.add_argument("--collection", required=True); p.add_argument("--replace", action="store_true")
    p.set_defaults(fn=cmd_copy)

    p = sub.add_parser("export-chunks")
    p.add_argument("--index", required=True); p.add_argument("--collection", required=True)
    p.add_argument("--out", required=True); p.add_argument("--manifest", default=None)
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("compare")
    p.add_argument("--index-a", required=True); p.add_argument("--index-b", required=True)
    p.add_argument("--collection", required=True); p.set_defaults(fn=cmd_compare)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
