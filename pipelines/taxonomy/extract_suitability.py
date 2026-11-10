#!/usr/bin/env python3
"""Extract suitability statements for practices (rules only; brief E2 C4, roadmap 7).

Scans the guideline chunks (``rag/corpus/guidelines/chunks.jsonl``) and the
catalogue entries (``data/taxonomy/catalogue_entries.json``) sentence by
sentence. A statement is kept when the same sentence names a practice (its
``practices.csv`` name or one of its non-rejected aliases, or, for a catalogue
entry, the entry's own practice) and contains one of:

* a slope range or bound (``3-15%``, ``above 50%``) in a sentence about slope;
* a rainfall band or bound in mm in a sentence about rainfall;
* a land-use term (cultivated, cropland, grazing, forest, degraded, hillside, ...);
* an agro-ecological belt name (Kolla, Weyna Dega, Dega, Wurch, Berha, with
  their moisture prefixes);
* a soil depth (cm, deep/shallow) or stoniness statement.

Output ``data/taxonomy/review/suitability_review.csv`` (``practice_id, attribute,
operator, value, unit, doc_id, page, quote, source, accepted, reviewer, date``).
No LLM; **nothing is applied** in E2 (E5 consumes accepted rows).

Usage::

    python pipelines/taxonomy/extract_suitability.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.evidence import common  # noqa: E402
from pipelines.taxonomy import taxonomy_io as tio  # noqa: E402

logger = logging.getLogger(__name__)

GUIDELINE_CHUNKS = common.REPO_ROOT / "rag" / "corpus" / "guidelines" / "chunks.jsonl"
CATALOGUE = common.TAXONOMY_DIR / "catalogue_entries.json"
OUT = tio.REVIEW_DIR / "suitability_review.csv"
COLUMNS = ["practice_id", "attribute", "operator", "value", "unit", "doc_id", "page", "quote", "source",
           "accepted", "reviewer", "date"]
MIN_NAME_CHARS = 5

_NUM = r"(\d+(?:\.\d+)?)"
_RANGE = rf"{_NUM}\s*(?:%\s*)?(?:-|–|—|to)\s*{_NUM}"
SLOPE_RANGE = re.compile(rf"{_RANGE}\s*%")
SLOPE_GT = re.compile(rf"(?:above|more than|greater than|over|exceeding|steeper than|>)\s*{_NUM}\s*%", re.I)
SLOPE_LT = re.compile(rf"(?:below|less than|under|up to|not exceed\w*|gentler than|<)\s*{_NUM}\s*%", re.I)
RAIN_RANGE = re.compile(rf"{_RANGE}\s*mm", re.I)
RAIN_GT = re.compile(rf"(?:above|more than|greater than|over|exceeding|>)\s*{_NUM}\s*mm", re.I)
RAIN_LT = re.compile(rf"(?:below|less than|under|up to|<)\s*{_NUM}\s*mm", re.I)
DEPTH_CM = re.compile(rf"(?:soil depth|deep|depth)[^.]{{0,40}}?{_NUM}\s*cm|{_NUM}\s*cm[^.]{{0,20}}?(?:soil )?depth", re.I)
DEPTH_WORD = re.compile(r"\b(deep|shallow)\s+soils?\b", re.I)
STONY = re.compile(r"\b(stony|rocky|stones? (?:are|is) (?:available|abundant)|availability of stones?)\b", re.I)
LAND_USE = {
    "cultivated": r"cultivated|cropland|crop land|farm ?land",
    "grazing": r"grazing|pasture|rangeland",
    "forest": r"forest|woodland",
    "degraded": r"degraded",
    "hillside": r"hillside|steep slopes?",
    "homestead": r"homestead|backyard",
    "exclosure": r"exclosure|area closure",
}
_MOIST = r"(?:(?:dry|moist|wet)\s+)?"
BELTS = re.compile(rf"\b({_MOIST}(?:weyna\s*dega|woina\s*dega|kolla|qolla|dega|wurch|berha|bereha))\b", re.I)


def sentences(text: str) -> list[str]:
    """Sentence split (also on bullet/semicolon breaks common in manuals)."""
    flat = " ".join(str(text or "").split())
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\s+[•▪●]\s+", flat) if len(s.strip()) > 15]


def practice_names(tax: tio.Taxonomy) -> list[tuple[re.Pattern, str]]:
    """``(pattern, practice_id)`` from practice names and usable aliases, longest first."""
    pairs: dict[str, str] = {}
    for r in tax.practices.itertuples():
        if r.status != "merged":
            pairs.setdefault(r.name_en.lower(), r.practice_id)
    for r in tax.practice_aliases.itertuples():
        if str(r.accepted).lower() != "no" and r.practice_id:
            pairs.setdefault(str(r.alias).lower(), r.practice_id)
    out = []
    for name, pid in sorted(pairs.items(), key=lambda kv: -len(kv[0])):
        name = " ".join(name.split())
        if len(name) < MIN_NAME_CHARS:
            continue
        out.append((re.compile(r"(?<![a-z])" + re.escape(name).replace(r"\ ", r"[\s-]+") + r"s?(?![a-z])", re.I), pid))
    return out


def statements(sentence: str) -> list[dict[str, str]]:
    """Suitability attributes stated in one sentence (no practice check here)."""
    out: list[dict[str, str]] = []
    low = sentence.lower()
    if "slope" in low:
        for m in SLOPE_RANGE.finditer(sentence):
            out.append({"attribute": "slope_pct", "operator": "between", "value": f"{m.group(1)}-{m.group(2)}", "unit": "%"})
        for m in SLOPE_GT.finditer(sentence):
            out.append({"attribute": "slope_pct", "operator": ">", "value": m.group(1), "unit": "%"})
        for m in SLOPE_LT.finditer(sentence):
            out.append({"attribute": "slope_pct", "operator": "<", "value": m.group(1), "unit": "%"})
    if "rain" in low or "precipitation" in low:
        for m in RAIN_RANGE.finditer(sentence):
            out.append({"attribute": "rainfall_mm", "operator": "between", "value": f"{m.group(1)}-{m.group(2)}", "unit": "mm"})
        for m in RAIN_GT.finditer(sentence):
            out.append({"attribute": "rainfall_mm", "operator": ">", "value": m.group(1), "unit": "mm"})
        for m in RAIN_LT.finditer(sentence):
            out.append({"attribute": "rainfall_mm", "operator": "<", "value": m.group(1), "unit": "mm"})
    for m in DEPTH_CM.finditer(sentence):
        out.append({"attribute": "soil_depth_cm", "operator": "mention", "value": m.group(1) or m.group(2), "unit": "cm"})
    for m in DEPTH_WORD.finditer(sentence):
        out.append({"attribute": "soil_depth", "operator": "in", "value": m.group(1).lower(), "unit": ""})
    if STONY.search(sentence):
        out.append({"attribute": "stoniness", "operator": "in", "value": "stony", "unit": ""})
    for term, rx in LAND_USE.items():
        if re.search(rf"\b(?:{rx})\b", low):
            out.append({"attribute": "land_use", "operator": "in", "value": term, "unit": ""})
    for m in BELTS.finditer(sentence):
        out.append({"attribute": "aez_belt", "operator": "in", "value": " ".join(m.group(1).title().split()), "unit": ""})
    return out


def _rows(text: str, names: list[tuple[re.Pattern, str]], doc_id: str, page: Any, source: str,
          fixed_practice: str | None = None) -> Iterable[dict[str, Any]]:
    for s in sentences(text):
        stmts = statements(s)
        if not stmts:
            continue
        pids = [fixed_practice] if fixed_practice else []
        for rx, pid in names:
            if pid not in pids and rx.search(s):
                pids.append(pid)
        for pid in pids:
            for st in stmts:
                yield {"practice_id": pid, **st, "doc_id": doc_id, "page": page, "quote": s[:500],
                       "source": source, "accepted": "", "reviewer": "", "date": ""}


def extract(tax: tio.Taxonomy | None = None, chunks_path: Path = GUIDELINE_CHUNKS,
            catalogue_path: Path = CATALOGUE) -> pd.DataFrame:
    """All suitability rows (deduplicated)."""
    tax = tax or tio.Taxonomy.load()
    names = practice_names(tax)
    cat_practice = {}
    for r in tax.practice_aliases.itertuples():
        if r.source == "CAT":
            cat_practice[r.alias] = r.practice_id
    rows: list[dict[str, Any]] = []
    if chunks_path.exists():
        for line in chunks_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            c = json.loads(line)
            if c.get("language") == "am":
                continue  # English rules only
            rows.extend(_rows(c["text"], names, c["doc_id"], c.get("page"), "guidelines"))
    if catalogue_path.exists():
        for e in json.loads(catalogue_path.read_text(encoding="utf-8")):
            pid = cat_practice.get(e["name"])
            for fld in ("suitable_land_use_and_agroecology", "scale", "description", "limitations"):
                rows.extend(_rows(e.get(fld) or "", names, e["catalogue_id"], "", f"catalogue:{fld}",
                                  fixed_practice=pid))
    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty:
        return df
    return df.drop_duplicates(["practice_id", "attribute", "operator", "value", "doc_id", "page"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    """CLI."""
    ap = argparse.ArgumentParser(description="Rules-only suitability statements -> review sheet.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    common.setup_logging(args.verbose)
    df = extract()
    if OUT.exists() and not df.empty:  # keep reviewer decisions
        old = pd.read_csv(OUT, dtype=str, keep_default_na=False)
        key = ["practice_id", "attribute", "operator", "value", "doc_id", "page"]
        old_k = old.assign(page=old["page"].astype(str)).set_index(key)
        for c in ("accepted", "reviewer", "date"):
            df[c] = [old_k[c].get(tuple(map(str, k)), "") if tuple(map(str, k)) in old_k.index else ""
                     for k in df[key].astype(str).itertuples(index=False)]
    print(f"suitability statements: {len(df):,} rows, {df['practice_id'].nunique() if len(df) else 0} practices")
    if len(df):
        print(df.groupby(["attribute"]).size().to_string())
    if not args.dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(OUT, index=False, lineterminator="\n", encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
