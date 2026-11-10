"""Ingest the government guidelines (Tier 2b) into page texts and chunks (Phase E2, Part C).

Input : ``rag/corpus/guidelines/manifest.csv`` + ``pdfs/`` (62 documents).
Output: ``rag/corpus/guidelines/texts/<doc_id>/page_<n>.txt`` (git-ignored),
        ``texts/<doc_id>/meta.json``, ``rag/corpus/guidelines/chunks.jsonl``
        (git-ignored mirror of the index) and ``ingest_report.md`` (in git).

1. **Text**: ``pdftotext -layout -enc UTF-8`` (xpdf/poppler), split on form
   feeds into pages; characters per page measured.
2. **OCR**: a page under 200 characters in a document where most pages are rich
   is an image page; a document whose pages are mostly under 200 characters is
   OCR'd whole. Pages are rendered with pypdfium2 (300 dpi) and read by
   Tesseract (``eng``, plus ``amh`` when the pack is installed). Without
   Tesseract the pages are listed as ``ocr_pending`` and keep their extracted
   text; re-running after installing Tesseract fills them (the step is
   resumable per document).
3. **Chunks**: the Tier 1/2 chunker (``parse_and_chunk.chunk_text``, wrapped via
   ``chunk_guidance``) applied **page by page**, so every chunk has a page
   number; the Tier 2 quality gate (``quality.chunk_quality``) is applied; the
   Tier 2 keyword filter and per-document cap are not (every guideline is a
   curated, on-topic document). Chunk ids ``GL_<doc_id>_p<page>_<i>``,
   ``tier = "guidelines"``, ``era_code = None``, plus ``doc_id, title,
   publisher, year, language, theme, page, citation``.

Usage (repo root)::

    python -m rag.ingest.ingest_guidelines [--doc DOC_ID] [--no-ocr] [--chunk-only]
    python rag/ingest/build_index.py --chunks rag/corpus/guidelines/chunks.jsonl --collection guidelines --rebuild

Tesseract on Windows: ``winget install UB-Mannheim.TesseractOCR`` (tick the Amharic
language data in the installer), then re-run this script.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # package import (repo root on path) or sibling-script import
    from rag.ingest.chunk_guidance import chunk_text
    from rag.ingest.quality import MIN_QUALITY, chunk_quality
except ImportError:  # pragma: no cover
    from chunk_guidance import chunk_text
    from quality import MIN_QUALITY, chunk_quality

ROOT = Path(__file__).resolve().parents[1]
GUIDE_DIR = ROOT / "corpus" / "guidelines"
MANIFEST = GUIDE_DIR / "manifest.csv"
TEXTS = GUIDE_DIR / "texts"
CHUNKS = GUIDE_DIR / "chunks.jsonl"
REPORT = GUIDE_DIR / "ingest_report.md"
TIER = "guidelines"
CHUNK_PREFIX = "GL_"
IMAGE_PAGE_CHARS = 200
MIN_WORDS = 40
OCR_DPI = 300
_ETHIOPIC = re.compile(r"[\u1200-\u137F]")
_LATIN = re.compile(r"[A-Za-z]")
KNOWN_TOOLS = {
    "pdftotext": [r"C:\Program Files\Git\mingw64\bin\pdftotext.exe", "/usr/bin/pdftotext", "/mingw64/bin/pdftotext"],
    "tesseract": [r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                  "/usr/bin/tesseract"],
}
PUBLISHER_SHORT = {
    "ministry of agriculture": "MoA", "ministry of agriculture and rural development": "MoARD",
    "ministry of water and energy": "MoWE", "giz": "GIZ", "cifor-icraf": "CIFOR-ICRAF", "world agroforestry": "ICRAF",
}


def find_tool(name: str) -> str | None:
    """Executable path of ``name`` (PATH first, then the usual install locations)."""
    hit = shutil.which(name)
    if hit:
        return hit
    for p in KNOWN_TOOLS.get(name, []):
        if Path(p).exists():
            return p
    return None


def tesseract_languages(tess: str) -> set[str]:
    """Installed Tesseract language packs."""
    try:
        out = subprocess.run([tess, "--list-langs"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {ln.strip() for ln in out.splitlines()[1:] if ln.strip()}


def read_manifest(path: Path = MANIFEST) -> list[dict[str, str]]:
    """Manifest rows (one per document)."""
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def short_publisher(publisher: str) -> str:
    """``Ministry of Agriculture; WLRC`` -> ``MoA`` (first publisher, known abbreviations)."""
    first = re.split(r";|,|\s+with\s+|\s+and\s+", publisher or "")[0].strip()
    if re.match(r"ministry of agriculture\b(?! and rural)", first, flags=re.I):
        return "MoA"  # "Ministry of Agriculture of Ethiopia", "... PASIDP II", "... (with INBAR)"
    return PUBLISHER_SHORT.get(first.lower(), first)


def citation_label(rec: dict[str, Any], page: int | None) -> str:
    """``MoA 2016, Guidelines for Development Agents on SWC, p. 34``."""
    title = re.sub(r"\s*\([^)]*\)\s*$", "", rec.get("title") or "").strip()
    head = ", ".join(x for x in (f"{short_publisher(rec.get('publisher', ''))} {rec.get('year', '')}".strip(), title) if x)
    return f"{head}, p. {page}" if page else head


def detect_language(text: str) -> str:
    """``am`` when Ethiopic script dominates the letters, else ``en``."""
    eth, lat = len(_ETHIOPIC.findall(text)), len(_LATIN.findall(text))
    return "am" if eth > lat else "en"


def extract_pages(pdf: Path, pdftotext: str) -> list[str]:
    """Page texts via ``pdftotext -layout`` (form-feed separated)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.txt"
        subprocess.run([pdftotext, "-layout", "-enc", "UTF-8", str(pdf), str(out)], check=True,
                       capture_output=True, timeout=600)
        raw = out.read_text(encoding="utf-8", errors="replace")
    pages = raw.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return pages


def image_pages(chars: list[int], threshold: int = IMAGE_PAGE_CHARS) -> tuple[list[int], bool]:
    """``(1-based pages to OCR, whole_document)`` by the brief's rule."""
    if not chars:
        return [], False
    low = [i + 1 for i, c in enumerate(chars) if c < threshold]
    whole = len(low) > len(chars) / 2
    return (list(range(1, len(chars) + 1)) if whole else low), whole


def ocr_page(pdf: Path, page: int, tess: str, langs: str) -> str:
    """Render one page (pypdfium2) and OCR it with Tesseract."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    try:
        img = doc[page - 1].render(scale=OCR_DPI / 72).to_pil()
    finally:
        doc.close()
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "p.png"
        img.save(png)
        r = subprocess.run([tess, str(png), "stdout", "-l", langs, "--psm", "3"], capture_output=True, timeout=300)
    return r.stdout.decode("utf-8", errors="replace")


@dataclass
class DocResult:
    """Per-document ingest record (written to ``meta.json`` and the report)."""

    doc_id: str
    pages: int = 0
    chars: int = 0
    ocr_pages: list[int] = field(default_factory=list)
    ocr_pending: list[int] = field(default_factory=list)
    whole_doc_ocr: bool = False
    language: str = "en"
    manifest_language: str = "en"
    error: str | None = None


def ingest_doc(rec: dict[str, str], pdftotext: str, tess: str | None, tess_langs: set[str],
               do_ocr: bool = True) -> DocResult:
    """Extract (and OCR where needed) one document into ``texts/<doc_id>/``."""
    res = DocResult(rec["doc_id"], manifest_language=rec.get("language", "en"))
    pdf = GUIDE_DIR / "pdfs" / rec["file_name"]
    out_dir = TEXTS / rec["doc_id"]
    meta_path = out_dir / "meta.json"
    if meta_path.exists():
        prev = json.loads(meta_path.read_text(encoding="utf-8"))
        if not prev.get("ocr_pending") or not (do_ocr and tess):
            return DocResult(**{k: prev.get(k) for k in DocResult.__dataclass_fields__ if k in prev})
    try:
        pages = extract_pages(pdf, pdftotext)
    except Exception as exc:  # noqa: BLE001 - recorded in the report, never fatal
        res.error = f"pdftotext failed: {exc}"[:200]
        return res
    chars = [len(p.strip()) for p in pages]
    todo, res.whole_doc_ocr = image_pages(chars)
    langs = "+".join(l for l in ("eng", "amh") if l in tess_langs) or "eng"
    for pg in todo:
        if do_ocr and tess:
            try:
                text = ocr_page(pdf, pg, tess, langs)
                if len(text.strip()) > chars[pg - 1]:
                    pages[pg - 1] = text
                res.ocr_pages.append(pg)
            except Exception as exc:  # noqa: BLE001
                res.ocr_pending.append(pg)
                res.error = f"ocr failed on page {pg}: {exc}"[:200]
        else:
            res.ocr_pending.append(pg)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(pages, start=1):
        (out_dir / f"page_{i}.txt").write_text(p, encoding="utf-8")
    res.pages, res.chars = len(pages), sum(len(p.strip()) for p in pages)
    res.language = detect_language(" ".join(pages))
    meta_path.write_text(json.dumps(res.__dict__, indent=1), encoding="utf-8")
    return res


def page_texts(doc_id: str) -> list[tuple[int, str]]:
    """``(page, text)`` pairs of an ingested document, in page order."""
    d = TEXTS / doc_id
    pages = []
    for p in d.glob("page_*.txt"):
        m = re.match(r"page_(\d+)\.txt$", p.name)
        if m:
            pages.append((int(m.group(1)), p.read_text(encoding="utf-8")))
    return sorted(pages)


def guideline_chunks(rec: dict[str, str], pages: list[tuple[int, str]], language: str,
                     min_words: int = MIN_WORDS, min_quality: float = MIN_QUALITY) -> list[dict[str, Any]]:
    """Chunk records for one document, page by page (pure; testable)."""
    out = []
    for page, text in pages:
        flat = " ".join(text.split())
        if len(flat.split()) < min_words:
            continue
        for i, piece in enumerate(chunk_text(flat)):
            if len(piece.split()) < min_words:
                continue
            q = chunk_quality(piece)["score"]
            if q < min_quality and language == "en":  # the gate is tuned on English text
                continue
            out.append({
                "chunk_id": f"{CHUNK_PREFIX}{rec['doc_id']}_p{page:03d}_{i}",
                "era_code": None, "tier": TIER, "doi": None,
                "doc_id": rec["doc_id"], "title": rec.get("title"), "publisher": rec.get("publisher"),
                "year": int(rec["year"]) if str(rec.get("year", "")).isdigit() else None,
                "journal": None, "url": rec.get("url"), "source": "guidelines",
                "language": language, "theme": rec.get("theme"), "page": page,
                "citation": citation_label(rec, page), "quality": q, "text": piece,
            })
    return out


def write_chunks(manifest: list[dict[str, str]], results: dict[str, DocResult]) -> dict[str, Any]:
    """Write ``chunks.jsonl``; returns counts per theme and language."""
    n_theme: dict[str, int] = {}
    n_lang: dict[str, int] = {}
    total = 0
    with open(CHUNKS, "w", encoding="utf-8", newline="\n") as fh:
        for rec in manifest:
            r = results.get(rec["doc_id"])
            if r is None or r.error and not r.pages:
                continue
            lang = r.language if r.language == "am" else (rec.get("language") or "en")
            for c in guideline_chunks(rec, page_texts(rec["doc_id"]), lang):
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
                n_theme[c["theme"]] = n_theme.get(c["theme"], 0) + 1
                n_lang[c["language"]] = n_lang.get(c["language"], 0) + 1
                total += 1
    return {"chunks": total, "by_theme": dict(sorted(n_theme.items(), key=lambda kv: -kv[1])), "by_language": n_lang}


def write_report(manifest: list[dict[str, str]], results: dict[str, DocResult], counts: dict[str, Any],
                 tess: str | None, tess_langs: set[str]) -> None:
    """``ingest_report.md``: per document pages, characters, OCR pages, language."""
    lines = ["# Guidelines ingest report (Tier 2b, E2)", "",
             f"Documents in the manifest: **{len(manifest)}**; ingested: "
             f"**{sum(1 for r in results.values() if r.pages)}**; chunks: **{counts['chunks']:,}** "
             f"(by language: {', '.join(f'{k} {v:,}' for k, v in counts['by_language'].items())}).", "",
             f"Tesseract: {'`' + tess + '` (languages: ' + ', '.join(sorted(tess_langs)) + ')' if tess else '**not installed**; image pages are listed as OCR pending'}.",
             "", "Chunks by theme: " + ", ".join(f"{k} {v:,}" for k, v in counts["by_theme"].items()), "",
             "| doc_id | Pages | Characters | Chars/page (median) | OCR pages | OCR pending | Whole-doc OCR | Language (detected / manifest) | Error |",
             "|---|---:|---:|---:|---:|---:|---|---|---|"]
    for rec in manifest:
        r = results.get(rec["doc_id"])
        if r is None:
            continue
        med = 0
        per = [len(t.strip()) for _, t in page_texts(rec["doc_id"])]
        if per:
            med = int(statistics.median(per))
        lines.append(f"| {r.doc_id} | {r.pages} | {r.chars:,} | {med:,} | {len(r.ocr_pages)} | {len(r.ocr_pending)} | "
                     f"{'yes' if r.whole_doc_ocr else ''} | {r.language} / {r.manifest_language} | {r.error or ''} |")
    pending = [r.doc_id for r in results.values() if r.ocr_pending]
    lines += ["", f"Documents with OCR pending ({len(pending)}): " + (", ".join(pending) or "none") + "."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    """CLI."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--doc", action="append", help="only these doc_ids (repeatable)")
    ap.add_argument("--no-ocr", action="store_true", help="skip OCR even when Tesseract exists")
    ap.add_argument("--chunk-only", action="store_true", help="re-chunk the existing page texts")
    ap.add_argument("--dry-run", action="store_true", help="list what would be ingested")
    args = ap.parse_args(argv)
    manifest = [r for r in read_manifest() if not args.doc or r["doc_id"] in args.doc]
    pdftotext = find_tool("pdftotext")
    tess = None if args.no_ocr else find_tool("tesseract")
    tess_langs = tesseract_languages(tess) if tess else set()
    if args.dry_run:
        print(f"{len(manifest)} documents; pdftotext={pdftotext}; tesseract={tess} {sorted(tess_langs)}")
        return 0
    if not pdftotext:
        raise SystemExit("ERROR: pdftotext not found (install poppler or Git for Windows)")
    results: dict[str, DocResult] = {}
    for n, rec in enumerate(manifest, start=1):
        if args.chunk_only and (TEXTS / rec["doc_id"] / "meta.json").exists():
            prev = json.loads((TEXTS / rec["doc_id"] / "meta.json").read_text(encoding="utf-8"))
            results[rec["doc_id"]] = DocResult(**{k: prev.get(k) for k in DocResult.__dataclass_fields__ if k in prev})
            continue
        r = ingest_doc(rec, pdftotext, tess, tess_langs, do_ocr=not args.no_ocr)
        results[rec["doc_id"]] = r
        print(f"[{n}/{len(manifest)}] {r.doc_id}: {r.pages} pages, {r.chars:,} chars, "
              f"OCR {len(r.ocr_pages)} done / {len(r.ocr_pending)} pending, lang {r.language}"
              + (f" ERROR {r.error}" if r.error else ""))
    counts = write_chunks(read_manifest(), {**{k: v for k, v in results.items()}})
    write_report(read_manifest(), results, counts, tess, tess_langs)
    print(json.dumps(counts, indent=1))
    print(f"wrote {CHUNKS} and {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
