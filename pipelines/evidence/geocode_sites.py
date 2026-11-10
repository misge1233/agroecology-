#!/usr/bin/env python3
"""Geocode the study sites of Habtamu's rows, with a human check (brief E2 B2; roadmap 5.5).

Per study (one record per Habtamu ``study_id``): DOI, title, the sheet's
``Agroecological_Zone`` text and country, and, when the paper is in the Tier 1
corpus, its text (first 4 pages plus any "Materials and methods" / "Study area"
section found by heading match).

Extraction
  * always: a regex pass for decimal and DMS coordinates and the sentences that
    contain "located", "study area", "district", "woreda", "zone";
  * with ``--llm``: one constrained JSON call per study (cached in
    ``data/evidence/review/geocode_llm_cache.jsonl``, git-ignored):
    ``{sites: [{name, admin, lat, lon, coordinate_source, quote}], confidence}``.
    Only paper text and public bibliographic labels are sent, never dataset
    numbers. A stated coordinate is kept only if the regex pass finds the same
    coordinate in the text (within 0.05 degrees) and it lies in the country's
    bounding box; a quote is marked verified only if it occurs in the text.

Resolution
  * stated coordinates win (bbox from ``countries/<cc>.yaml``, else a world table
    derived from GeoNames ``cities500``);
  * otherwise site names are resolved against GeoNames (``ET.txt`` for Ethiopia,
    ``cities500.txt`` elsewhere; feature classes P and A), best match by name
    similarity and admin agreement;
  * ``loc_precision``: ``site`` (stated coordinates or a populated place),
    ``district`` (ADM2/ADM3 centroid), ``country`` (nothing resolved);
  * fallback when no named site resolves: the admin units the text names, then
    the tokens of the sheet's ``Agroecological_Zone`` text, always at ``district``
    precision and lower confidence (``geonames_admin`` / ``geonames_zone_text``).

Outputs: ``data/evidence/review/geocoding_review.csv`` (one row per study) and
``geocoding_review.html`` (Leaflet map). ``--apply-geocoding`` copies the
resolved rows to ``data/evidence/hab_geocoding.csv`` (``geocoded_llm_checked``
for accepted rows, ``geocoded_llm_unchecked`` for the rest), which
``build_evidence_store.py`` applies to the HAB rows; the store, cards and
registry are then rebuilt.

GeoNames (CC BY 4.0, https://www.geonames.org/) files are downloaded once into
``pipelines/evidence/cache/geonames/`` (git-ignored); URLs in
``pipelines/evidence/geonames_manifest.json``.

Usage::

    python pipelines/evidence/geocode_sites.py [--llm] [--limit N] [--dry-run]
    python pipelines/evidence/geocode_sites.py --apply-geocoding
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import html as _html
import json
import logging
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.evidence import common  # noqa: E402

logger = logging.getLogger(__name__)

GEONAMES_DIR = Path(__file__).resolve().parent / "cache" / "geonames"
REVIEW_CSV = common.EVIDENCE_DIR / "review" / "geocoding_review.csv"
REVIEW_HTML = common.EVIDENCE_DIR / "review" / "geocoding_review.html"
APPLIED_CSV = common.EVIDENCE_DIR / "hab_geocoding.csv"
LLM_CACHE = common.EVIDENCE_DIR / "review" / "geocode_llm_cache.jsonl"
CORPUS = common.REPO_ROOT / "rag" / "corpus"
SITE_KM = 25.0
LLM_TEXT_CHARS = 12000
LLM_CONCURRENCY = 6
REVIEW_COLUMNS = ["study_id", "doi", "country", "site_name", "admin", "lat", "lon", "loc_precision", "method",
                  "confidence", "quote", "quote_verified", "geonames_id", "n_sites", "other_sites", "text_source",
                  "accepted", "reviewer", "date"]
GEONAMES_COLUMNS = ["geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude", "feature_class",
                    "feature_code", "country_code", "cc2", "admin1", "admin2", "admin3", "admin4", "population",
                    "elevation", "dem", "timezone", "modified"]
SITE_WORDS = re.compile(r"\blocated\b|study area|study site|experimental site|\bdistrict\b|\bworeda\b|\bzone\b|"
                        r"\bkebele\b|\bvillage\b|\bwatershed\b|research (?:station|center|centre)", re.I)
METHODS_HEAD = re.compile(r"(materials?\s+and\s+methods?|study\s+(?:area|site)s?|description\s+of\s+the\s+study"
                          r"|experimental\s+site|site\s+description)", re.I)


# ------------------------------------------------------------ coordinates
_DEG = r"(?:°|º|˚|o(?=\s*\d)|\s+deg(?:rees)?)"
_MIN = r"(?:'|′|’|`|\s*min)"
_SEC = r"(?:\"|″|''|”|\s*sec)"
DMS_RE = re.compile(
    rf"(?P<d>\d{{1,3}})\s*{_DEG}\s*(?:(?P<m>\d{{1,2}}(?:[.,]\d+)?)\s*{_MIN}?\s*)?"
    rf"(?:(?P<s>\d{{1,2}}(?:[.,]\d+)?)\s*{_SEC}?\s*)?(?P<h>[NSEW])\b"
)
DEC_HEMI_RE = re.compile(r"(?P<v>\d{1,3}\.\d+)\s*(?:°|º|˚)?\s*(?P<h>[NSEW])\b")
HEMI_DEC_RE = re.compile(r"\b(?P<h>[NSEW])\s*(?P<v>\d{1,3}\.\d+)\s*(?:°|º|˚)?")
LATLON_WORD_RE = re.compile(r"\b(?P<k>lat(?:itude)?|long?(?:itude)?)\s*(?:of|:|=)?\s*(?P<v>-?\d{1,3}\.\d+)", re.I)


def _norm_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    return t.replace("′", "'").replace("″", '"')


def parse_coordinates(text: str) -> list[tuple[float, float, str]]:
    """``(lat, lon, matched_text)`` pairs found in ``text`` (DMS, decimal with hemisphere, lat/long words)."""
    t = _norm_text(text)
    cands: list[tuple[int, int, float, str, str]] = []  # (start, end, value, axis, text)
    for m in DMS_RE.finditer(t):
        if m.start() > 0 and (t[m.start() - 1].isdigit() or t[m.start() - 1] == "."):
            continue  # "7.05° N" must not also yield "05° N"
        d = float(m.group("d"))
        mi = float((m.group("m") or "0").replace(",", "."))
        s = float((m.group("s") or "0").replace(",", "."))
        if mi >= 60 or s >= 60:
            continue
        v = d + mi / 60 + s / 3600
        h = m.group("h")
        cands.append((m.start(), m.end(), -v if h in "SW" else v, "lat" if h in "NS" else "lon", m.group(0)))
    for rx in (DEC_HEMI_RE, HEMI_DEC_RE):
        for m in rx.finditer(t):
            if rx is DEC_HEMI_RE and m.start() > 0 and (t[m.start() - 1].isdigit() or t[m.start() - 1] == "."):
                continue
            v, h = float(m.group("v")), m.group("h")
            cands.append((m.start(), m.end(), -v if h in "SW" else v, "lat" if h in "NS" else "lon", m.group(0)))
    for m in LATLON_WORD_RE.finditer(t):
        axis = "lat" if m.group("k").lower().startswith("lat") else "lon"
        cands.append((m.start(), m.end(), float(m.group("v")), axis, m.group(0)))
    # non-overlapping, leftmost-longest (DMS "9°02'N" beats a decimal reading inside it)
    cands.sort(key=lambda c: (c[0], -(c[1] - c[0])))
    hits: list[tuple[int, float, str, str]] = []
    last_end = -1
    for start, end, v, axis, txt in cands:
        if start >= last_end:
            hits.append((start, v, axis, txt))
            last_end = end
    pairs: list[tuple[float, float, str]] = []
    used: set[int] = set()
    for i, (p, v, axis, txt) in enumerate(hits):
        if i in used or axis != "lat":
            continue
        for j in range(i + 1, min(i + 4, len(hits))):
            p2, v2, axis2, txt2 = hits[j]
            if axis2 == "lon" and j not in used and p2 - p < 120:
                if -90 <= v <= 90 and -180 <= v2 <= 180:
                    pairs.append((round(v, 5), round(v2, 5), t[p:p2 + len(txt2)]))
                used.update({i, j})
                break
    return pairs


def site_sentences(text: str, max_n: int = 5) -> list[str]:
    """Sentences that describe where the study took place."""
    sents = re.split(r"(?<=[.!?])\s+", _norm_text(text))
    return [s.strip()[:400] for s in sents if SITE_WORDS.search(s)][:max_n]


# ------------------------------------------------------------------ bboxes
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def world_bboxes(geonames_dir: Path = GEONAMES_DIR) -> dict[str, tuple[float, float, float, float]]:
    """``cc -> (lat_min, lat_max, lon_min, lon_max)`` from GeoNames cities500 (padded 0.5 degree)."""
    path = geonames_dir / "cities500.txt"
    if not path.exists():
        return {}
    t = pd.read_csv(path, sep="\t", header=None, names=GEONAMES_COLUMNS, usecols=["latitude", "longitude",
                    "country_code"], dtype={"country_code": str}, keep_default_na=False, quoting=3)
    g = t.groupby("country_code").agg(lat_min=("latitude", "min"), lat_max=("latitude", "max"),
                                      lon_min=("longitude", "min"), lon_max=("longitude", "max"))
    return {cc: (r.lat_min - 0.5, r.lat_max + 0.5, r.lon_min - 0.5, r.lon_max + 0.5) for cc, r in g.iterrows()}


def country_bbox(cc: str | None) -> tuple[float, float, float, float] | None:
    """Bounding box of a country: ``countries/<cc>.yaml`` when present, else the GeoNames table."""
    if not cc:
        return None
    try:
        from pipelines.common.country_config import load_country

        b = load_country(cc, check_files=False).bbox
        return (b.lat_min, b.lat_max, b.lon_min, b.lon_max)
    except Exception:  # noqa: BLE001 - no config for this country
        return world_bboxes().get(cc)


def in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float] | None) -> bool:
    """True when the point lies inside ``bbox`` (or no bbox is known)."""
    if bbox is None:
        return True
    return bbox[0] <= lat <= bbox[1] and bbox[2] <= lon <= bbox[3]


# ---------------------------------------------------------------- gazetteer
def _fold(s: str) -> str:
    s = re.sub(r"['\u2019\u2018`\u02bc]", "", str(s or ""))  # "Dogu'a" == "Dogu\u2019a"
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(woreda|wereda|district|zone|kebele|village|town|city|region|regional state|province|county|"
               r"research (?:station|center|centre)|agricultural|watershed|catchment)\b", " ", s)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def _admin_agrees(admin_keys: list[str], a1: str) -> bool:
    """Fuzzy agreement of named admin units with a GeoNames admin-1 name ("Oromia" ~ "Oromiya")."""
    from rapidfuzz import fuzz

    if not a1:
        return False
    return any(a and (a in a1 or a1 in a or fuzz.ratio(a, a1) >= 85) for a in admin_keys)


@dataclass
class Gazetteer:
    """GeoNames places (classes P and A) for one country, indexed by folded name."""

    places: pd.DataFrame
    admin1: dict[str, str] = field(default_factory=dict)
    index: dict[str, list[int]] = field(default_factory=dict)

    @classmethod
    def build(cls, places: pd.DataFrame, admin1: dict[str, str] | None = None) -> "Gazetteer":
        """Index ``places`` (GeoNames columns) by name, asciiname and alternate names."""
        places = places[places["feature_class"].isin(["P", "A"])].reset_index(drop=True)
        index: dict[str, list[int]] = {}
        for i, r in places.iterrows():
            names = {r["name"], r["asciiname"], *str(r["alternatenames"] or "").split(",")}
            for n in names:
                k = _fold(n)
                if k and len(k) >= 3:
                    index.setdefault(k, []).append(i)
        return cls(places, admin1 or {}, index)

    def resolve(self, name: str, admin: list[str] | None = None, exact_only: bool = False) -> dict[str, Any] | None:
        """Best match for ``name``: exact folded match first, then fuzzy (ratio >= 85, or 92 for short names).

        Admin agreement breaks ties; a fuzzy match is rejected when the text names admin
        units and none of them agrees with the candidate's region ("Nairobi" must not
        become an Ethiopian "Ail Robi").
        """
        from rapidfuzz import fuzz, process

        key = _fold(name)
        if len(key) < 3:
            return None
        rows = self.index.get(key)
        score = 100.0
        fuzzy = False
        if not rows and exact_only:
            return None
        if not rows:
            fuzzy = True
            cutoff = 85 if len(key) >= 5 else 92  # "kenna" ~ "kena"; short names need a near-exact match
            hit = process.extractOne(key, list(self.index), scorer=fuzz.ratio, score_cutoff=cutoff)
            if not hit:
                return None
            rows, score = self.index[hit[0]], float(hit[1])
        admin_keys = [_fold(a) for a in admin or [] if a]

        def rank(i: int) -> tuple:
            r = self.places.loc[i]
            a1 = _fold(self.admin1.get(f"{r['country_code']}.{r['admin1']}", ""))
            agree = _admin_agrees(admin_keys, a1)
            code = str(r["feature_code"])
            kind = 0 if r["feature_class"] == "P" else (1 if code in ("ADM2", "ADM3", "ADM4") else 2)
            return (not agree, kind, -int(r["population"] or 0))

        best = sorted(rows, key=rank)[0]
        r = self.places.loc[best]
        code = str(r["feature_code"])
        if r["feature_class"] == "P":
            precision = "site"
        elif code in ("ADM2", "ADM3", "ADM4", "ADMD"):
            precision = "district"
        else:
            return None  # ADM1 or country-level: not a usable position
        a1 = self.admin1.get(f"{r['country_code']}.{r['admin1']}", "")
        agree = _admin_agrees(admin_keys, _fold(a1))
        if fuzzy and admin_keys and not agree:
            return None
        conf = (score / 100.0) * (1.0 if agree or not admin_keys else 0.8)
        return {"lat": float(r["latitude"]), "lon": float(r["longitude"]), "loc_precision": precision,
                "geonames_id": int(r["geonameid"]), "matched": r["name"], "admin1": a1,
                "confidence": round(conf, 3)}


def read_geonames(path: Path, country: str | None = None) -> pd.DataFrame:
    """Read a GeoNames dump (optionally only one country)."""
    t = pd.read_csv(path, sep="\t", header=None, names=GEONAMES_COLUMNS, dtype=str, keep_default_na=False,
                    quoting=3, usecols=["geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude",
                                        "feature_class", "feature_code", "country_code", "admin1", "population"])
    if country:
        t = t[t["country_code"] == country]
    t = t.copy()
    t["latitude"] = pd.to_numeric(t["latitude"])
    t["longitude"] = pd.to_numeric(t["longitude"])
    t["population"] = pd.to_numeric(t["population"], errors="coerce").fillna(0).astype(int)
    return t


@lru_cache(maxsize=1)
def _admin1(geonames_dir: Path = GEONAMES_DIR) -> dict[str, str]:
    path = geonames_dir / "admin1CodesASCII.txt"
    if not path.exists():
        return {}
    t = pd.read_csv(path, sep="\t", header=None, names=["code", "name", "ascii", "id"], dtype=str,
                    keep_default_na=False, quoting=3)
    return dict(zip(t["code"], t["ascii"]))


@lru_cache(maxsize=80)
def gazetteer_for(cc: str, geonames_dir: Path = GEONAMES_DIR) -> Gazetteer | None:
    """``ET.txt`` for Ethiopia (all P and A features), ``cities500.txt`` filtered elsewhere."""
    own = geonames_dir / f"{cc}.txt"
    path = own if own.exists() else geonames_dir / "cities500.txt"
    if not path.exists():
        logger.warning("GeoNames file missing for %s (%s); download it first", cc, path)
        return None
    return Gazetteer.build(read_geonames(path, cc), _admin1(geonames_dir))


# ------------------------------------------------------------------- studies
def _paper_text(rec: dict[str, Any]) -> tuple[str, str]:
    """(text, source) from the corpus: first 4 pages + methods/study-area section."""
    common.bootstrap_repo_path()
    pdf, xml = rec.get("pdf_file"), rec.get("fulltext_xml")
    if pdf and (CORPUS / "pdfs" / pdf).exists() and pdf.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(CORPUS / "pdfs" / pdf))
            pages = []
            for page in reader.pages[:12]:
                try:
                    pages.append(page.extract_text() or "")
                except Exception:  # noqa: BLE001
                    pages.append("")
            head = "\n".join(pages[:4])
            rest = "\n".join(pages[4:])
            m = METHODS_HEAD.search(rest)
            section = rest[m.start(): m.start() + 4000] if m else ""
            return " ".join((head + "\n" + section).split()), "pdf"
        except Exception as exc:  # noqa: BLE001
            logger.debug("pdf read failed for %s: %s", pdf, exc)
    if xml and (CORPUS / "xml" / xml).exists():
        from rag.ingest.parse_and_chunk import extract_xml_text

        full = extract_xml_text(CORPUS / "xml" / xml)
        m = METHODS_HEAD.search(full)
        return full[:9000] + (" " + full[m.start(): m.start() + 4000] if m else ""), "xml"
    if rec.get("abstract"):
        return rec["abstract"], "abstract"
    return "", "none"


def study_records() -> list[dict[str, Any]]:
    """One record per Habtamu study with its sheet text and, when available, the paper text."""
    from pipelines.evidence import fetch_habtamu_papers as fhp
    from pipelines.evidence import load_habtamu, schema

    hab = schema.coerce(load_habtamu.load()[0])
    manifest = {r["era_code"]: r for r in fhp.read_manifest() if r.get("source") == "HAB"}
    out = []
    for sid, g in hab.groupby("study_id", sort=True):
        rec = manifest.get(sid, {})
        zones = [z for z in g["ctx_reported_aez"].dropna().unique()]
        evid = [e for e in g["evidence_text"].dropna().unique() if SITE_WORDS.search(e)]
        out.append({
            "study_id": sid, "doi": next(iter(g["doi"].dropna()), None) or rec.get("doi"),
            "country": next(iter(g["country"].dropna()), None),
            "title": rec.get("title") or rec.get("matched_title"),
            "zone_text": "; ".join(zones[:3]), "evidence_sentences": evid[:3], "manifest": rec,
        })
    return out


# ---------------------------------------------------------------------- LLM
SITE_PROMPT = (
    "You extract the locations of field studies from scientific text. Return JSON only: "
    '{"sites": [{"name": str, "admin": [str], "lat": number|null, "lon": number|null, '
    '"coordinate_source": "stated"|"none", "quote": str}], "confidence": number}. '
    "List only places where the experiment or data collection took place (village, kebele, district/woreda, "
    "research station, watershed), most specific first. 'admin' lists the higher administrative units named "
    "in the text (zone, region, province). Give lat/lon only when the text states them, as decimal degrees "
    "(south and west negative), with coordinate_source 'stated'; otherwise null and 'none'. 'quote' is one "
    "sentence copied verbatim from the text that names the site. If no site is named, return an empty list."
)


def llm_messages(rec: dict[str, Any], text: str) -> list[dict[str, str]]:
    """Constrained prompt for one study (paper text and public labels only)."""
    head = f"Title: {rec.get('title') or 'n/a'}\nCountry: {rec.get('country') or 'n/a'}\n"
    if rec.get("zone_text"):
        head += f"Study zone as recorded: {rec['zone_text']}\n"
    return [{"role": "system", "content": SITE_PROMPT},
            {"role": "user", "content": head + "\nTEXT:\n" + (text[:LLM_TEXT_CHARS] or "(no paper text)")}]


def _cache_key(rec: dict[str, Any], text: str) -> str:
    return hashlib.sha256((rec["study_id"] + "\x1f" + text[:LLM_TEXT_CHARS]).encode()).hexdigest()[:24]


def read_llm_cache(path: Path = LLM_CACHE) -> dict[str, Any]:
    """Cached answers keyed by study/text hash."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["key"]] = rec
    return out


def parse_site_answer(raw: str) -> dict[str, Any]:
    """Validated LLM answer (bad JSON -> no sites)."""
    try:
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return {"sites": [], "confidence": 0.0}
    sites = []
    for s in data.get("sites") or []:
        if not isinstance(s, dict) or not str(s.get("name") or "").strip():
            continue
        lat, lon = s.get("lat"), s.get("lon")
        ok = isinstance(lat, (int, float)) and isinstance(lon, (int, float))
        sites.append({"name": str(s["name"]).strip()[:120],
                      "admin": [str(a)[:80] for a in (s.get("admin") or []) if str(a).strip()][:4],
                      "lat": float(lat) if ok else None, "lon": float(lon) if ok else None,
                      "coordinate_source": "stated" if ok and s.get("coordinate_source") == "stated" else "none",
                      "quote": str(s.get("quote") or "")[:400]})
    try:
        conf = float(data.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    return {"sites": sites[:5], "confidence": max(0.0, min(conf, 1.0))}


async def _ask(jobs: list[tuple[str, list[dict]]]) -> dict[str, str]:
    common.bootstrap_repo_path()
    backend = str(common.REPO_ROOT / "app" / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.config import get_settings
    from app.services.openai_chat import OPENAI_CHAT_COMPLETIONS_URL, OPENAI_CHAT_MODEL, make_client

    settings = get_settings()
    if not settings.openai_api_key:
        raise SystemExit("--llm needs OPENAI_API_KEY in app/backend/.env")
    out: dict[str, str] = {}
    sem = asyncio.Semaphore(LLM_CONCURRENCY)
    async with make_client(settings.openai_api_key, settings.openai_timeout_seconds) as client:
        async def one(key: str, messages: list[dict]) -> None:
            async with sem:
                for attempt in range(4):
                    r = await client.post(OPENAI_CHAT_COMPLETIONS_URL, json={
                        "model": OPENAI_CHAT_MODEL, "messages": messages, "temperature": 0,
                        "response_format": {"type": "json_object"}})
                    if r.status_code in (429, 500, 502, 503) and attempt < 3:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    r.raise_for_status()
                    out[key] = r.json()["choices"][0]["message"]["content"]
                    return

        await asyncio.gather(*(one(k, m) for k, m in jobs))
    return out


# --------------------------------------------------------------- resolution
def _verified(quote: str, text: str) -> bool:
    q = " ".join(_norm_text(quote).lower().split())
    return bool(q) and q[:120] in " ".join(_norm_text(text).lower().split())


def resolve_study(rec: dict[str, Any], text: str, answer: dict[str, Any] | None,
                  gazetteer: Gazetteer | None) -> dict[str, Any]:
    """Best position for one study (see module docstring); every row carries a quote."""
    cc = rec.get("country")
    bbox = country_bbox(cc)
    regex_pairs = [(la, lo, q) for la, lo, q in parse_coordinates(text) if in_bbox(la, lo, bbox)]
    sentences = site_sentences(text)
    row: dict[str, Any] = {c: "" for c in REVIEW_COLUMNS}
    row.update(study_id=rec["study_id"], doi=rec.get("doi") or "", country=cc or "",
               text_source=rec.get("_text_source", "none"), n_sites=0)
    sites = (answer or {}).get("sites") or []
    row["n_sites"] = len(sites)
    best: dict[str, Any] | None = None
    # 1. stated coordinates confirmed by the regex pass
    for s in sites:
        if s["coordinate_source"] == "stated" and s["lat"] is not None:
            match = next((p for p in regex_pairs if abs(p[0] - s["lat"]) < 0.05 and abs(p[1] - s["lon"]) < 0.05), None)
            if match and in_bbox(s["lat"], s["lon"], bbox):
                best = {"site_name": s["name"], "admin": "; ".join(s["admin"]), "lat": s["lat"], "lon": s["lon"],
                        "loc_precision": "site", "method": "stated_coordinates_llm_regex", "confidence": 0.95,
                        "quote": s["quote"] or match[2]}
                break
    if best is None and regex_pairs and not sites:
        la, lo, q = regex_pairs[0]
        best = {"site_name": "", "admin": "", "lat": la, "lon": lo, "loc_precision": "site",
                "method": "stated_coordinates_regex", "confidence": 0.8, "quote": q}
    # 2. names against GeoNames
    if best is None and gazetteer is not None:
        for s in sites:
            hit = gazetteer.resolve(s["name"], s["admin"])
            if hit and in_bbox(hit["lat"], hit["lon"], bbox):
                best = {"site_name": s["name"], "admin": "; ".join(s["admin"]), "lat": hit["lat"], "lon": hit["lon"],
                        "loc_precision": hit["loc_precision"], "method": f"geonames:{hit['matched']}",
                        "confidence": round(hit["confidence"] * max((answer or {}).get("confidence", 0.6), 0.5), 3),
                        "quote": s["quote"], "geonames_id": hit["geonames_id"]}
                if regex_pairs:  # a stated coordinate nearby confirms the place
                    la, lo, _ = regex_pairs[0]
                    if haversine_km(la, lo, hit["lat"], hit["lon"]) <= SITE_KM:
                        best["confidence"] = min(1.0, best["confidence"] + 0.1)
                break
    # 3. fallback: the named admin units, then the sheet's zone tokens, at district precision
    if best is None and gazetteer is not None:
        candidates: list[tuple[str, str, str]] = []  # (name, quote, method)
        for s in sites:
            for a in s["admin"]:
                candidates.append((a, s["quote"], "geonames_admin"))
        for tok in re.split(r"[;,()/]|\band\b", rec.get("zone_text") or ""):
            if tok.strip():
                candidates.append((tok.strip(), f"Recorded zone: {rec.get('zone_text')}", "geonames_zone_text"))
        for name, quote, method in candidates:
            hit = gazetteer.resolve(name, [], exact_only=True)
            if hit and in_bbox(hit["lat"], hit["lon"], bbox):
                best = {"site_name": name, "admin": "", "lat": hit["lat"], "lon": hit["lon"],
                        "loc_precision": "district", "method": f"{method}:{hit['matched']}",
                        "confidence": round(hit["confidence"] * 0.6, 3), "quote": quote,
                        "geonames_id": hit["geonames_id"]}
                break
    if best is None:
        quote = (sites[0]["quote"] if sites else "") or (sentences[0] if sentences else "") \
            or (f"Recorded zone: {rec['zone_text']}" if rec.get("zone_text") else "") \
            or f"No site statement found; country {cc or 'unknown'}"
        best = {"site_name": sites[0]["name"] if sites else "", "admin": "; ".join(sites[0]["admin"]) if sites else "",
                "lat": "", "lon": "", "loc_precision": "country", "method": "unresolved", "confidence": 0.0,
                "quote": quote}
    row.update(best)
    row["quote_verified"] = "yes" if _verified(str(row["quote"]), text + " " + rec.get("zone_text", "")) else "no"
    row["other_sites"] = "; ".join(s["name"] for s in sites if s["name"] != row["site_name"])[:300]
    return row


def run(llm: bool = False, limit: int = 0, dry_run: bool = False) -> pd.DataFrame:
    """Build the review sheet and the map; returns the sheet."""
    recs = study_records()
    if limit:
        recs = recs[:limit]
    texts = {}
    for r in recs:
        text, src = _paper_text(r["manifest"])
        if r.get("evidence_sentences"):
            text = text + " " + " ".join(r["evidence_sentences"]) if text else " ".join(r["evidence_sentences"])
        r["_text_source"] = src
        texts[r["study_id"]] = text
    answers: dict[str, dict[str, Any]] = {}
    if llm:
        cache = read_llm_cache()
        jobs, keys = [], {}
        for r in recs:
            k = _cache_key(r, texts[r["study_id"]])
            keys[r["study_id"]] = k
            if k not in cache and (texts[r["study_id"]].strip() or r.get("zone_text") or r.get("title")):
                jobs.append((k, llm_messages(r, texts[r["study_id"]])))
        if jobs and not dry_run:
            model = _model()
            raw = asyncio.run(_ask(jobs))
            LLM_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with open(LLM_CACHE, "a", encoding="utf-8", newline="\n") as fh:
                for k, txt in raw.items():
                    rec = {"key": k, "model": model, "answer": parse_site_answer(txt)}
                    cache[k] = rec
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        for r in recs:
            hit = cache.get(keys[r["study_id"]])
            if hit:
                answers[r["study_id"]] = hit["answer"]
    rows = []
    for r in recs:
        gz = gazetteer_for(r["country"]) if r.get("country") else None
        rows.append(resolve_study(r, texts[r["study_id"]], answers.get(r["study_id"]), gz))
    sheet = pd.DataFrame(rows, columns=REVIEW_COLUMNS)
    old = pd.read_csv(REVIEW_CSV, dtype=str, keep_default_na=False) if REVIEW_CSV.exists() else None
    if old is not None and not old.empty:  # carry reviewer decisions over
        prev = old.set_index("study_id")
        for c in ("accepted", "reviewer", "date"):
            sheet[c] = [prev[c].get(s, "") if s in prev.index else "" for s in sheet["study_id"]]
    if not dry_run:
        REVIEW_CSV.parent.mkdir(parents=True, exist_ok=True)
        sheet.to_csv(REVIEW_CSV, index=False, lineterminator="\n", encoding="utf-8")
        common.write_text(REVIEW_HTML, review_map(sheet))
    return sheet


def _model() -> str:
    common.bootstrap_repo_path()
    backend = str(common.REPO_ROOT / "app" / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.services.openai_chat import OPENAI_CHAT_MODEL

    return OPENAI_CHAT_MODEL


# ----------------------------------------------------------------------- map
def review_map(sheet: pd.DataFrame) -> str:
    """Leaflet page: one marker per geocoded study, popup with the quote."""
    pts = []
    for r in sheet.itertuples():
        if str(r.lat) in ("", "nan"):
            continue
        pts.append({"lat": float(r.lat), "lon": float(r.lon), "study": r.study_id, "site": r.site_name,
                    "precision": r.loc_precision, "method": r.method, "conf": r.confidence,
                    "quote": str(r.quote)[:400], "accepted": r.accepted})
    data = json.dumps(pts, ensure_ascii=False).replace("</", "<\\/")
    n_total = len(sheet)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Geocoding review</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root {{ --bg:#fff; --fg:#1d2a1f; --muted:#5b6b5d; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141a15; --fg:#e8efe8; --muted:#9fb09f; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:14px/1.4 system-ui, sans-serif; }}
header {{ padding:10px 16px; }} header p {{ margin:2px 0; color:var(--muted); }}
#map {{ height: calc(100vh - 70px); }}
.q {{ font-style: italic; max-width: 320px; }}
</style></head><body>
<header><strong>Habtamu study sites: geocoding review</strong>
<p>{len(pts)} of {n_total} studies placed. Green: site, amber: district. Check each quote, then set
<code>accepted</code> in <code>geocoding_review.csv</code>.</p></header>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const pts = {data};
const map = L.map('map').setView([9, 39], 4);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom: 18,
  attribution: '&copy; OpenStreetMap contributors; places: GeoNames (CC BY 4.0)'}}).addTo(map);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
const layer = L.featureGroup();
for (const p of pts) {{
  const color = p.precision === 'site' ? '#2e7d32' : '#e0a100';
  L.circleMarker([p.lat, p.lon], {{radius: 6, color, fillOpacity: 0.8}})
    .bindPopup(`<b>${{esc(p.study)}}</b><br>${{esc(p.site)}} (${{esc(p.precision)}}, ${{esc(p.method)}}, conf ${{esc(p.conf)}})`
      + `<div class="q">&ldquo;${{esc(p.quote)}}&rdquo;</div>` + (p.accepted ? `accepted: ${{esc(p.accepted)}}` : ''))
    .addTo(layer);
}}
layer.addTo(map);
if (pts.length) map.fitBounds(layer.getBounds(), {{padding: [20, 20]}});
</script></body></html>
"""


# --------------------------------------------------------------------- apply
def apply_geocoding(sheet_path: Path = REVIEW_CSV, out_path: Path = APPLIED_CSV) -> pd.DataFrame:
    """Resolved rows -> ``hab_geocoding.csv`` with the right ``loc_method`` (checked = accepted yes)."""
    sheet = pd.read_csv(sheet_path, dtype=str, keep_default_na=False)
    placed = sheet[(sheet["lat"] != "") & sheet["loc_precision"].isin(["site", "district", "exact"])]
    placed = placed[placed["accepted"].str.lower() != "no"]  # a rejected position is never applied
    out = pd.DataFrame({
        "study_id": placed["study_id"], "lat": placed["lat"], "lon": placed["lon"],
        "loc_precision": placed["loc_precision"], "site_name": placed["site_name"],
        "loc_method": ["geocoded_llm_checked" if a.lower() == "yes" else "geocoded_llm_unchecked"
                       for a in placed["accepted"]],
        "method": placed["method"], "quote": placed["quote"],
    })
    out.to_csv(out_path, index=False, lineterminator="\n", encoding="utf-8")
    return out


def apply_to_frame(df: pd.DataFrame, path: Path = APPLIED_CSV, log: common.RuleLog | None = None) -> pd.DataFrame:
    """Write applied geocoding into HAB rows (``build_evidence_store`` calls this)."""
    if not path.exists():
        return df
    geo = pd.read_csv(path, dtype=str, keep_default_na=False).set_index("study_id")
    out = df.copy()
    hit = out["study_id"].isin(geo.index)
    for col in ("lat", "lon"):
        out.loc[hit, col] = pd.to_numeric(out.loc[hit, "study_id"].map(geo[col]))
    out.loc[hit, "loc_precision"] = out.loc[hit, "study_id"].map(geo["loc_precision"])
    out.loc[hit, "loc_method"] = out.loc[hit, "study_id"].map(geo["loc_method"])
    if log is not None:
        for method, n in out.loc[hit, "loc_method"].value_counts().items():
            log.parse(f"geocoding_applied_{method}", int(n))
    return out


def coverage(sheet: pd.DataFrame) -> dict[str, Any]:
    """Coverage by precision overall and for Ethiopian studies (and Ethiopian DOIs)."""
    def share(s: pd.DataFrame) -> dict[str, Any]:
        n = len(s)
        vc = s["loc_precision"].value_counts().to_dict()
        good = int(s["loc_precision"].isin(["site", "district"]).sum())
        return {"n": n, "by_precision": vc, "site_or_district": good, "share": round(good / n, 4) if n else 0.0}

    et = sheet[sheet["country"] == "ET"]
    et_doi = et[et["doi"] != ""].drop_duplicates("doi")
    return {"all": share(sheet), "ET_studies": share(et), "ET_dois": share(et_doi),
            "with_quote": int((sheet["quote"].astype(str).str.strip() != "").sum()),
            "quote_verified": int((sheet["quote_verified"] == "yes").sum())}


def main(argv: list[str] | None = None) -> int:
    """CLI."""
    ap = argparse.ArgumentParser(description="Geocode Habtamu study sites (review sheet + map).")
    ap.add_argument("--llm", action="store_true", help="constrained LLM site extraction (cached)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="build in memory, write nothing (no LLM calls)")
    ap.add_argument("--apply-geocoding", action="store_true",
                    help="copy resolved rows to data/evidence/hab_geocoding.csv and rebuild store and registry")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    common.setup_logging(args.verbose)
    if args.apply_geocoding:
        out = apply_geocoding()
        print(f"applied: {len(out)} studies -> {APPLIED_CSV} ({out['loc_method'].value_counts().to_dict()})")
        if args.dry_run:
            return 0
        from pipelines.evidence import build_evidence_store, build_registry

        build_evidence_store.build()
        build_registry.main(["--country", "ET"])
        return 0
    sheet = run(llm=args.llm, limit=args.limit, dry_run=args.dry_run)
    print(json.dumps(coverage(sheet), indent=2))
    if not args.dry_run:
        print(f"wrote {REVIEW_CSV} and {REVIEW_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
