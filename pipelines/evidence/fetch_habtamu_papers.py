#!/usr/bin/env python3
"""Acquire open-access papers for Habtamu's studies into the Tier 1 corpus (brief E2 B1).

Wraps, never forks, ``rag/ingest/fetch_papers.py``: every study goes through
the same ``acquire`` fallback chain (Crossref, Unpaywall all locations,
OpenAlex, Europe PMC, Crossref links; only legally open copies). PDFs land in
``rag/corpus/pdfs/`` and manifest rows are appended to
``rag/corpus/manifest.jsonl`` with ``source: HAB`` (existing rows gain
``source: ERA``; nothing else in them changes).

* **Studies with a DOI** (normalised in the store): fetched directly. When the
  ERA corpus already holds the same DOI with a full text, that file is reused.
* **Studies without a DOI**: a Crossref author + year search built from
  ``Study_ID`` (``DeOliveira_2026`` -> author "De Oliveira", year 2026) and the
  study's intervention, outcome and country words. A hit is accepted only when
  the first author's family name and the year both match and the title shares
  at least two content words with the study; it is recorded with
  ``doi_source = crossref_author_year_search`` and the matched title, for the
  reviewer to check.
* Non-OA papers are listed with their landing URL in
  ``data/evidence/review/habtamu_papers_missing.csv``.

Every download is recorded with its URL (``download_url``). Resumable: studies
already in the manifest are skipped.

Usage::

    python pipelines/evidence/fetch_habtamu_papers.py --email you@example.org [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.evidence import common  # noqa: E402

logger = logging.getLogger(__name__)

CORPUS = common.REPO_ROOT / "rag" / "corpus"
MANIFEST = CORPUS / "manifest.jsonl"
MISSING_CSV = common.EVIDENCE_DIR / "review" / "habtamu_papers_missing.csv"
CROSSREF_SEARCH = "https://api.crossref.org/works"
SOURCE = "HAB"
_STOP = {"the", "and", "of", "in", "on", "a", "an", "for", "with", "to", "by", "under", "effect", "effects",
         "nr", "na", "system", "systems", "yield", "soil"}


# ---------------------------------------------------------------- studies
def habtamu_studies(store: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per Habtamu study: ``study_id, doi, study_id_raw, country, keywords``."""
    if store is None:
        from pipelines.evidence import load_habtamu, schema

        store = schema.coerce(load_habtamu.load()[0])
    hab = store[store["source"] == SOURCE]
    rows = []
    for sid, g in hab.groupby("study_id", sort=True):
        extra = [json.loads(e) for e in g["extra"].dropna()]
        raw = next((e.get("Study_ID_raw") for e in extra if e.get("Study_ID_raw")), sid.removeprefix("HAB_"))
        words: list[str] = []
        for col in ("practice_raw", "outcome_raw", "crop"):
            for v in g[col].dropna().unique()[:3]:
                words += [w for w in re.findall(r"[A-Za-z]{4,}", str(v)) if w.lower() not in _STOP]
        rows.append({
            "study_id": sid, "doi": next(iter(g["doi"].dropna()), None), "study_id_raw": raw,
            "country": next(iter(g["country"].dropna()), None),
            "keywords": " ".join(dict.fromkeys(words))[:200],
        })
    return pd.DataFrame(rows)


def author_year(study_id_raw: str) -> tuple[str | None, int | None]:
    """``DeOliveira_2026`` -> ("De Oliveira", 2026); ``Roschewitz_2005_001`` -> ("Roschewitz", 2005)."""
    m = re.match(r"^([A-Za-zÀ-ɏ'\-]+?)(?:_?et_?al)?_((?:19|20)\d{2})", study_id_raw or "")
    if not m:
        return None, None
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", m.group(1)).replace("_", " ").strip()
    return name, int(m.group(2))


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().replace(" ", "")


def accept_search_hit(item: dict[str, Any], surname: str, year: int, keywords: str) -> bool:
    """Strict acceptance of a Crossref search hit (family name, year, two shared title words)."""
    authors = item.get("author") or []
    if not authors or _fold(authors[0].get("family", "")) != _fold(surname):
        return False
    years = [((item.get(k) or {}).get("date-parts") or [[None]])[0][0]
             for k in ("published-print", "published-online", "issued")]
    if year not in years:
        return False
    title = " ".join(item.get("title") or []).lower()
    shared = {w.lower() for w in keywords.split()} & set(re.findall(r"[a-z]{4,}", title))
    return len(shared) >= 2


def search_doi(session, surname: str, year: int, keywords: str, email: str) -> dict[str, Any] | None:
    """Best accepted Crossref hit for an author/year study, or ``None``."""
    params = {"query.author": surname, "query.bibliographic": keywords, "rows": 5,
              "filter": f"from-pub-date:{year},until-pub-date:{year}", "mailto": email}
    try:
        r = session.get(CROSSREF_SEARCH, params=params, timeout=30)
    except Exception as exc:  # noqa: BLE001 - network errors are logged, never fatal
        logger.warning("crossref search failed for %s %s: %s", surname, year, exc)
        return None
    if r.status_code != 200:
        return None
    for item in (r.json().get("message") or {}).get("items") or []:
        if accept_search_hit(item, surname, year, keywords):
            return {"doi": str(item.get("DOI", "")).lower(), "title": " ".join(item.get("title") or [])}
    return None


# ---------------------------------------------------------------- manifest
def read_manifest(path: Path = MANIFEST) -> list[dict[str, Any]]:
    """Manifest records in file order."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_manifest(records: list[dict[str, Any]], path: Path = MANIFEST) -> None:
    """Atomic rewrite (``.bak`` kept), every record tagged with ``source`` (ERA by default)."""
    if path.exists():
        path.with_suffix(".jsonl.bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    tmp = path.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            rec.setdefault("source", "ERA")
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def has_fulltext(rec: dict[str, Any], corpus: Path = CORPUS) -> bool:
    """True when the record's PDF or XML is on disk."""
    pdf, xml = rec.get("pdf_file"), rec.get("fulltext_xml")
    return bool((pdf and (corpus / "pdfs" / pdf).exists()) or (xml and (corpus / "xml" / xml).exists()))


def run(email: str, limit: int = 0, sleep: float = 1.0, dry_run: bool = False) -> dict[str, Any]:
    """Fetch every Habtamu study not yet in the manifest; returns counts."""
    import requests

    common.bootstrap_repo_path()
    from rag.ingest import fetch_papers as fp

    studies = habtamu_studies()
    records = read_manifest()
    done = {r["era_code"] for r in records}
    era_by_doi = {r["doi"].lower(): r for r in records if r.get("doi") and r.get("source", "ERA") == "ERA"}
    seen_doi: dict[str, dict[str, Any]] = {  # HAB rows from earlier runs (resumable)
        r["doi"].lower(): r for r in records if r.get("doi") and r.get("source") == SOURCE}
    todo = studies[~studies["study_id"].isin(done)]
    if limit:
        todo = todo.head(limit)
    logger.info("%d Habtamu studies, %d already in the manifest, %d to process", len(studies),
                len(studies) - len(studies[~studies['study_id'].isin(done)]), len(todo))
    if dry_run:
        return {"studies": len(studies), "to_process": len(todo), "with_doi": int(studies["doi"].notna().sum())}

    session = requests.Session()
    session.headers["User-Agent"] = fp.UA.format(email=email)
    downloaded: dict[str, str] = {}
    original = fp.download_pdf

    def recording_download(url, dest, sess):  # wrap: remember which URL produced the file
        ok = original(url, dest, sess)
        if ok:
            downloaded[dest.name] = url
        return ok

    fp.download_pdf = recording_download
    pdf_dir, xml_dir = CORPUS / "pdfs", CORPUS / "xml"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    xml_dir.mkdir(parents=True, exist_ok=True)
    try:
        for n, s in enumerate(todo.itertuples(), start=1):
            doi = s.doi if isinstance(s.doi, str) and s.doi else None          # NaN-safe (pandas)
            country = s.country if isinstance(s.country, str) else None
            rec: dict[str, Any] = {"era_code": s.study_id, "source": SOURCE, "doi": doi,
                                   "author": s.study_id_raw, "study_id_raw": s.study_id_raw,
                                   "country": country, "doi_source": "habtamu_sheet" if doi else None}
            if not rec["doi"]:
                surname, year = author_year(s.study_id_raw)
                hit = search_doi(session, surname, year, s.keywords, email) if surname and year else None
                if hit and hit["doi"]:
                    rec.update(doi=hit["doi"], doi_source="crossref_author_year_search", matched_title=hit["title"])
            doi_key = (rec["doi"] or "").lower()
            era = era_by_doi.get(doi_key)
            same = seen_doi.get(doi_key)
            if (era and has_fulltext(era)) or same:
                src = era if (era and has_fulltext(era)) else same
                for k in ("title", "container", "year", "abstract", "pdf_file", "fulltext_xml", "oa_status",
                          "licence", "landing_url", "download_url"):
                    if src.get(k) is not None:
                        rec[k] = src[k]
                rec["pdf_source"] = (f"reused_era:{src['era_code']}" if src is era
                                     else f"same_doi_as:{src['era_code']}")
            elif rec["doi"]:
                try:
                    fp.acquire(rec, email, session, pdf_dir, xml_dir)
                except Exception as exc:  # noqa: BLE001 - one study never stops the run
                    rec["fetch_error"] = str(exc)[:200]
                if rec.get("pdf_file") in downloaded:
                    rec["download_url"] = downloaded[rec["pdf_file"]]
            else:
                rec["oa_status"] = "no_doi"
            if doi_key and doi_key not in seen_doi:
                seen_doi[doi_key] = rec
            records.append(rec)
            got = "fulltext" if has_fulltext(rec) else rec.get("oa_status", "?")
            print(f"[{n}/{len(todo)}] {s.study_id} {rec.get('doi_source') or 'no doi'} -> {got}")
            if n % 25 == 0:
                write_manifest(records)
            time.sleep(sleep)
    finally:
        fp.download_pdf = original
        write_manifest(records)
    return summarise()


def summarise() -> dict[str, Any]:
    """Coverage of the HAB manifest rows and the missing-paper sheet."""
    hab = [r for r in read_manifest() if r.get("source") == SOURCE]
    rows = []
    for r in hab:
        if r.get("doi") and not has_fulltext(r):
            rows.append({"study_id": r["era_code"], "doi": r["doi"], "doi_source": r.get("doi_source"),
                         "title": r.get("title") or r.get("matched_title"), "oa_status": r.get("oa_status"),
                         "landing_url": r.get("landing_url") or f"https://doi.org/{r['doi']}"})
    MISSING_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["study_id", "doi", "doi_source", "title", "oa_status", "landing_url"]).to_csv(
        MISSING_CSV, index=False, lineterminator="\n", encoding="utf-8")
    with_doi = [r for r in hab if r.get("doi")]
    full = [r for r in hab if has_fulltext(r)]
    return {
        "studies": len(hab), "with_doi": len(with_doi),
        "doi_from_sheet": sum(r.get("doi_source") == "habtamu_sheet" for r in hab),
        "doi_from_search": sum(r.get("doi_source") == "crossref_author_year_search" for r in hab),
        "fulltext": len(full), "reused_era": sum(str(r.get("pdf_source", "")).startswith("reused_era") for r in hab),
        "oa_share_of_doi": round(len(full) / len(with_doi), 4) if with_doi else 0.0,
        "missing_listed": len(rows),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI."""
    ap = argparse.ArgumentParser(description="Fetch open-access Habtamu papers into the Tier 1 corpus.")
    ap.add_argument("--email", default=os.environ.get("UNPAYWALL_EMAIL"),
                    help="contact email for Unpaywall/OpenAlex/Crossref (or set UNPAYWALL_EMAIL)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--summary-only", action="store_true", help="recompute the summary and missing sheet only")
    ap.add_argument("--dry-run", action="store_true", help="count studies to process, fetch nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    common.setup_logging(args.verbose)
    if args.summary_only:
        print(json.dumps(summarise(), indent=2))
        return 0
    if not args.email and not args.dry_run:
        raise SystemExit("ERROR: a contact email is required (--email or UNPAYWALL_EMAIL)")
    print(json.dumps(run(args.email or "", args.limit, args.sleep, args.dry_run), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
