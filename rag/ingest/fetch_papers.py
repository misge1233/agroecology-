"""Acquire the RAG corpus: ERA study DOIs -> metadata + open-access PDFs.

For every study in the DOI manifest (paper/references/era_doi_list.csv):
  1. Crossref  -> bibliographic metadata + abstract (when deposited).
  2. Unpaywall -> best open-access location -> download PDF when available.
  3. Record everything in corpus/manifest.jsonl (one JSON object per study).

Polite + resumable:
  - identifies itself to both APIs (Unpaywall REQUIRES an email: set
    UNPAYWALL_EMAIL or pass --email);
  - throttles requests (--sleep, default 1s);
  - re-running skips studies already present in the manifest, so interrupted
    runs continue where they left off.

Usage:
    export UNPAYWALL_EMAIL="you@example.org"
    python fetch_papers.py --doi-list ../../paper/references/era_doi_list.csv --out ../corpus

Closed-access studies still contribute metadata + abstract to the index —
the manifest records `oa_status` so the paper can report exact corpus coverage.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

CROSSREF_URL = "https://api.crossref.org/works/{doi}"
UNPAYWALL_URL = "https://api.unpaywall.org/v2/{doi}"
TIMEOUT = 30
UA = "AgroAdvisor-ET corpus builder (research use; mailto:{email})"


def slugify(doi: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", doi).strip("_")[:120]


def load_manifest(path: Path) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["era_code"]] = rec
    return done


def crossref_meta(doi: str, session: requests.Session) -> dict:
    r = session.get(CROSSREF_URL.format(doi=doi), timeout=TIMEOUT)
    if r.status_code != 200:
        return {"crossref_status": r.status_code}
    m = r.json().get("message", {})
    year = None
    for k in ("published-print", "published-online", "issued"):
        parts = (m.get(k) or {}).get("date-parts") or [[None]]
        if parts[0][0]:
            year = parts[0][0]
            break
    abstract = re.sub(r"<[^>]+>", " ", m.get("abstract") or "").strip() or None
    return {
        "crossref_status": 200,
        "title": (m.get("title") or [None])[0],
        "container": (m.get("container-title") or [None])[0],
        "year": year,
        "abstract": abstract,
        "type": m.get("type"),
    }


def unpaywall_oa(doi: str, email: str, session: requests.Session) -> dict:
    r = session.get(UNPAYWALL_URL.format(doi=doi), params={"email": email}, timeout=TIMEOUT)
    if r.status_code != 200:
        return {"oa_status": f"unpaywall_http_{r.status_code}", "pdf_url": None}
    j = r.json()
    best = j.get("best_oa_location") or {}
    return {
        "oa_status": j.get("oa_status") or ("closed" if not j.get("is_oa") else "unknown"),
        "pdf_url": best.get("url_for_pdf") or None,
        "landing_url": best.get("url") or None,
        "licence": best.get("license"),
    }


def download_pdf(url: str, dest: Path, session: requests.Session) -> bool:
    try:
        with session.get(url, timeout=60, stream=True, allow_redirects=True) as r:
            if r.status_code != 200:
                return False
            head = b""
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if not head:
                        head = chunk[:5]
                    f.write(chunk)
            if not head.startswith(b"%PDF"):
                dest.rename(dest.with_suffix(".html"))  # kept for manual review
                return False
            return True
    except requests.RequestException:
        if dest.exists():
            dest.rename(dest.with_suffix(".partial"))
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--doi-list", required=True, help="era_doi_list.csv (era_code,doi,...)")
    ap.add_argument("--out", default="../corpus", help="corpus output directory")
    ap.add_argument("--email", default=os.environ.get("UNPAYWALL_EMAIL"),
                    help="contact email for the Unpaywall polite pool (or set UNPAYWALL_EMAIL)")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between studies")
    ap.add_argument("--limit", type=int, default=0, help="stop after N new studies (0 = all)")
    args = ap.parse_args()

    if not args.email:
        sys.exit("ERROR: Unpaywall requires a contact email. Set UNPAYWALL_EMAIL or pass --email.")

    out = Path(args.out)
    pdf_dir = out / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.jsonl"
    done = load_manifest(manifest_path)

    with open(args.doi_list, newline="", encoding="utf-8") as f:
        studies = list(csv.DictReader(f))

    session = requests.Session()
    session.headers["User-Agent"] = UA.format(email=args.email)

    new = 0
    with open(manifest_path, "a", encoding="utf-8") as mf:
        for s in studies:
            code, doi = s["era_code"].strip(), (s.get("doi") or "").strip()
            if code in done:
                continue
            rec: dict = {"era_code": code, "doi": doi or None,
                         "author": s.get("author"), "journal": s.get("journal")}
            if doi and doi.upper() != "NA":
                rec.update(crossref_meta(doi, session))
                rec.update(unpaywall_oa(doi, args.email, session))
                if rec.get("pdf_url"):
                    dest = pdf_dir / f"{code}_{slugify(doi)}.pdf"
                    rec["pdf_file"] = dest.name if download_pdf(rec["pdf_url"], dest, session) else None
                else:
                    rec["pdf_file"] = None
            else:
                rec.update({"oa_status": "no_doi", "pdf_file": None})
            mf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            mf.flush()
            new += 1
            got = "PDF" if rec.get("pdf_file") else rec.get("oa_status", "?")
            print(f"[{new}] {code}  {got}")
            if args.limit and new >= args.limit:
                break
            time.sleep(args.sleep)

    total = len(load_manifest(manifest_path))
    with_pdf = sum(1 for r in load_manifest(manifest_path).values() if r.get("pdf_file"))
    print(f"\nDone. Manifest: {total} studies, {with_pdf} with full-text PDF.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
