"""Acquire the RAG corpus: ERA study DOIs -> metadata + open-access full text.

For every study in the DOI manifest (paper/references/era_doi_list.csv):
  1. Crossref   -> bibliographic metadata + abstract (when deposited).
  2. OA fallback chain (stop at first success, never bypassing paywalls):
       a. Unpaywall — ALL `oa_locations` (not just best): `url_for_pdf`
          first, then the landing `url` with PDF content sniffing.
       b. OpenAlex — `best_oa_location.pdf_url`, then every other location;
          also reconstructs a missing abstract from
          `abstract_inverted_index`.
       c. Europe PMC — if `isOpenAccess`, fetch the full-text JATS XML
          (saved as corpus/xml/<era_code>.xml); abstract fallback otherwise.
       d. Crossref `link` array (publisher-deposited full-text URLs).
  3. Record everything in corpus/manifest.jsonl (one JSON object per study),
     including provenance: `pdf_source`, `abstract_source`, `fulltext_xml`.

All bibliographic strings (title, journal, abstract) are cleaned of HTML
tags and entities (Crossref deposits titles like "<i>Eragrostis tef</i>"
and double-escaped "&lt;i&gt;...").

Polite + resumable:
  - identifies itself to every API (Unpaywall REQUIRES an email: set
    UNPAYWALL_EMAIL or pass --email; the same email goes to OpenAlex's
    polite pool via `mailto`);
  - throttles requests (--sleep, default 1s between studies);
  - re-running skips studies already present in the manifest, so interrupted
    runs continue where they left off.

Modes:
  default          process DOI-list studies not yet in the manifest.
  --retry-missing  reprocess ONLY manifest entries that lack a full text
                   (no pdf_file / fulltext_xml on disk) and/or an abstract,
                   running the full fallback chain for each; the manifest is
                   rewritten in place (atomic replace, .bak backup kept) and
                   successful first-run entries pass through untouched apart
                   from HTML tag/entity cleaning of their metadata.

Usage:
    export UNPAYWALL_EMAIL="you@example.org"
    python fetch_papers.py --doi-list ../../paper/references/era_doi_list.csv --out ../corpus
    python fetch_papers.py --doi-list ../../paper/references/era_doi_list.csv --out ../corpus --retry-missing

Closed-access studies still contribute metadata + abstract to the index —
the manifest records `oa_status` so the paper can report exact corpus coverage.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

CROSSREF_URL = "https://api.crossref.org/works/{doi}"
UNPAYWALL_URL = "https://api.unpaywall.org/v2/{doi}"
OPENALEX_URL = "https://api.openalex.org/works/https://doi.org/{doi}"
EUROPEPMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPEPMC_XML_URL = (
    "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
)
TIMEOUT = 30
DOWNLOAD_TIMEOUT = 60
UA = "AgroAdvisor-ET corpus builder (research use; mailto:{email})"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_html(value: str | None) -> str | None:
    """Strip HTML tags and entities from bibliographic strings.

    Crossref titles arrive both singly ("<i>tef</i>") and doubly
    ("&lt;i&gt;tef&lt;/i&gt;") encoded, so unescape+strip runs twice.
    """
    if not value:
        return None
    for _ in range(2):
        value = html.unescape(value)
        value = _TAG_RE.sub(" ", value)
    return _WS_RE.sub(" ", value).strip() or None


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


# --------------------------------------------------------------------- sources
def crossref_meta(doi: str, session: requests.Session) -> dict:
    """Bibliographic metadata (+ abstract, + full-text link array) from Crossref."""
    try:
        r = session.get(CROSSREF_URL.format(doi=doi), timeout=TIMEOUT)
    except requests.RequestException:
        return {"crossref_status": "error"}
    if r.status_code != 200:
        return {"crossref_status": r.status_code}
    m = r.json().get("message", {})
    year = None
    for k in ("published-print", "published-online", "issued"):
        parts = (m.get(k) or {}).get("date-parts") or [[None]]
        if parts[0][0]:
            year = parts[0][0]
            break
    links = []
    for link in m.get("link") or []:
        url = link.get("URL")
        if url and link.get("content-type") in ("application/pdf", "unspecified"):
            links.append(url)
    return {
        "crossref_status": 200,
        "title": clean_html((m.get("title") or [None])[0]),
        "container": clean_html((m.get("container-title") or [None])[0]),
        "year": year,
        "abstract": clean_html(m.get("abstract")),
        "type": m.get("type"),
        "_links": links,  # transient — consumed by the fallback chain, not stored
    }


def unpaywall_info(doi: str, email: str, session: requests.Session) -> dict:
    """OA status + EVERY OA location (best first), not just best_oa_location."""
    try:
        r = session.get(UNPAYWALL_URL.format(doi=doi), params={"email": email},
                        timeout=TIMEOUT)
    except requests.RequestException:
        return {"oa_status": "unpaywall_error", "locations": []}
    if r.status_code != 200:
        return {"oa_status": f"unpaywall_http_{r.status_code}", "locations": []}
    j = r.json()
    best = j.get("best_oa_location") or {}
    locations = [best] + [
        loc for loc in (j.get("oa_locations") or []) if loc and loc != best
    ]
    return {
        "oa_status": j.get("oa_status") or ("closed" if not j.get("is_oa") else "unknown"),
        "locations": [loc for loc in locations if loc],
        "pdf_url": best.get("url_for_pdf") or None,
        "landing_url": best.get("url") or None,
        "licence": best.get("license"),
    }


def openalex_info(doi: str, email: str, session: requests.Session) -> dict:
    """PDF candidate URLs + abstract (from abstract_inverted_index) via OpenAlex."""
    try:
        r = session.get(OPENALEX_URL.format(doi=doi), params={"mailto": email},
                        timeout=TIMEOUT)
    except requests.RequestException:
        return {"pdf_urls": [], "abstract": None}
    if r.status_code != 200:
        return {"pdf_urls": [], "abstract": None}
    j = r.json()
    best = j.get("best_oa_location") or {}
    urls: list[str] = []
    for loc in [best] + list(j.get("locations") or []):
        if not loc:
            continue
        for u in (loc.get("pdf_url"), loc.get("landing_page_url")):
            if u and u not in urls:
                urls.append(u)
    inv = j.get("abstract_inverted_index") or {}
    abstract = None
    if inv:
        positions: dict[int, str] = {}
        for word, idxs in inv.items():
            for i in idxs:
                positions[i] = word
        abstract = clean_html(" ".join(positions[i] for i in sorted(positions)))
    return {"pdf_urls": urls, "abstract": abstract}


def europepmc_info(doi: str, session: requests.Session) -> dict:
    """Open-access flag, full-text PMCID, and abstract via Europe PMC.

    Full-text XML is only served for articles with a PMCID, via
    /rest/<PMCID>/fullTextXML (the <source>/<id> form 404s).
    """
    try:
        r = session.get(
            EUROPEPMC_SEARCH_URL,
            params={"query": f'DOI:"{doi}"', "format": "json", "resultType": "core"},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return {}
    if r.status_code != 200:
        return {}
    results = (r.json().get("resultList") or {}).get("result") or []
    if not results:
        return {}
    hit = results[0]
    return {
        "is_oa": hit.get("isOpenAccess") == "Y",
        "in_epmc": hit.get("inEPMC") == "Y",
        "pmcid": hit.get("pmcid"),
        "abstract": clean_html(hit.get("abstractText")),
    }


# ------------------------------------------------------------------- downloads
def download_pdf(url: str, dest: Path, session: requests.Session) -> bool:
    """Download url to dest; keep only if it is a real PDF (%PDF magic)."""
    try:
        with session.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True,
                         allow_redirects=True) as r:
            if r.status_code != 200:
                return False
            head = b""
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if not head:
                        head = chunk[:5]
                    f.write(chunk)
        if head.startswith(b"%PDF"):
            return True
    except requests.RequestException:
        pass
    dest.unlink(missing_ok=True)  # never litter non-PDF/partial downloads
    return False


def download_xml(url: str, dest: Path, session: requests.Session) -> bool:
    """Download full-text XML to dest; keep only if it looks like XML."""
    try:
        r = session.get(url, timeout=DOWNLOAD_TIMEOUT, allow_redirects=True)
    except requests.RequestException:
        return False
    body = r.content if r.status_code == 200 else b""
    if body.lstrip()[:1] == b"<" and b"<article" in body[:4000]:
        dest.write_bytes(body)
        return True
    return False


# -------------------------------------------------------------- fallback chain
def acquire(rec: dict, email: str, session: requests.Session,
            pdf_dir: Path, xml_dir: Path, refresh_meta: bool = True) -> None:
    """Run the OA fallback chain for one study, updating `rec` in place.

    Stops at the first full-text success (PDF or XML). Also fills a missing
    abstract from any source encountered along the way, recording
    `abstract_source`. Only ever touches legally-open locations.
    """
    code, doi = rec["era_code"], rec.get("doi")
    if not doi:
        rec.setdefault("oa_status", "no_doi")
        rec.setdefault("pdf_file", None)
        return

    crossref_links: list[str] = []
    if refresh_meta or rec.get("crossref_status") != 200:
        meta = crossref_meta(doi, session)
        crossref_links = meta.pop("_links", [])
        old_abstract = rec.get("abstract")
        rec.update({k: v for k, v in meta.items() if v is not None or k not in rec})
        if not old_abstract and rec.get("abstract"):
            rec["abstract_source"] = "crossref"

    pdf_path = pdf_dir / f"{code}_{slugify(doi)}.pdf"
    xml_path = xml_dir / f"{code}.xml"
    has_fulltext = bool(rec.get("pdf_file")) and (pdf_dir / rec["pdf_file"]).exists()
    tried: set[str] = set()

    def try_pdf(urls: list[str | None], source: str) -> bool:
        for url in urls:
            if not url or url in tried:
                continue
            tried.add(url)
            if download_pdf(url, pdf_path, session):
                rec["pdf_file"] = pdf_path.name
                rec["pdf_source"] = source
                return True
        return False

    # (a) Unpaywall — all OA locations: url_for_pdf first, then landing url.
    up = unpaywall_info(doi, email, session)
    for k in ("oa_status", "pdf_url", "landing_url", "licence"):
        if k in up:
            rec[k] = up[k]
    if not has_fulltext:
        for loc in up["locations"]:
            if try_pdf([loc.get("url_for_pdf")], "unpaywall"):
                has_fulltext = True
                break
        if not has_fulltext:
            for loc in up["locations"]:
                if try_pdf([loc.get("url")], "unpaywall_landing"):
                    has_fulltext = True
                    break

    # (b) OpenAlex — more PDF locations + abstract reconstruction.
    if not has_fulltext or not rec.get("abstract"):
        oa = openalex_info(doi, email, session)
        if not has_fulltext and try_pdf(oa["pdf_urls"], "openalex"):
            has_fulltext = True
        if not rec.get("abstract") and oa["abstract"]:
            rec["abstract"] = oa["abstract"]
            rec["abstract_source"] = "openalex"

    # (c) Europe PMC — full-text JATS XML for OA papers, abstract otherwise.
    if not has_fulltext or not rec.get("abstract"):
        ep = europepmc_info(doi, session)
        if not has_fulltext and ep.get("is_oa") and ep.get("pmcid"):
            url = EUROPEPMC_XML_URL.format(pmcid=ep["pmcid"])
            if download_xml(url, xml_path, session):
                rec["fulltext_xml"] = xml_path.name
                has_fulltext = True
        if not rec.get("abstract") and ep.get("abstract"):
            rec["abstract"] = ep["abstract"]
            rec["abstract_source"] = "europepmc"

    # (d) Crossref link array — publisher-deposited full-text URLs.
    if not has_fulltext:
        has_fulltext = try_pdf(crossref_links, "crossref_link")

    rec.setdefault("pdf_file", None)
    rec.setdefault("fulltext_xml", None)


def needs_retry(rec: dict, pdf_dir: Path, xml_dir: Path) -> bool:
    """A manifest entry is retried if it lacks full text on disk or an abstract."""
    has_pdf = bool(rec.get("pdf_file")) and (pdf_dir / rec["pdf_file"]).exists()
    has_xml = bool(rec.get("fulltext_xml")) and (xml_dir / rec["fulltext_xml"]).exists()
    return bool(rec.get("doi")) and not ((has_pdf or has_xml) and rec.get("abstract"))


def coverage_summary(records: list[dict], pdf_dir: Path, xml_dir: Path) -> str:
    n_pdf = sum(1 for r in records
                if r.get("pdf_file") and (pdf_dir / r["pdf_file"]).exists())
    n_xml = sum(1 for r in records
                if not (r.get("pdf_file") and (pdf_dir / r["pdf_file"]).exists())
                and r.get("fulltext_xml") and (xml_dir / r["fulltext_xml"]).exists())
    n_abs = sum(1 for r in records
                if not (r.get("pdf_file") and (pdf_dir / r["pdf_file"]).exists())
                and not (r.get("fulltext_xml") and (xml_dir / r["fulltext_xml"]).exists())
                and r.get("abstract"))
    n_meta = len(records) - n_pdf - n_xml - n_abs
    return (f"{len(records)} studies: {n_pdf + n_xml} full-text "
            f"({n_pdf} PDF + {n_xml} XML), {n_abs} abstract-only, "
            f"{n_meta} metadata-only")


# ------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--doi-list", required=True, help="era_doi_list.csv (era_code,doi,...)")
    ap.add_argument("--out", default="../corpus", help="corpus output directory")
    ap.add_argument("--email", default=os.environ.get("UNPAYWALL_EMAIL"),
                    help="contact email for the Unpaywall/OpenAlex polite pools "
                         "(or set UNPAYWALL_EMAIL)")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between studies")
    ap.add_argument("--limit", type=int, default=0, help="stop after N studies (0 = all)")
    ap.add_argument("--retry-missing", action="store_true",
                    help="reprocess manifest entries lacking full text and/or "
                         "abstract via the full OA fallback chain; rewrite the "
                         "manifest in place")
    args = ap.parse_args()

    if not args.email:
        sys.exit("ERROR: Unpaywall requires a contact email. Set UNPAYWALL_EMAIL or pass --email.")

    out = Path(args.out)
    pdf_dir = out / "pdfs"
    xml_dir = out / "xml"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    xml_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.jsonl"
    done = load_manifest(manifest_path)

    session = requests.Session()
    session.headers["User-Agent"] = UA.format(email=args.email)

    if args.retry_missing:
        if not done:
            sys.exit(f"ERROR: --retry-missing needs an existing manifest at {manifest_path}.")
        backup = manifest_path.with_suffix(".jsonl.bak")
        backup.write_text(manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
        records = list(done.values())
        targets = [r for r in records if needs_retry(r, pdf_dir, xml_dir)]
        print(f"{len(records)} manifest entries, {len(targets)} to retry "
              f"(missing full text and/or abstract). Backup: {backup.name}")
        def rewrite_manifest() -> None:
            """Persist all records atomically — called on finish AND on crash/^C."""
            tmp = manifest_path.with_suffix(".jsonl.tmp")
            with open(tmp, "w", encoding="utf-8") as mf:
                for r in records:
                    mf.write(json.dumps(r, ensure_ascii=False) + "\n")
            os.replace(tmp, manifest_path)

        target_ids = {id(r) for r in targets}
        n = 0
        try:
            for rec in records:
                # finding #2: clean already-stored metadata even when not retried
                for k in ("title", "container", "abstract", "journal"):
                    if rec.get(k):
                        rec[k] = clean_html(rec[k])
                if id(rec) not in target_ids:
                    continue
                n += 1
                try:
                    acquire(rec, args.email, session, pdf_dir, xml_dir)
                    # v1 records may have pdf_file without provenance fields —
                    # .get() everywhere so a status print can never crash a run.
                    got = ("PDF:" + rec.get("pdf_source", "existing")
                           if rec.get("pdf_file")
                           else "XML:" + rec.get("pdf_source", "europepmc")
                           if rec.get("fulltext_xml")
                           else "abstract:" + rec.get("abstract_source", "existing")
                           if rec.get("abstract")
                           else rec.get("oa_status", "?"))
                except Exception as exc:  # one bad study must not kill the run
                    got = f"ERROR ({exc})"
                print(f"[{n}/{len(targets)}] {rec['era_code']}  {got}")
                if n % 25 == 0:
                    rewrite_manifest()  # checkpoint every 25 studies
                if args.limit and n >= args.limit:
                    break
                time.sleep(args.sleep)
        finally:
            rewrite_manifest()  # progress survives crashes and Ctrl+C
        print("\nDone. " + coverage_summary(records, pdf_dir, xml_dir))
        return 0

    with open(args.doi_list, newline="", encoding="utf-8") as f:
        studies = list(csv.DictReader(f))

    new = 0
    with open(manifest_path, "a", encoding="utf-8") as mf:
        for s in studies:
            code, doi = s["era_code"].strip(), (s.get("doi") or "").strip()
            if code in done:
                continue
            rec: dict = {"era_code": code,
                         "doi": doi if doi and doi.upper() != "NA" else None,
                         "author": s.get("author"), "journal": s.get("journal")}
            acquire(rec, args.email, session, pdf_dir, xml_dir)
            mf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            mf.flush()
            new += 1
            got = ("PDF" if rec.get("pdf_file") else "XML" if rec.get("fulltext_xml")
                   else rec.get("oa_status", "?"))
            print(f"[{new}] {code}  {got}")
            if args.limit and new >= args.limit:
                break
            time.sleep(args.sleep)

    records = list(load_manifest(manifest_path).values())
    print("\nDone. " + coverage_summary(records, pdf_dir, xml_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
