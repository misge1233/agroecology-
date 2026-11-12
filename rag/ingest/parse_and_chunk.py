"""Parse the acquired corpus into retrieval-ready chunks.

Input : corpus/manifest.jsonl (from fetch_papers.py) + corpus/pdfs/*.pdf
        + corpus/xml/*.xml (Europe PMC full-text JATS XML)
Output: corpus/chunks.jsonl — one JSON object per chunk:
        {chunk_id, era_code, doi, title, year, journal, source, text,
         corpus_source, study_ids}
        source = "pdf" | "xml" (full text) | "abstract" (metadata-only studies)
        corpus_source = "ERA" | "HAB" (the manifest row's source, E4)
        study_ids = every evidence-store study id the chunk belongs to (E4 Part 3:
        ``ERA_<era_code>`` and its sub-studies, the Habtamu study id, and every
        store study of any source that carries the chunk's DOI), so a held-out
        study can be masked through any of its identifiers

NOTE: this script rewrites chunks.jsonl from scratch on every run, so chunk
ids are reassigned. After the corpus changes (e.g. fetch_papers.py
--retry-missing upgraded studies from abstract-only to full text), rebuild
the vector index with `build_index.py --rebuild` — resumable indexing would
keep stale embeddings for reused chunk ids.

Chunking: ~CHUNK_WORDS words per chunk with OVERLAP_WORDS overlap, split on
paragraph boundaries where possible. The reference section is trimmed. Every
chunk carries `era_code` — the join key back to the training rows behind a
recommendation (the linkage the whole RAG design is built on).

Usage:
    python parse_and_chunk.py --corpus ../corpus [--store ../../data/evidence/evidence_rows.parquet]
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

CHUNK_WORDS = 380      # ~512 tokens
OVERLAP_WORDS = 60

_REFS_RE = re.compile(
    r"\n\s*(references|literature cited|bibliography)\s*\n", re.IGNORECASE
)
_WS_RE = re.compile(r"[ \t]+")
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\n(\w)")
_XML_DROP_RE = re.compile(
    r"<(ref-list|back|xref|table-wrap|fig|disp-formula|inline-formula)\b.*?</\1>",
    re.DOTALL,
)
_XML_BLOCK_RE = re.compile(r"</(p|sec|title|abstract)>", re.IGNORECASE)
_XML_CONTENT_RE = re.compile(r"<(abstract|body)\b.*?</\1>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader  # deferred: chunk_guidance.py imports this
    # module for chunk_text() alone and must not require the PDF stack

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = "\n".join(pages)
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)          # de-hyphenate line breaks
    text = _WS_RE.sub(" ", text)
    # trim references (keep everything before the LAST references heading)
    m = list(_REFS_RE.finditer(text))
    if m:
        text = text[: m[-1].start()]
    return text.strip()


def extract_xml_text(path: Path) -> str:
    """Full text from a JATS XML file (Europe PMC) via simple tag stripping.

    Only <abstract> and <body> content is kept (front matter is journal/
    article metadata noise); references, tables, figures, formulas, and
    citation cross-refs are dropped; block-level closers become paragraph
    breaks so chunk_text() still sees paragraph boundaries.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    parts = [m.group(0) for m in _XML_CONTENT_RE.finditer(raw)]
    if parts:
        raw = "\n\n".join(parts)
    raw = _XML_DROP_RE.sub(" ", raw)
    raw = _XML_BLOCK_RE.sub("\n\n", raw)
    text = html.unescape(_TAG_RE.sub(" ", raw))
    text = _WS_RE.sub(" ", text)
    m = list(_REFS_RE.finditer(text))
    if m:
        text = text[: m[-1].start()]
    return text.strip()


def chunk_text(text: str) -> list[str]:
    """Greedy paragraph packing to ~CHUNK_WORDS, word-window fallback."""
    paras = [p.strip() for p in re.split(r"\n{2,}|\n(?=[A-Z0-9][^a-z]{0,3}\s)", text) if p.strip()]
    if not paras:
        paras = [text]
    chunks: list[list[str]] = []
    cur: list[str] = []
    for p in paras:
        words = p.split()
        if len(words) > CHUNK_WORDS:                    # oversized para → window it
            if cur:
                chunks.append(cur)
                cur = []
            step = CHUNK_WORDS - OVERLAP_WORDS
            for i in range(0, len(words), step):
                chunks.append(words[i : i + CHUNK_WORDS])
                if i + CHUNK_WORDS >= len(words):
                    break
            continue
        if len(cur) + len(words) > CHUNK_WORDS and cur:
            chunks.append(cur)
            cur = cur[-OVERLAP_WORDS:]                  # carry overlap forward
        cur.extend(words)
    if len(cur) > OVERLAP_WORDS or not chunks:
        chunks.append(cur)
    return [" ".join(c) for c in chunks if c]


def study_id_index(store_path: Path | None) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """``(era_code -> store study ids, normalised doi -> store study ids)`` from the evidence store.

    ERA store ids are ``ERA_<era_code>`` plus sub-studies ``ERA_<era_code>.<n>``; Habtamu ids
    equal their corpus code. Empty when the store is absent (the chunks then carry only
    the ids derivable from the manifest).
    """
    by_code: dict[str, set[str]] = {}
    by_doi: dict[str, set[str]] = {}
    if store_path and Path(store_path).exists():
        import pandas as pd

        df = pd.read_parquet(store_path, columns=["study_id", "doi", "source"])
        for sid, doi, source in zip(df["study_id"], df["doi"], df["source"]):
            sid = str(sid)
            if source == "ERA" and sid.startswith("ERA_"):
                by_code.setdefault(sid[4:].split(".")[0], set()).add(sid)
            elif source == "HAB":
                by_code.setdefault(sid, set()).add(sid)
            if isinstance(doi, str) and doi.strip():
                by_doi.setdefault(doi.strip().lower(), set()).add(sid)
    return ({k: sorted(v) for k, v in by_code.items()}, {k: sorted(v) for k, v in by_doi.items()})


def study_ids_for(rec: dict, by_code: dict[str, list[str]], by_doi: dict[str, list[str]]) -> list[str]:
    """Every store study id a manifest record belongs to (sorted, never empty)."""
    code = rec["era_code"]
    ids = set(by_code.get(code, []))
    ids.add(code if str(rec.get("source", "ERA")) == "HAB" else f"ERA_{code}")
    doi = rec.get("doi")
    if isinstance(doi, str) and doi.strip() and doi != "None":
        ids |= set(by_doi.get(doi.strip().lower(), []))
    return sorted(ids)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default="../corpus", help="corpus dir (manifest.jsonl, pdfs/)")
    ap.add_argument("--min-words", type=int, default=40, help="drop chunks shorter than this")
    ap.add_argument("--store", default=str(Path(__file__).resolve().parents[2] / "data" / "evidence" / "evidence_rows.parquet"),
                    help="evidence store (study ids per chunk, E4); skipped when absent")
    args = ap.parse_args()

    corpus = Path(args.corpus)
    manifest = [
        json.loads(l)
        for l in (corpus / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    by_code, by_doi = study_id_index(Path(args.store) if args.store else None)
    out_path = corpus / "chunks.jsonl"
    n_chunks = n_pdf = n_xml = n_abs = n_same_paper = 0
    seen_doi: dict[str, str] = {}  # one paper is chunked once: later manifest rows of the same DOI are skipped
    with open(out_path, "w", encoding="utf-8") as out:
        for rec in manifest:
            code = rec["era_code"]
            doi = rec.get("doi")
            doi_key = doi.strip().lower() if isinstance(doi, str) and doi != "None" and doi.strip() else None
            if doi_key and doi_key in seen_doi:
                # the Habtamu sheet lists one study per contrast set, so a paper can have ten
                # manifest rows; its chunks carry every study id of the DOI (study_ids), so the
                # repeats add nothing but duplicated text (E4)
                n_same_paper += 1
                continue
            if doi_key:
                seen_doi[doi_key] = code
            meta = {
                "era_code": code,
                "doi": doi if isinstance(doi, str) and doi != "None" and doi.strip() else None,
                "title": rec.get("title"),
                "year": rec.get("year"),
                "journal": rec.get("container") or rec.get("journal"),
                "corpus_source": rec.get("source") or "ERA",
                "study_ids": study_ids_for(rec, by_code, by_doi),
            }
            texts: list[tuple[str, str]] = []          # (source, chunk_text)
            pdf_file = rec.get("pdf_file")
            if pdf_file == "None":
                pdf_file = None
            if pdf_file and (corpus / "pdfs" / pdf_file).exists():
                try:
                    full = extract_pdf_text(corpus / "pdfs" / pdf_file)
                    if len(full.split()) >= args.min_words:
                        texts = [("pdf", c) for c in chunk_text(full)]
                        n_pdf += 1
                except Exception as exc:
                    print(f"[warn] {code}: PDF parse failed ({exc}); falling back to abstract")
            xml_file = rec.get("fulltext_xml")
            if xml_file == "None":
                xml_file = None
            if not texts and xml_file and (corpus / "xml" / xml_file).exists():
                try:
                    full = extract_xml_text(corpus / "xml" / xml_file)
                    if len(full.split()) >= args.min_words:
                        texts = [("xml", c) for c in chunk_text(full)]
                        n_xml += 1
                except Exception as exc:
                    print(f"[warn] {code}: XML parse failed ({exc}); falling back to abstract")
            if not texts and rec.get("abstract"):
                texts = [("abstract", rec["abstract"])]
                n_abs += 1
            for i, (source, text) in enumerate(texts):
                if len(text.split()) < args.min_words and source in ("pdf", "xml"):
                    continue
                out.write(json.dumps({
                    "chunk_id": f"{code}_{i:03d}",
                    **meta,
                    "source": source,
                    "text": text,
                }, ensure_ascii=False) + "\n")
                n_chunks += 1

    print(f"Done: {n_chunks} chunks from {n_pdf + n_xml} full-text "
          f"({n_pdf} PDF + {n_xml} XML) + {n_abs} abstract-only studies "
          f"({n_same_paper} manifest rows skipped as repeats of an already chunked DOI) "
          f"-> {out_path}")
    print("Reminder: chunk ids were reassigned — rebuild the index with "
          "`build_index.py --rebuild` if it already exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
