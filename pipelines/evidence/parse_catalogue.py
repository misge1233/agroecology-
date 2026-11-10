#!/usr/bin/env python3
"""Parse the Agroecology+ Solutions Catalogue (docx) into structured entries.

Input ``data/raw/catalogue/Catalogue 1-30 for dashboard testing.docx``
(partner document, git-ignored; opened read-only with python-docx, never
modified). Output ``data/taxonomy/catalogue_entries.json`` and ``.csv``.

The document is irregular: titles appear as ``1. Agroecology solution name:
...``, ``6. Solution name: ...``, ``11. Solution Name Level fanya juu``,
``16. Stone-faced level soil bund`` (no label) and one auto-numbered title with
no number in its text (entry 13); field labels vary in case and punctuation
(``Solution at a glance (Short description:``), some values continue on the
next paragraph, and photo captions sit in paragraphs or in a table. Parsing:

1. walk the body in order (paragraphs and table cells);
2. a block is a **title** when the next non-empty block starts with
   ``Category``; its number comes from the text, else previous + 1;
3. every other block is split on the known field labels (a label may also
   appear mid-paragraph after a colon-less run, so labels followed by ``:`` are
   split anywhere in the text);
4. unlabelled blocks after a title are photo captions when they mention a
   photo/credit/"by", else a continuation of the last field.

Photos are not extracted (captions only). ``key_problems`` are normalised to
canonical problem terms (:data:`PROBLEM_SYNONYMS`) that ``challenges.csv``
links to (``catalogue_problem_terms``).

Usage::

    python pipelines/evidence/parse_catalogue.py [--input DOCX] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.evidence import common  # noqa: E402

logger = logging.getLogger(__name__)

RAW_PATH = common.DATA_DIR / "raw" / "catalogue" / "Catalogue 1-30 for dashboard testing.docx"
OUT_JSON = common.TAXONOMY_DIR / "catalogue_entries.json"
OUT_CSV = common.TAXONOMY_DIR / "catalogue_entries.csv"
EXPECTED_ENTRIES = 30

#: field -> label regex (matched case-insensitively at the start of a segment).
FIELD_LABELS: list[tuple[str, str]] = [
    ("category", r"category"),
    ("target_farming_system", r"target\s+farming\s+system"),
    ("suitable_land_use_and_agroecology", r"suitable\s+land\s+use(?:\s+type)?(?:\s+and\s+agro-?ecology)?"),
    ("scaling_stage", r"current\s+scaling\s+stage|scaling\s+stage"),
    ("scale", r"scale\s+to\s+be\s+used"),
    ("description", r"solution\s+at\s+a\s+glance\s*(?:\(\s*short\s+description\s*\)?)?"),
    ("key_problems", r"key\s+problems?\s+to\s+be\s+addressed"),
    ("principles", r"key\s+agro-?ecology\s+principles?\s+that\s+apply"),
    ("benefits", r"key\s+benefits?\s*(?:/\s*evidence)?"),
    ("evidence_base", r"evidence\s+base"),
    ("limitations", r"limitations?"),
]
LIST_FIELDS = ("principles", "benefits", "evidence_base")
_LABEL_ANY = "|".join(f"(?:{rx})" for _, rx in FIELD_LABELS)
_START_RE = re.compile(rf"^\s*(?P<label>{_LABEL_ANY})\s*(?::\s*)*", re.I)
_INLINE_RE = re.compile(rf"(?<=[.;\s])(?P<label>{_LABEL_ANY})\s*:", re.I)
_TITLE_RE = re.compile(
    r"^\s*(?P<num>\d{1,3})\s*[.)]?\s*(?:agro-?ecology\s+)?(?:solution\s+name\s*:?\s*)?(?P<name>.*)$", re.I
)
_NAME_LABEL_RE = re.compile(r"^\s*(?:agro-?ecology\s+)?solution\s+name\s*:?\s*", re.I)
_CAPTION_RE = re.compile(r"\bphoto\b|\bcredit\b|\bcredi\b|\bby\s+[A-Z]", re.I)

#: raw problem phrase (normalised) -> canonical problem term. Unknown phrases pass through.
PROBLEM_SYNONYMS = {
    "soil erosion": "soil erosion",
    "reduces erosion": "soil erosion",
    "erosion": "soil erosion",
    "gully erosion": "gully erosion",
    "soil erosion in gully form": "gully erosion",
    "landslide": "landslide",
    "soil fertility depletion": "soil fertility depletion",
    "soil nutrient depletion": "soil nutrient depletion",
    "nutrient depletion": "soil nutrient depletion",
    "nutrient losses": "soil nutrient depletion",
    "nutrient loss": "soil nutrient depletion",
    "moisture stress": "soil moisture stress",
    "soil moisture stress": "soil moisture stress",
    "conserve moisture": "soil moisture stress",
    "excessive runoff": "excessive runoff",
    "excessive surface runoff": "excessive runoff",
    "water shortage": "water scarcity",
    "water scarcity": "water scarcity",
    "feed shortage": "feed shortage",
    "deforestation": "deforestation",
    "pollution": "water pollution",
    "water pollution": "water pollution",
    "degraded and steep hillsides": "degraded hillsides",
    "steep hillsides": "degraded hillsides",
    "degraded hillsides": "degraded hillsides",
    "stabilize soil": "soil erosion",
    "run off": "excessive runoff",
    "gullies": "gully erosion",
    "water table": "water scarcity",
    "wood shortage": "fuelwood shortage",
    "fuelwood shortage": "fuelwood shortage",
    "ghg emissions": "ghg emissions",
}
#: Unmatched phrases longer than this many words are prose, not a problem term:
#: kept in ``key_problems_raw`` only.
MAX_UNMATCHED_WORDS = 4


@dataclass
class CatalogueEntry:
    """One catalogue solution."""

    catalogue_id: str
    number: int
    name: str
    category: str | None = None
    target_farming_system: str | None = None
    suitable_land_use_and_agroecology: str | None = None
    scaling_stage: str | None = None
    scale: str | None = None
    description: str | None = None
    key_problems: list[str] = field(default_factory=list)
    key_problems_raw: str | None = None
    principles: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    evidence_base: list[str] = field(default_factory=list)
    limitations: str | None = None
    photo_captions: list[str] = field(default_factory=list)
    source_file: str = ""
    extracted_on: str = ""


def iter_blocks(doc) -> Iterator[tuple[str, str]]:
    """Yield ``(kind, text)`` for paragraphs and table cells in body order."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield "p", " ".join(Paragraph(child, doc).text.split())
        elif tag == "tbl":
            for row in Table(child, doc).rows:
                seen = set()
                for cell in row.cells:
                    if id(cell._tc) in seen:
                        continue
                    seen.add(id(cell._tc))
                    for para in cell.paragraphs:
                        yield "cell", " ".join(para.text.split())


def split_fields(text: str) -> list[tuple[str | None, str]]:
    """Split one block into ``(field or None, value)`` segments on known labels."""
    segments: list[tuple[str | None, str]] = []
    m = _START_RE.match(text)
    if m and _field_for(m.group("label")):
        current, rest = _field_for(m.group("label")), text[m.end():]
    else:
        current, rest = None, text
    while True:
        im = _INLINE_RE.search(rest)
        if not im or not _field_for(im.group("label")):
            segments.append((current, rest.strip()))
            break
        segments.append((current, rest[: im.start()].strip()))
        current, rest = _field_for(im.group("label")), rest[im.end():]
    return [(f, v.strip(" :")) for f, v in segments if f is not None or v.strip(" :.")]


def _field_for(label: str) -> str | None:
    for name, rx in FIELD_LABELS:
        if re.fullmatch(rx, label.strip(), flags=re.I):
            return name
    return None


def _clean_name(text: str) -> tuple[int | None, str]:
    m = _TITLE_RE.match(text)
    if m:
        num = int(m.group("num"))
        name = _NAME_LABEL_RE.sub("", m.group("name"))
    else:
        num, name = None, _NAME_LABEL_RE.sub("", text)
    return num, " ".join(name.split()).strip(" :.")


def _split_list(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"\s*[,;]\s*|\s+and\s+(?=[a-z])", value)
    out = []
    for p in parts:
        p = p.strip(" .:-")
        if p and p.lower() not in {x.lower() for x in out}:
            out.append(p)
    return out


def normalise_problems(value: str | None) -> list[str]:
    """Split the "key problems" text and map each phrase to a canonical problem term."""
    out: list[str] = []
    for p in _split_list(value):
        key = " ".join(re.sub(r"[^a-z\s]", " ", p.lower()).split())
        term = PROBLEM_SYNONYMS.get(key)
        if term is None:
            for phrase, t in PROBLEM_SYNONYMS.items():
                if re.search(rf"\b{re.escape(phrase)}\b", key):
                    term = t
                    break
        if term is None and len(key.split()) <= MAX_UNMATCHED_WORDS:
            term = key
        if term and term not in out:
            out.append(term)
    return out


def parse_blocks(blocks: list[tuple[str, str]], source_file: str = "", extracted_on: str = "") -> list[CatalogueEntry]:
    """Parse ordered blocks into entries (see module docstring)."""
    blocks = [(k, t) for k, t in blocks if t and t.strip(" .")]
    entries: list[CatalogueEntry] = []
    cur: CatalogueEntry | None = None
    last_field: str | None = None
    for i, (kind, text) in enumerate(blocks):
        if re.fullmatch(r"references?", text.strip(), flags=re.I):
            cur = None
            break
        nxt = blocks[i + 1][1] if i + 1 < len(blocks) else ""
        if kind == "p" and _START_RE.match(nxt) and _field_for(_START_RE.match(nxt).group("label")) == "category" \
                and not _START_RE.match(text):
            num, name = _clean_name(text)
            num = num if num is not None else (entries[-1].number + 1 if entries else 1)
            cur = CatalogueEntry(catalogue_id=f"CAT_{num:02d}", number=num, name=name,
                                 source_file=source_file, extracted_on=extracted_on)
            entries.append(cur)
            last_field = None
            continue
        if cur is None:
            continue
        for fld, value in split_fields(text):
            if fld is None:
                if kind == "cell" or _CAPTION_RE.search(value):
                    cur.photo_captions.append(value)
                elif last_field:
                    _append(cur, last_field, value)
                continue
            _append(cur, fld, value)
            last_field = fld
    for e in entries:
        e.key_problems = normalise_problems(e.key_problems_raw)
    return entries


def _append(entry: CatalogueEntry, fld: str, value: str) -> None:
    if not value:
        return
    if fld == "key_problems":
        entry.key_problems_raw = f"{entry.key_problems_raw} {value}".strip() if entry.key_problems_raw else value
    elif fld in LIST_FIELDS:
        getattr(entry, fld).extend(x for x in _split_list(value) if x not in getattr(entry, fld))
    else:
        old = getattr(entry, fld)
        setattr(entry, fld, f"{old} {value}".strip() if old else value)


def parse(path: Path = RAW_PATH) -> list[CatalogueEntry]:
    """Parse the catalogue docx (read-only)."""
    import docx

    if not path.exists():
        raise FileNotFoundError(f"catalogue not found: {path}")
    doc = docx.Document(str(path))
    today = _dt.date.today().isoformat()
    return parse_blocks(list(iter_blocks(doc)), source_file=path.name, extracted_on=today)


def check(entries: list[CatalogueEntry], expected: int | None = EXPECTED_ENTRIES) -> None:
    """Assert the expected number of entries, consecutive numbers, a name and a category each."""
    if expected is not None and len(entries) != expected:
        raise AssertionError(f"catalogue: {len(entries)} entries parsed, expected {expected}")
    nums = [e.number for e in entries]
    if nums != list(range(1, len(entries) + 1)):
        raise AssertionError(f"catalogue numbers not consecutive: {nums}")
    bad = [e.catalogue_id for e in entries if not e.name or not e.category]
    if bad:
        raise AssertionError(f"catalogue entries without name or category: {bad}")


def to_frame(entries: list[CatalogueEntry]) -> pd.DataFrame:
    """Flat table (lists joined with ``; ``)."""
    rows = []
    for e in entries:
        d = asdict(e)
        for k, v in d.items():
            if isinstance(v, list):
                d[k] = "; ".join(v)
        rows.append(d)
    return pd.DataFrame(rows)


def write(entries: list[CatalogueEntry], json_path: Path = OUT_JSON, csv_path: Path = OUT_CSV) -> None:
    """Write the JSON and CSV outputs (UTF-8, LF)."""
    common.write_text(json_path, json.dumps([asdict(e) for e in entries], indent=2, ensure_ascii=False) + "\n")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    to_frame(entries).to_csv(csv_path, index=False, lineterminator="\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI."""
    ap = argparse.ArgumentParser(description="Parse the Agroecology+ Solutions Catalogue docx.")
    ap.add_argument("--input", type=Path, default=RAW_PATH)
    ap.add_argument("--dry-run", action="store_true", help="parse and print, write nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    common.setup_logging(args.verbose)
    entries = parse(args.input)
    check(entries)
    for e in entries:
        missing = [f for f in ("target_farming_system", "suitable_land_use_and_agroecology", "scaling_stage",
                               "scale", "description", "limitations") if not getattr(e, f)]
        print(f"{e.catalogue_id} {e.name!r} [{e.category}] problems={e.key_problems} "
              f"captions={len(e.photo_captions)}" + (f" MISSING={missing}" if missing else ""))
    if not args.dry_run:
        write(entries)
        print(f"wrote {OUT_JSON} and {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
