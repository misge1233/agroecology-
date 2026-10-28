#!/usr/bin/env python3
"""Translation review workflow (U1 → U2).

Three catalogs hold translatable strings:

* ``messages/{en,am,om}.json``      — the UI (next-intl)
* ``src/i18n/glossary.ts``          — data-contract display names (families,
                                      indicators, belts, crop groups, labels,
                                      the 44 practice components)
* ``app/backend/app/i18n/{am,om}.py`` — texts the API itself produces

Commands (run from the repo root or app/frontend):

    python scripts/translation_status.py                   # regenerate docs/i18n/TRANSLATION_STATUS.md
    python scripts/translation_status.py --export review.csv
    python scripts/translation_status.py --import review.csv

``--export`` writes one row per key — glossary terms first, because they
appear on every screen — with the columns
``source,key,en,am,om,status_am,status_om``. A reviewer edits the ``am``/``om``
cells and sets a status to ``reviewed``; ``--import`` writes the text back into
the three catalogs and records a fingerprint of every reviewed string in
``messages/review-status.json``. Tests (``src/i18n/review-status.test.ts`` and
``app/backend/tests/test_translation_review.py``) fail if a reviewed string is
later changed without going through this workflow, so a sign-off can never be
silently overwritten.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import OrderedDict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve()
FRONTEND = HERE.parents[1]
ROOT = FRONTEND.parents[1]
BACKEND = ROOT / "app" / "backend"
MESSAGES_DIR = FRONTEND / "messages"
GLOSSARY = FRONTEND / "src" / "i18n" / "glossary.ts"
STATUS_FILE = MESSAGES_DIR / "review-status.json"
OUT_MD = ROOT / "docs" / "i18n" / "TRANSLATION_STATUS.md"

LANGS = ("am", "om")
GLOSSARY_TABLES = (
    "FAMILIES", "FAMILIES_SHORT", "FAMILIES_BLURB", "INDICATORS", "INDICATOR_NOUNS",
    "AEZ_BELTS", "CROP_GROUPS", "CONFIDENCE", "CONFIDENCE_MEANING", "TIERS",
    "SOURCE_MODES", "SOURCE_MODES_TOOLTIP", "COMPONENTS",
)
SRC_MESSAGES = "messages"
SRC_GLOSSARY = "glossary"
SRC_BACKEND = "backend"


def fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------------- readers
def flatten(d: dict, prefix: str = "") -> "OrderedDict[str, str]":
    out: "OrderedDict[str, str]" = OrderedDict()
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out


def read_messages() -> dict[str, "OrderedDict[str, str]"]:
    out = {}
    for lang in ("en", *LANGS):
        out[lang] = flatten(json.loads((MESSAGES_DIR / f"{lang}.json").read_text(encoding="utf-8"), object_pairs_hook=OrderedDict))
    return out


_ENTRY_RE = re.compile(r'^[ ]{2}"?([^"\n:]+?)"?: \{(.*?)\n?[ ]*\},?$', re.M | re.S)
_VAL_RE = re.compile(r'\b(en|am|om): "((?:[^"\\]|\\.)*)"')


def _ts_unescape(s: str) -> str:
    return json.loads(f'"{s}"')


def _ts_escape(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)[1:-1]


def read_glossary() -> "OrderedDict[str, dict[str, str]]":
    """{ 'TABLE::key': {en, am, om} } in file order."""
    src = GLOSSARY.read_text(encoding="utf-8")
    out: "OrderedDict[str, dict[str, str]]" = OrderedDict()
    for table in GLOSSARY_TABLES:
        m = re.search(rf"export const {table}[^=]*=\s*\{{(.*?)\n\}};", src, re.S)
        if not m:
            raise SystemExit(f"glossary table {table} not found")
        for mm in _ENTRY_RE.finditer(m.group(1)):
            vals = {k: _ts_unescape(v) for k, v in _VAL_RE.findall(mm.group(2))}
            out[f"{table}::{mm.group(1)}"] = vals
    return out


def read_backend() -> dict[str, "OrderedDict[str, str]"]:
    sys.path.insert(0, str(BACKEND))
    from app.i18n import am, en, om  # noqa: E402

    tables = {"en": en.STRINGS, "am": am.STRINGS, "om": om.STRINGS}
    return {lang: OrderedDict(tables[lang]) for lang in tables}


def read_status() -> dict:
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    return {}


def write_status(status: dict) -> None:
    STATUS_FILE.write_text(json.dumps(status, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


# ----------------------------------------------------------------- rows
def collect_rows():
    """[(source, key, {en, am, om})] — glossary first, then UI, then backend."""
    rows = []
    for key, vals in read_glossary().items():
        rows.append((SRC_GLOSSARY, key, vals))
    msgs = read_messages()
    for key in msgs["en"]:
        rows.append((SRC_MESSAGES, key, {lang: msgs[lang].get(key, "") for lang in ("en", *LANGS)}))
    be = read_backend()
    for key in be["en"]:
        rows.append((SRC_BACKEND, key, {lang: be[lang].get(key, "") for lang in ("en", *LANGS)}))
    return rows


def status_of(status: dict, source: str, key: str, lang: str, current: str) -> str:
    entry = status.get(f"{source}::{key}", {}).get(lang)
    if not entry:
        return "machine-draft"
    if entry.get("sha1") == fingerprint(current):
        return "reviewed"
    return "changed-since-review"


# ----------------------------------------------------------------- writers
def write_messages_value(lang: str, key: str, value: str) -> None:
    path = MESSAGES_DIR / f"{lang}.json"
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    node = data
    parts = key.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, OrderedDict())
    node[parts[-1]] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_glossary_value(lang: str, table_key: str, value: str) -> None:
    table, key = table_key.split("::", 1)
    src = GLOSSARY.read_text(encoding="utf-8")
    m = re.search(rf"(export const {table}[^=]*=\s*\{{)(.*?)(\n\}};)", src, re.S)
    if not m:
        raise SystemExit(f"glossary table {table} not found")
    body = m.group(2)
    found = False

    def repl_entry(mm: re.Match) -> str:
        nonlocal found
        if mm.group(1) != key:
            return mm.group(0)
        found = True
        inner = mm.group(0)
        pattern = re.compile(rf'\b{lang}: "(?:[^"\\]|\\.)*"')
        if not pattern.search(inner):
            raise SystemExit(f"{table_key} has no {lang} value")
        return pattern.sub(f'{lang}: "{_ts_escape(value)}"', inner, count=1)

    new_body = _ENTRY_RE.sub(repl_entry, body)
    if not found:
        raise SystemExit(f"glossary key {table_key} not found")
    GLOSSARY.write_text(src[: m.start(2)] + new_body + src[m.end(2):], encoding="utf-8")


def write_backend_catalog(lang: str, values: "OrderedDict[str, str]") -> None:
    """Rewrite app/i18n/<lang>.py: keep the module docstring, regenerate the dict."""
    path = BACKEND / "app" / "i18n" / f"{lang}.py"
    src = path.read_text(encoding="utf-8")
    head, sep, _ = src.partition("STRINGS: dict[str, str] = {")
    if not sep:
        raise SystemExit(f"{path} has no STRINGS table")
    lines = [head.rstrip() + "\n\n", "STRINGS: dict[str, str] = {\n"]
    for key, value in values.items():
        lines.append(f"    {json.dumps(key, ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False)},\n")
    lines.append("}\n")
    path.write_text("".join(lines), encoding="utf-8")


# ----------------------------------------------------------------- commands
def cmd_export(path: Path) -> int:
    status = read_status()
    rows = collect_rows()
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "key", "en", "am", "om", "status_am", "status_om"])
        for source, key, vals in rows:
            w.writerow([
                source, key, vals.get("en", ""), vals.get("am", ""), vals.get("om", ""),
                status_of(status, source, key, "am", vals.get("am", "")),
                status_of(status, source, key, "om", vals.get("om", "")),
            ])
    print(f"exported {len(rows)} rows to {path}")
    return 0


def cmd_import(path: Path) -> int:
    status = read_status()
    backend = read_backend()
    changed = {"messages": 0, "glossary": 0, "backend": 0}
    reviewed = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            source, key = row["source"], row["key"]
            for lang in LANGS:
                value = (row.get(lang) or "").strip()
                flag = (row.get(f"status_{lang}") or "").strip().lower()
                if not value:
                    continue
                if source == SRC_MESSAGES:
                    current = read_messages()[lang].get(key)
                    if current != value:
                        write_messages_value(lang, key, value)
                        changed["messages"] += 1
                elif source == SRC_GLOSSARY:
                    current = read_glossary().get(key, {}).get(lang)
                    if current != value:
                        write_glossary_value(lang, key, value)
                        changed["glossary"] += 1
                elif source == SRC_BACKEND:
                    if backend[lang].get(key) != value:
                        backend[lang][key] = value
                        changed["backend"] += 1
                else:
                    raise SystemExit(f"unknown source {source!r} for {key}")
                slot = status.setdefault(f"{source}::{key}", {})
                if flag == "reviewed":
                    slot[lang] = {"status": "reviewed", "sha1": fingerprint(value), "on": date.today().isoformat()}
                    reviewed += 1
                elif flag in ("machine-draft", "draft", ""):
                    slot.pop(lang, None)
                if not slot:
                    status.pop(f"{source}::{key}", None)
    for lang in LANGS:
        write_backend_catalog(lang, backend[lang])
    write_status(status)
    print(f"imported: {changed} changed strings, {reviewed} reviewed cells recorded in {STATUS_FILE.name}")
    return cmd_status()


def cmd_status() -> int:
    status = read_status()
    rows = collect_rows()
    counts: dict[str, int] = {}
    table = ["| source | key | am | om |", "|---|---|---|---|"]
    for source, key, vals in rows:
        s_am = status_of(status, source, key, "am", vals.get("am", ""))
        s_om = status_of(status, source, key, "om", vals.get("om", ""))
        for s in (s_am, s_om):
            counts[s] = counts.get(s, 0) + 1
        table.append(f"| `{source}` | `{key}` | {s_am} | {s_om} |")
    totals = " · ".join(f"{counts.get(s, 0)} {s}" for s in ("machine-draft", "reviewed", "changed-since-review"))
    lines = [
        "# Translation status — Amharic (am) and Afaan Oromoo (om)",
        "",
        f"Generated by `app/frontend/scripts/translation_status.py` on {date.today().isoformat()}.",
        "Every Amharic and Afaan Oromoo string in the product was **drafted by the",
        "implementation agent** and must be reviewed by a native speaker before release.",
        "",
        "Workflow: `python scripts/translation_status.py --export review.csv` → edit the",
        "`am`/`om` cells and set `status_am`/`status_om` to `reviewed` → `--import review.csv`.",
        "The import writes the text back into all three catalogs and fingerprints every",
        "reviewed string in `app/frontend/messages/review-status.json`; a vitest and a",
        "pytest guard fail if a reviewed string changes again without this workflow.",
        "",
        "Statuses: `machine-draft` (needs native review) · `reviewed` (signed off) ·",
        "`changed-since-review` (edited after sign-off — re-review or re-import).",
        "Since U2 the chat quick-reply sentences are translated too (the backend reads",
        "the structured hint behind a chip and the translated sentence itself).",
        "",
        f"**Totals (am + om cells):** {totals} — {len(rows)} keys "
        f"({sum(1 for r in rows if r[0] == SRC_GLOSSARY)} glossary, "
        f"{sum(1 for r in rows if r[0] == SRC_MESSAGES)} UI, "
        f"{sum(1 for r in rows if r[0] == SRC_BACKEND)} backend).",
        "",
    ]
    lines.extend(table)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(ROOT)}: {len(rows)} keys; {totals}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", metavar="CSV", help="write the review sheet")
    ap.add_argument("--import", dest="import_", metavar="CSV", help="read a reviewed sheet back")
    args = ap.parse_args()
    if args.export:
        return cmd_export(Path(args.export))
    if args.import_:
        return cmd_import(Path(args.import_))
    return cmd_status()


if __name__ == "__main__":
    raise SystemExit(main())
