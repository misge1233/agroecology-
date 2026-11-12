#!/usr/bin/env python3
"""Load the fresh test set ``fresh_2024plus`` (E7 Part A6).

Ethiopian multi-practice trials **published after June 2024** (after the knowledge cutoff
of ``gpt-4o-mini`` and ``gpt-4.1-mini``), extracted by the data team in Habtamu Sewnet's
database format, are dropped by the owner into ``data/raw/fresh_2024plus/`` as one or more
CSV exports with the MasterData columns. Every file goes through
:func:`pipelines.evidence.load_habtamu.load` (same parsing rules, same rule log), then:

* **date rule (pre-registered 12 Nov 2026):** a row is fresh when its publication year is
  2025 or later, or 2024 with a publication month of July or later in an optional
  ``Publication_date`` / ``Published`` column; 2024 rows without a month and older rows are
  dropped and counted (they cannot be shown to postdate the cutoff);
* **country:** Ethiopia only (``country == "ET"``); others dropped and counted;
* study ids get the prefix ``HAB_FRESH_`` (row ids stay unique next to the main Habtamu
  rows) and ``extra`` carries ``{"fresh_2024plus": true, "fresh_file": <name>}``.

The rows join the store as source ``HAB`` (the format and licence of the partner
database). :mod:`model.harness.queries` gives cells made only of fresh rows the query set
``fresh_2024plus``; the harness split ``fresh`` holds them all out in one fold (training
on everything else), so the existing spatial and study folds are unchanged.

With no files the set is *pending*: :func:`status` says so and nothing else changes.

Usage::

    python pipelines/evidence/load_fresh.py [--dir PATH]   # status and counts, writes nothing
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.evidence import common, crop_lookup, load_habtamu  # noqa: E402
from pipelines.evidence.common import RuleLog  # noqa: E402

logger = logging.getLogger(__name__)

FRESH_DIR = common.DATA_DIR / "raw" / "fresh_2024plus"
QUERY_SET = "fresh_2024plus"
MARKER = "fresh_2024plus"
PREFIX = "HAB_FRESH_"
CUTOFF = (2024, 7)  # published in July 2024 or later
DATE_COLUMNS = ("Publication_date", "Published")
MIN_QUERIES = 30    # E7: run A1 and the hybrids on the set only with at least this many queries


def files(directory: Path = FRESH_DIR) -> list[Path]:
    return sorted(p for p in Path(directory).glob("*.csv") if p.is_file()) if Path(directory).exists() else []


def available(directory: Path = FRESH_DIR) -> bool:
    return bool(files(directory))


def publication_month(raw: Any) -> int | None:
    """Month of a publication date string (``2024-09-03``, ``09/2024``, ``Sep 2024``), else ``None``."""
    s = str(raw or "").strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    m = re.search(r"(?:19|20)\d{2}[-/.](\d{1,2})", s) or re.search(r"\b(\d{1,2})[-/.](?:19|20)\d{2}", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    months = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
    for i, name in enumerate(months, start=1):
        if re.search(rf"\b{name}", s.lower()):
            return i
    return None


def is_fresh(year: Any, month: int | None) -> bool:
    """The pre-registered date rule: year >= 2025, or 2024 with a month of July or later."""
    try:
        y = int(year)
    except (TypeError, ValueError):
        return False
    if y > CUTOFF[0]:
        return True
    return y == CUTOFF[0] and month is not None and month >= CUTOFF[1]


def is_fresh_extra(extra: Any) -> bool:
    """True when a store row's ``extra`` JSON carries the fresh marker."""
    if not isinstance(extra, str) or MARKER not in extra:
        return False
    try:
        return bool(json.loads(extra).get(MARKER))
    except (ValueError, AttributeError):
        return False


def load(directory: Path = FRESH_DIR, crops: crop_lookup.CropLookup | None = None) -> tuple[pd.DataFrame, RuleLog]:
    """Fresh rows from every CSV in ``directory`` (empty frame when none)."""
    log = RuleLog()
    frames = []
    for path in files(directory):
        df, file_log, raw = load_habtamu.load(path, crops=crops)
        for k, v in file_log.parsing.items():
            log.parse(f"{path.name}: {k}", int(v))
        for k, v in file_log.dropped.items():
            log.drop(f"{path.name}: {k}", int(v))
        month = pd.Series([None] * len(raw), index=raw.index, dtype=object)
        for col in DATE_COLUMNS:
            if col in raw.columns:
                month = raw[col].map(publication_month)
                break
        fresh = [is_fresh(y, m) for y, m in zip(df["year"], month.reindex(df.index))]
        fresh_s = pd.Series(fresh, index=df.index)
        keep = fresh_s & (df["country"] == "ET")
        log.drop("not_after_june_2024", int((~fresh_s).sum()))
        log.drop("not_ethiopia", int((fresh_s & (df["country"] != "ET")).sum()))
        df = df[keep].copy()
        if df.empty:
            continue
        df["study_id"] = PREFIX + df["study_id"].str.removeprefix("HAB_")
        df["row_id"] = common.make_row_ids(load_habtamu.SOURCE, df["study_id"])
        extras = []
        for e in df["extra"]:
            d = json.loads(e) if isinstance(e, str) and e.strip() else {}
            d.update({MARKER: True, "fresh_file": path.name})
            extras.append(common.json_extra(d))
        df["extra"] = extras
        frames.append(df)
        log.parse(f"{path.name}: fresh_rows_kept", int(len(df)))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return out, log


def status(directory: Path = FRESH_DIR) -> dict[str, Any]:
    """``pending`` without files, else the number of files and fresh Ethiopian rows."""
    fs = files(directory)
    if not fs:
        return {"status": "pending", "dir": str(directory), "files": 0, "rows": 0}
    df, _ = load(directory)
    return {"status": "loaded", "dir": str(directory), "files": len(fs), "rows": int(len(df)),
            "studies": int(df["study_id"].nunique()) if len(df) else 0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Status of the fresh_2024plus test set (writes nothing)")
    ap.add_argument("--dir", type=Path, default=FRESH_DIR)
    a = ap.parse_args(argv)
    print(json.dumps(status(a.dir), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
