"""Acquire the Tier-2 GUIDANCE corpus from GARDIAN (Phase P5a).

Two-tier doctrine (decision record, 19 Aug 2026): Tier 1 ``era_corpus`` is
FROZEN — this script never touches it. Tier 2 ``guidance_corpus`` powers the
R2 function (implementation how-to, costs, timing, failure modes) and is
built here from the Hugging Face dataset ``CGIAR/gardian-cigi-ai-documents``
(gated — request access on the HF hub first).

Auth: HF_TOKEN from the environment, else from app/backend/.env (same
fallback pattern as build_index.py's OPENAI_API_KEY). The token is never
printed or written anywhere.

The 85k-document dataset is read in STREAMING mode — nothing is loaded into
memory beyond the current record. Because the exact schema is not documented,
run ``--inspect`` first: it prints the field names and truncated sample
values of the first few records, then exits. The extraction helpers below
probe a candidate-key list per logical field (id/title/text/country/year/
url/doi) so reasonable schema variants work unchanged; if inspection shows
different names, extend the *_KEYS tuples.

Filter rules (documented for the phase report):
  1. Ethiopia — the record's country-like metadata field mentions "ethiopia"
     (case-insensitive); if NO country metadata is present on the record,
     fall back to text matching: "ethiopia" in the title, or at least
     ETHIOPIA_TEXT_MIN (3) occurrences in the body text (one passing mention
     does not make a document Ethiopian).
  2. Agroecology relevance — keyword map over the 5 practice families
     (FAMILY_KEYWORDS, built from the frozen ``practice_family`` +
     ``CSA_practices`` vocabulary): at least one keyword in the title, OR at
     least RELEVANCE_TEXT_MIN (2) DISTINCT keywords in the body text.
  3. Usable text — at least --min-words (default 100) words of body text
     (guidance docs are chunked from this text; no text, nothing to index).

Output (under --out, default rag/corpus/guidance/):
  manifest.jsonl — one record per kept document with full provenance
      (dataset id, document id, title, year, source URL / DOI when present,
      matched families, how the Ethiopia rule matched, ``tier: "guidance"``)
  texts/<doc_id>.txt — the body text, one file per document (chunk input)

Counts reported: total scanned -> Ethiopia -> agroecology-relevant -> kept
(after the text-length rule and the --max-docs cap; a hit cap is reported
loudly so the filter can be tightened instead).

Resumable: document ids already in the manifest are skipped on re-run.

Usage:
    python fetch_gardian.py --inspect                # look at the schema first
    python fetch_gardian.py                          # full filtered fetch
    python fetch_gardian.py --limit 500              # smoke test on 500 records
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

DATASET_ID = "CGIAR/gardian-cigi-ai-documents"

# Candidate field names per logical field, probed in order (schemas vary;
# --inspect shows the real ones — extend these tuples if needed).
# REAL schema (--inspect, 21 Aug 2026): metadata / keywords / sieverID /
# pagecount / content / tokenCount / images / tables. So: id = sieverID,
# text = content; there is NO title/country/year/url field — the source URL
# (when present) is embedded in the "; "-joined `metadata` blob and is
# extracted by url_from_metadata() below.
ID_KEYS = ("sieverid",  # GARDIAN's actual id field (first_present lowercases)
           "id", "document_id", "doc_id", "handle", "identifier", "uuid", "_id")
TITLE_KEYS = ("title", "dc_title", "name", "document_title")
TEXT_KEYS = ("text", "content", "full_text", "fulltext", "body",
             "pdf_text", "extracted_text", "document_text")
COUNTRY_KEYS = ("country", "countries", "region", "regions", "coverage",
                "spatial_coverage", "geographic_coverage", "geography")
YEAR_KEYS = ("year", "publication_year", "date", "publication_date",
             "issued", "date_issued", "dc_date")
URL_KEYS = ("url", "source_url", "link", "pdf_url", "download_url",
            "handle_url", "uri", "landing_page")
DOI_KEYS = ("doi", "dois")

ETHIOPIA_TEXT_MIN = 3    # body-text mentions needed when no country metadata
RELEVANCE_TEXT_MIN = 2   # distinct body-text keywords needed without a title hit

# Practice vocabulary of the frozen model (practice_family + CSA_practices in
# data/processed/CSA_ERA_final_model_ready.csv), lowered to match lowercased
# title/text. Substring match: "intercrop" also hits "intercropping" etc.
FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Integrated soil fertility management": (
        "soil fertility", "inorganic fertilizer", "organic fertilizer",
        "fertilizer application", "fertiliser", "compost", "manure",
        "biochar", "isfm", "organic amendment", "liming", "green manure",
        "crop residue", "vermicompost", "soil amendment",
    ),
    "Crop production and management": (
        "improved variet", "improved seed", "intercrop", "crop rotation",
        "mulch", "conservation tillage", "reduced tillage", "zero tillage",
        "no-till", "minimum tillage", "conservation agriculture",
        "drought tolerant", "drought-tolerant", "improved fallow",
        "row planting", "residue incorporation",
    ),
    "Erosion control and water management": (
        "soil and water conservation", "soil bund", "stone bund", "terrac",
        "water harvesting", "check dam", "gully", "contour",
        "drip irrigation", "furrow irrigation", "deficit irrigation",
        "supplemental irrigation", "small-scale irrigation",
        "erosion control", "soil erosion", "watershed management",
        "runoff management", "exclosure",
    ),
    "Agro-forestry and forest management": (
        "agroforestry", "agro-forestry", "alley cropping", "alleycropping",
        "parkland", "faidherbia", "multistrata", "tree planting",
        "afforestation", "reforestation", "farm forestry", "homegarden",
        "farmer managed natural regeneration",
    ),
    "Livestock production and management": (
        "grazing management", "rotational grazing", "pasture management",
        "rangeland", "fodder", "forage production", "animal feed",
        "feed management", "feed supplement", "livestock feed",
        "feed processing",
    ),
}

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9._-]+")
_URL_RE = re.compile(r"https?://[^\s;\"']+")
TITLE_HEAD_WORDS = 12  # display-title fallback: first N words of the content


def find_hf_token() -> str:
    """HF_TOKEN from the environment, else app/backend/.env. Never printed."""
    import os

    token = os.environ.get("HF_TOKEN", "").strip()
    if token:
        return token
    env_path = Path(__file__).resolve().parents[2] / "app" / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("HF_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                if token:
                    return token
    raise SystemExit(
        "ERROR: set HF_TOKEN (env var or app/backend/.env) — the dataset "
        f"'{DATASET_ID}' is gated and needs an authorized Hugging Face token."
    )


# ---------------------------------------------------------- field extraction
def as_text(value: Any) -> str:
    """Flatten a field value (str / list / dict / scalar) to a plain string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return "; ".join(t for t in (as_text(v) for v in value) if t)
    if isinstance(value, dict):
        return "; ".join(t for t in (as_text(v) for v in value.values()) if t)
    return str(value).strip()


def first_present(record: dict[str, Any], keys: Iterable[str]) -> str:
    """First non-empty candidate field, flattened to text ('' if none)."""
    lowered = {k.lower(): v for k, v in record.items()}
    for key in keys:
        text = as_text(lowered.get(key))
        if text:
            return text
    return ""


def extract_year(record: dict[str, Any]) -> int | None:
    m = _YEAR_RE.search(first_present(record, YEAR_KEYS))
    return int(m.group(0)) if m else None


def safe_doc_id(raw_id: str, fallback_index: int) -> str:
    """Filesystem/chunk-id safe document id (G_ chunk ids build on this)."""
    cleaned = _SAFE_ID_RE.sub("_", raw_id).strip("_")[:80]
    return cleaned or f"doc{fallback_index:06d}"


def url_from_metadata(record: dict[str, Any]) -> str:
    """Source URL from GARDIAN's '; '-joined `metadata` blob ('' if none).

    The blob looks like "<md5>; gardian_index; <source url>; <leading text>"
    — the URL segment is present for some records only.
    """
    m = _URL_RE.search(first_present(record, ("metadata",)))
    return m.group(0).rstrip(".,);") if m else ""


def display_title(text: str) -> str | None:
    """Fallback display title — first TITLE_HEAD_WORDS words of the body.

    GARDIAN records carry no title field; the UI would otherwise show
    "Untitled document" for every guidance chip. Marked in the manifest as
    ``title_source: "content_head"`` — it is NOT used by the filter rules,
    which see the raw (empty) title so their semantics stay as documented.
    """
    words = text.split()
    if not words:
        return None
    head = " ".join(words[:TITLE_HEAD_WORDS])
    return head + (" …" if len(words) > TITLE_HEAD_WORDS else "")


# ---------------------------------------------------------------- filter rules
def is_ethiopia(country_meta: str, title: str, text: str) -> tuple[bool, str]:
    """Ethiopia rule (see module docstring). Returns (verdict, how)."""
    if country_meta:
        return ("ethiopia" in country_meta.lower(), "country_metadata")
    if "ethiopia" in title.lower():
        return True, "title"
    if text.lower().count("ethiopia") >= ETHIOPIA_TEXT_MIN:
        return True, "text"
    return False, "none"


def matched_families(title: str, text: str) -> list[str]:
    """Practice families whose keywords the document matches.

    A family matches on ≥1 keyword in the title, or ≥RELEVANCE_TEXT_MIN
    distinct keywords in the body text. Relevance = any family matches.
    """
    title_l, text_l = title.lower(), text.lower()
    out: list[str] = []
    for family, keywords in FAMILY_KEYWORDS.items():
        if any(kw in title_l for kw in keywords):
            out.append(family)
            continue
        if sum(1 for kw in keywords if kw in text_l) >= RELEVANCE_TEXT_MIN:
            out.append(family)
    return out


# ------------------------------------------------------------------ inspection
def inspect(stream: Iterable[dict[str, Any]], n: int) -> None:
    """Print field names + truncated sample values of the first n records."""
    for i, record in enumerate(stream):
        if i >= n:
            break
        print(f"\n--- record {i} ---")
        for key, value in record.items():
            preview = as_text(value).replace("\n", " ")[:160]
            print(f"  {key!r}: {preview!r}")
    print("\n(inspection only — nothing written; adjust *_KEYS if needed)")


# ------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="../corpus/guidance",
                    help="output dir (manifest.jsonl, texts/)")
    ap.add_argument("--split", default="train")
    ap.add_argument("--inspect", action="store_true",
                    help="print the first --inspect-n records' schema and exit")
    ap.add_argument("--inspect-n", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0,
                    help="scan only the first N records (smoke test)")
    ap.add_argument("--max-docs", type=int, default=3000,
                    help="hard cap on kept documents (2-5k sane range; a hit "
                         "cap means: tighten the filter)")
    ap.add_argument("--min-words", type=int, default=100,
                    help="drop documents with less body text than this")
    args = ap.parse_args()

    from datasets import load_dataset  # deferred heavy import

    token = find_hf_token()
    stream = load_dataset(DATASET_ID, split=args.split, streaming=True,
                          token=token)

    if args.inspect:
        inspect(iter(stream), args.inspect_n)
        return 0

    out_dir = Path(args.out)
    texts_dir = out_dir / "texts"
    texts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"

    existing: set[str] = set()
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.add(json.loads(line)["doc_id"])
        print(f"Resuming: {len(existing)} documents already in the manifest.")

    n_scanned = n_ethiopia = n_relevant = n_kept = n_thin = n_skipped = 0
    capped = False
    with open(manifest_path, "a", encoding="utf-8") as manifest:
        for i, record in enumerate(stream):
            if args.limit and i >= args.limit:
                break
            n_scanned += 1
            title = first_present(record, TITLE_KEYS)
            text = first_present(record, TEXT_KEYS)
            country_meta = first_present(record, COUNTRY_KEYS)

            eth, eth_via = is_ethiopia(country_meta, title, text)
            if not eth:
                continue
            n_ethiopia += 1

            families = matched_families(title, text)
            if not families:
                continue
            n_relevant += 1

            if len(text.split()) < args.min_words:
                n_thin += 1
                continue

            doc_id = safe_doc_id(first_present(record, ID_KEYS), i)
            if doc_id in existing:
                n_skipped += 1
                continue
            if n_kept >= args.max_docs:
                capped = True
                break

            (texts_dir / f"{doc_id}.txt").write_text(text, encoding="utf-8")
            manifest.write(json.dumps({
                "doc_id": doc_id,
                "dataset": DATASET_ID,
                "tier": "guidance",
                # Real records have no title field — fall back to the first
                # words of the body for the UI chips (filters above saw the
                # raw title, so this changes display only).
                "title": title or display_title(text),
                "title_source": "field" if title else "content_head",
                "year": extract_year(record),
                "url": (first_present(record, URL_KEYS)
                        or url_from_metadata(record) or None),
                "doi": first_present(record, DOI_KEYS) or None,
                "country_meta": country_meta or None,
                "ethiopia_via": eth_via,
                "matched_families": families,
                "n_words": len(text.split()),
                "text_file": f"texts/{doc_id}.txt",
            }, ensure_ascii=False) + "\n")
            existing.add(doc_id)
            n_kept += 1
            if n_kept % 100 == 0:
                print(f"  kept {n_kept} (scanned {n_scanned})")

    print(
        f"Done: scanned {n_scanned} -> Ethiopia {n_ethiopia} -> "
        f"agroecology-relevant {n_relevant} -> kept {n_kept} "
        f"({n_thin} dropped as <{args.min_words} words, "
        f"{n_skipped} already in manifest) -> {manifest_path}"
    )
    if capped:
        print(f"WARNING: --max-docs cap ({args.max_docs}) HIT — the filter "
              "yields more; tighten it (or raise the cap deliberately) and "
              "report this in the phase log.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
