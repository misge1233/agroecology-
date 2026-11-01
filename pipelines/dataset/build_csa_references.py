"""Build ``data/processed/csa_study_references.json`` (U9 / C3).

Dataset rows with ``source == "CSA"`` carry ``Study_No_ = "CSA_<n>"``; the UI
cited them as "Dataset study #CSA_18" with no bibliographic entry. The raw
compilation sheet ``data/raw/CSA_practices_by_Agroecology.xlsx`` (Adimassu et
al. CSA studies, one row per observation) has a ``Reference`` column next to
``Study_No_`` — this script turns it into a study -> reference map.

Caveats handled honestly (nothing is invented):
- The sheet is a shapefile/DBF export: ``Reference`` strings are cut at 255
  characters. Truncated strings are flagged ``"truncated": true`` and the
  parsed fields keep only what is actually there.
- Some references are short forms ("Burayu et al"); they are resolved to the
  full reference with the same first-author surname when exactly one exists in
  the sheet, otherwise kept as-is with only ``authors`` / ``year`` parsed.
- 26 study numbers are attached to >1 reference in the sheet. The reference
  with the most observation rows becomes the primary entry; the others are
  listed under ``alternatives`` and the entry is marked ``"ambiguous": true``.
- No DOIs are present in the sheet; ``doi`` is filled only by an exact
  (normalised) title match against the ERA corpus manifest
  (``rag/corpus/manifest.jsonl``), never guessed.

A ``"_compilation"`` entry always carries the compilation's own citation so a
study absent from the map can be cited as "<compilation>, study <n>".

Pure stdlib (the xlsx is read as zipped XML; no openpyxl needed).

Usage:
    python pipelines/dataset/build_csa_references.py [--dry-run]
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

log = logging.getLogger("build_csa_references")

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_XLSX = REPO_ROOT / "data" / "raw" / "CSA_practices_by_Agroecology.xlsx"
ERA_MANIFEST = REPO_ROOT / "rag" / "corpus" / "manifest.jsonl"
OUT_PATH = REPO_ROOT / "data" / "processed" / "csa_study_references.json"
DBF_TEXT_LIMIT = 255

# The with/without study compilation (Study_No_, With, without, unit,
# Agro_zone) is the evidence base of the Adimassu et al. (2024) Farming System
# meta-analysis; title/DOI/handle verbatim from its CGSpace record
# (hdl 10568/151652). The two framework papers in rag/corpus/pdfs/ are the
# companion publications of the same AICCRA work (expert prioritisation; no
# meta-analysis) and are listed under ``related``.
COMPILATION: dict[str, Any] = {
    "authors": "Adimassu, Z.; Tibebe, D.; Abera, W.; Tamene, L.",
    "year": 2024,
    "title": ("Integrating meta-analysis and experts’ knowledge for "
              "prioritizing climate-smart agricultural practices in Ethiopian"),
    "journal": "Farming System 2(4): 100110",
    "doi": "10.1016/j.farsys.2024.100110",
    "handle_url": "https://cgspace.cgiar.org/handle/10568/151652",
    "citation": ("Adimassu, Z., Tibebe, D., Abera, W., & Tamene, L. (2024). "
                 "Integrating meta-analysis and experts’ knowledge for "
                 "prioritizing climate-smart agricultural practices in "
                 "Ethiopian. Farming System, 2(4), 100110. "
                 "https://doi.org/10.1016/j.farsys.2024.100110"),
    "related": [
        ("Adimassu, Z., Tamene, L., Tibebe, D., Ebrahim, M., & Abera, W. "
         "(2024). Identification and prioritization of context-specific "
         "climate smart agricultural (CSA) practices in Ethiopia: a framework "
         "approach. Environmental Research Communications, 6, 065007. "
         "https://doi.org/10.1088/2515-7620/ad54a1"),
        ("Adimassu, Z., Tamene, L., Tibebe, D., Ebrahim, M., & Abera, W. "
         "(2023). Identification and Prioritization of Context-Specific "
         "Climate-Smart Agricultural Practices in Major Agro-ecological Zones "
         "of Ethiopia. AICCRA Working Paper No. 11."),
    ],
}

# "Authors (2009). Title. Journal, 104(1), 185-191."  (APA-like)
_APA_RE = re.compile(
    r"^(?P<authors>.+?)\s*\((?P<year>(?:19|20)\d{2})[a-z]?(?:,[^)]*)?\)\.?\s*"
    r"(?P<rest>.+)$", re.S)
# "Authors 2020. Title. Journal ..." / "Authors, 2005. Title ..."
_YEAR_DOT_RE = re.compile(
    r"^(?P<authors>[^0-9]{3,200}?)[,.]?\s+(?P<year>(?:19|20)\d{2})[a-z]?\.+\s+"
    r"(?P<rest>.+)$", re.S)
# Short forms: "Burayu et al", "Rockstrom et al 2009", "Kebede and Yaekob 2006"
_SHORT_RE = re.compile(
    r"^(?P<authors>[^\d(]+?)[,.]?\s*(?P<year>(?:19|20)\d{2})?\.?\s*$")
SHORT_FORM_MAX = 60
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s,]+")


def _norm(s: str) -> str:
    """Accent-folded, lower-cased alphanumerics (for matching only)."""
    folded = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", folded.lower()).strip()


# ------------------------------------------------------------------ xlsx read
def read_sheet(path: Path) -> list[dict[str, str | None]]:
    """Rows of the first worksheet as header -> value dicts (stdlib only)."""
    with zipfile.ZipFile(path) as z:
        shared = z.read("xl/sharedStrings.xml").decode("utf-8")
        strings = [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
                   for si in re.findall(r"<si>(.*?)</si>", shared, re.S)]
        sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    grid: list[dict[str, str | None]] = []
    for rm in re.finditer(r"<row[^>]*>(.*?)</row>", sheet, re.S):
        row: dict[str, str | None] = {}
        for cm in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)',
                              rm.group(1), re.S):
            col, attrs, inner = cm.groups()
            v = re.search(r"<v>(.*?)</v>", inner or "", re.S)
            if 't="s"' in attrs and v:
                row[col] = strings[int(v.group(1))]
            else:
                row[col] = html.unescape(v.group(1)) if v else None
        grid.append(row)
    header = grid[0]
    return [{header[c]: r.get(c) for c in header if header[c]} for r in grid[1:]]


# ------------------------------------------------------------------- parsing
def parse_reference(ref: str) -> dict[str, Any]:
    """Split one reference string into authors/year/title/journal (pure).

    Only fields actually present are filled; the raw string is always kept
    under ``citation``.
    """
    raw_len = len(ref)
    ref = re.sub(r"\s+", " ", ref).strip()
    out: dict[str, Any] = {"authors": None, "year": None, "title": None,
                           "journal": None, "doi": None, "citation": ref,
                           # DBF export cut: ~254-255 chars, no closing period
                           "truncated": (raw_len >= DBF_TEXT_LIMIT - 10
                                         and not ref.endswith(".")),
                           "short_form": False}
    doi_m = _DOI_RE.search(ref)
    if doi_m:  # a DOI printed inside the reference itself
        out["doi"] = doi_m.group(0).rstrip(".,;)")
    m = _APA_RE.match(ref) or _YEAR_DOT_RE.match(ref)
    if m:
        out["authors"] = m.group("authors").strip().rstrip(",.")
        out["year"] = int(m.group("year"))
        rest = m.group("rest").strip()
        parts = re.split(r"(?<=[a-z0-9)?])\.\s+", rest, maxsplit=1)
        out["title"] = parts[0].strip().rstrip(".") or None
        if len(parts) > 1:
            journal = re.split(r",\s*\d|\.\s*$", parts[1], maxsplit=1)[0]
            out["journal"] = journal.strip().rstrip(".,") or None
        return out
    if len(ref) <= SHORT_FORM_MAX:
        out["short_form"] = True
        s = _SHORT_RE.match(ref.replace(" at al", " et al"))
        if s:
            out["authors"] = s.group("authors").strip().rstrip(",")
            if s.group("year"):
                out["year"] = int(s.group("year"))
    return out  # long but unparseable: citation string only


def first_surname(authors: str | None, short_form: bool) -> str:
    """First-author surname, lower-cased ('' if unknown).

    Full APA form "Temesgen, M., ..." -> text before the first comma.
    Short form "Ermias Aynekulu et al" / "Burayu et al" / "Kebede and
    Yaekob" -> last word of the first name group (Ethiopian names are
    given-name first in the short forms, surname-first in the APA list).
    """
    if not authors:
        return ""
    if not short_form:
        return _norm(authors.split(",", 1)[0])
    head = re.split(r",|\bet al\b|\bat al\b|\band\b|&", authors)[0].split()
    return _norm(head[-1]) if head else ""


def era_doi_index(path: Path) -> dict[str, str]:
    """Normalised title -> DOI from the ERA corpus manifest (may be empty)."""
    index: dict[str, str] = {}
    if not path.exists():
        return index
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("title") and rec.get("doi"):
            index[_norm(rec["title"])] = rec["doi"]
    return index


def build(rows: list[dict[str, str | None]],
          doi_index: dict[str, str]) -> tuple[dict[str, Any], dict[str, int]]:
    """Study -> reference map plus counts (pure — testable)."""
    per_study: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        sid, ref = r.get("Study_No_"), (r.get("Reference") or "").strip()
        if sid and ref:
            per_study[str(int(float(sid)))][ref] += 1

    parsed = {ref: parse_reference(ref)
              for refs in per_study.values() for ref in refs}
    # Resolve short forms to a unique full reference by first-author surname.
    full_by_surname: dict[str, list[str]] = defaultdict(list)
    for ref, p in parsed.items():
        if not p["short_form"]:
            full_by_surname[first_surname(p["authors"], False)].append(ref)

    def resolved(ref: str) -> dict[str, Any]:
        p = dict(parsed[ref])
        if p["short_form"]:
            cands = full_by_surname.get(first_surname(p["authors"], True), [])
            cands = [c for c in cands if not p["year"] or parsed[c]["year"] == p["year"]]
            # Variant spellings of one paper count once (same normalised title).
            if cands and len({_norm(parsed[c]["title"] or c) for c in cands}) == 1:
                full = dict(parsed[cands[0]])
                full["resolved_from"] = ref
                p = full
        if p.get("title") and not p.get("doi"):
            p["doi"] = doi_index.get(_norm(p["title"]))
        return p

    out: dict[str, Any] = {}
    n_ambiguous = n_short = n_doi = 0
    for sid in sorted(per_study, key=int):
        refs = [ref for ref, _ in per_study[sid].most_common()]
        entry = resolved(refs[0])
        if len(refs) > 1:
            entry["ambiguous"] = True
            entry["alternatives"] = [resolved(r)["citation"] for r in refs[1:]]
            n_ambiguous += 1
        n_short += 1 if entry.get("short_form") else 0
        n_doi += 1 if entry.get("doi") else 0
        out[f"CSA_{sid}"] = entry
    counts = {"studies": len(out), "ambiguous": n_ambiguous,
              "unresolved_short_form": n_short, "with_doi": n_doi,
              "truncated": sum(1 for e in out.values() if e.get("truncated"))}
    return out, counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--xlsx", type=Path, default=RAW_XLSX)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    studies, counts = build(read_sheet(args.xlsx), era_doi_index(ERA_MANIFEST))
    log.info("CSA study references: %s", json.dumps(counts))
    payload = {
        "_about": {
            "description": ("Study_No_ (CSA_<n>) -> bibliographic reference "
                            "for dataset rows with source == 'CSA'."),
            "provenance": ("Reference column of data/raw/CSA_practices_by_"
                           "Agroecology.xlsx (Adimassu et al. CSA compilation); "
                           "built by pipelines/dataset/build_csa_references.py"),
            "caveats": ("Reference strings are cut at 255 chars in the source "
                        "(truncated: true); ambiguous: true = the study number "
                        "carries >1 reference in the source sheet; doi only "
                        "from an exact title match to the ERA corpus."),
            "counts": counts,
        },
        "_compilation": COMPILATION,
        **studies,
    }
    if args.dry_run:
        log.info("--dry-run: not writing %s", args.out)
        return 0
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    log.info("Wrote %d study entries -> %s", len(studies), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
