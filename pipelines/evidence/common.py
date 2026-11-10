"""Shared helpers for the evidence loaders.

* :func:`parse_number` (and :func:`parse_quantity`): text numerics from the
  extraction sheets, every decision a named, counted rule.
* id helpers: :func:`slug`, :func:`upper_snake`, :func:`make_row_ids`,
  :func:`normalise_doi`.
* effect sizes: :func:`lrr`, :func:`var_lrr` (delta method).
* :class:`RuleLog`: counts rows per rule (kept / dropped / parsed) for the
  data cards, so nothing is dropped silently.
* :func:`setup_logging`, :func:`bootstrap_repo_path`.
"""
from __future__ import annotations

import json
import logging
import math
import re
import sys
import unicodedata
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
EVIDENCE_DIR = DATA_DIR / "evidence"
CARDS_DIR = EVIDENCE_DIR / "cards"
TAXONOMY_DIR = DATA_DIR / "taxonomy"
REVIEW_DIR = TAXONOMY_DIR / "review"

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure root logging once for a CLI run."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def bootstrap_repo_path() -> None:
    """Put the repo root on ``sys.path`` so ``pipelines``/``rag`` import as packages."""
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


# ------------------------------------------------------------------ rule log
@dataclass
class RuleLog:
    """Ordered counters of named rules, rendered into a data card."""

    dropped: "OrderedDict[str, int]" = field(default_factory=OrderedDict)
    parsing: "OrderedDict[str, int]" = field(default_factory=OrderedDict)
    notes: list[str] = field(default_factory=list)

    def drop(self, rule: str, n: int) -> None:
        """Count ``n`` rows excluded by ``rule`` (always recorded, even 0)."""
        self.dropped[rule] = self.dropped.get(rule, 0) + int(n)

    def parse(self, rule: str, n: int = 1) -> None:
        """Count ``n`` applications of a parsing/mapping rule."""
        self.parsing[rule] = self.parsing.get(rule, 0) + int(n)

    def note(self, text: str) -> None:
        """Free-text provenance note for the card."""
        self.notes.append(text)


# ------------------------------------------------------------------- numbers
_MISSING_TOKENS = {"", "na", "n/a", "nr", "nd", "none", "null", "-", "–", "—", "not reported", "nan", "ns"}
_RANGE_RE = re.compile(
    r"^\s*(?P<a>[-+]?\d+(?:\.\d+)?)\s*(?:–|—|-|to|‑)\s*(?P<b>[-+]?\d+(?:\.\d+)?)\b"
)
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")


@dataclass(frozen=True)
class Parsed:
    """Result of :func:`parse_quantity`.

    ``value`` is the number to use (null for a range when ``kind == 'mean'``),
    ``rule`` the named rule that fired, ``unit`` any trailing text that looked
    like a unit, ``low``/``high`` the bounds when the text was a range.
    """

    value: float | None
    rule: str
    unit: str | None = None
    low: float | None = None
    high: float | None = None
    raw: str | None = None


def _clean_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("−", "-")  # minus sign
    return " ".join(s.split())


def parse_quantity(raw: Any, kind: str = "mean") -> Parsed:
    """Parse one text numeric.

    Rules (the ``rule`` names appear in the data cards):

    * ``missing``: empty, ``NA``, ``NR``, ``ND``, ``-`` ... -> null.
    * ``number``: a plain number (``1.3``, ``-2``, ``1e3``).
    * ``thousands_separator``: ``1,204`` -> 1204.
    * ``approx``: ``~800`` / ``≈800`` / ``c. 800`` -> 800.
    * ``plus_minus_first``: ``12 ± 3`` -> 12 (the first number is the value).
    * ``range_as_null`` (``kind='mean'``): ``a–b``, ``a-b``, ``a to b`` -> null,
      because a range is not a mean.
    * ``range_midpoint`` (``kind='context'``): the same ranges -> midpoint.
    * ``number_with_unit``: ``700 mm yr⁻¹`` -> 700, unit ``mm yr-1``.
    * ``comparator_bound``: ``<0.05`` / ``>2`` -> null (a bound, not a value).
    * ``ambiguous_decimal_comma``: ``1,2`` -> null (decimal comma or list; never guessed).
    * ``number_with_trailing_text``: ``3 (estimated)`` -> 3.
    * ``unparsed``: anything else -> null.
    """
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return Parsed(None, "missing", raw=None)
    if isinstance(raw, (int, float, np.integer, np.floating)) and not isinstance(raw, bool):
        return Parsed(float(raw), "number", raw=str(raw))
    text = _clean_text(str(raw))
    low = text.lower()
    if low in _MISSING_TOKENS:
        return Parsed(None, "missing", raw=text)
    if low[:1] in "<>≤≥":
        return Parsed(None, "comparator_bound", raw=text)
    rule = "number"
    work = text
    if work[:1] in "~≈" or low.startswith(("c.", "ca.", "approx", "about", "around")):
        work = re.sub(r"^(~|≈|c\.|ca\.|approx\.?|approximately|about|around)\s*", "", work, flags=re.I)
        rule = "approx"
    if "±" in work or "+/-" in work:
        first = re.split(r"±|\+/-", work, maxsplit=1)[0]
        m = _NUM_RE.search(_THOUSANDS_RE.sub("", first))
        if m:
            return Parsed(float(m.group()), "plus_minus_first", raw=text)
        return Parsed(None, "unparsed", raw=text)
    if _THOUSANDS_RE.search(work):
        work = _THOUSANDS_RE.sub("", work)
        if rule == "number":
            rule = "thousands_separator"
    rm = _RANGE_RE.match(work)
    if rm:
        a, b = float(rm.group("a")), float(rm.group("b"))
        unit = _unit_tail(work[rm.end():])
        if kind == "context":
            return Parsed((a + b) / 2.0, "range_midpoint", unit=unit, low=a, high=b, raw=text)
        return Parsed(None, "range_as_null", unit=unit, low=a, high=b, raw=text)
    m = re.match(r"^\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", work)
    if m:
        tail = work[m.end():]
        if re.match(r"^,\d", tail):
            # "1,2": a decimal comma or a list; never guess.
            return Parsed(None, "ambiguous_decimal_comma", raw=text)
        value = float(m.group(1))
        unit = _unit_tail(tail)
        if unit:
            return Parsed(value, "number_with_unit" if rule == "number" else rule, unit=unit, raw=text)
        if tail.strip():
            return Parsed(value, "number_with_trailing_text" if rule == "number" else rule, raw=text)
        return Parsed(value, rule, raw=text)
    return Parsed(None, "unparsed", raw=text)


def _unit_tail(tail: str) -> str | None:
    """Trailing text that looks like a unit (starts with a letter, %, ° or µ)."""
    t = tail.translate(_SUPERSCRIPT).strip(" ,;()")
    if t and (t[0].isalpha() or t[0] in "%°µ/"):
        return t
    return None


def parse_number(raw: Any, kind: str = "mean") -> float | None:
    """Value of :func:`parse_quantity` (``None`` when the text is not a usable number)."""
    return parse_quantity(raw, kind).value


# --------------------------------------------------------------- effect sizes
def lrr(mean_with: float | None, mean_without: float | None) -> float | None:
    """``ln(mean_with / mean_without)`` when both means are positive, else ``None``."""
    if mean_with is None or mean_without is None:
        return None
    try:
        mw, mo = float(mean_with), float(mean_without)
    except (TypeError, ValueError):
        return None
    if not (mw > 0 and mo > 0) or math.isnan(mw) or math.isnan(mo):
        return None
    return math.log(mw / mo)


def var_lrr(
    mean_with: float | None, mean_without: float | None,
    sd_with: float | None, sd_without: float | None,
    n_with: float | None, n_without: float | None,
) -> float | None:
    """Delta-method variance of the log response ratio (Hedges et al. 1999).

    ``var = sd_t² / (n_t · m_t²) + sd_c² / (n_c · m_c²)``; ``None`` unless both
    means are positive, both SDs and both Ns exist, Ns are positive and the
    result is strictly positive (an SD of 0 gives no usable variance).
    """
    vals = (mean_with, mean_without, sd_with, sd_without, n_with, n_without)
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals):
        return None
    mw, mo, sw, so, nw, no = (float(v) for v in vals)
    if not (mw > 0 and mo > 0 and nw > 0 and no > 0 and sw >= 0 and so >= 0):
        return None
    v = sw * sw / (nw * mw * mw) + so * so / (no * mo * mo)
    return v if v > 0 else None


def lrr_series(mw: pd.Series, mo: pd.Series) -> pd.Series:
    """Vectorised :func:`lrr`."""
    mw = pd.to_numeric(mw, errors="coerce")
    mo = pd.to_numeric(mo, errors="coerce")
    ok = (mw > 0) & (mo > 0)
    out = pd.Series(np.nan, index=mw.index, dtype="float64")
    out[ok] = np.log(mw[ok] / mo[ok])
    return out


def var_lrr_series(df: pd.DataFrame) -> pd.Series:
    """Vectorised :func:`var_lrr` over the schema columns of ``df``."""
    mw = pd.to_numeric(df["mean_with"], errors="coerce")
    mo = pd.to_numeric(df["mean_without"], errors="coerce")
    sw = pd.to_numeric(df["sd_with"], errors="coerce")
    so = pd.to_numeric(df["sd_without"], errors="coerce")
    nw = pd.to_numeric(df["n_with"], errors="coerce").astype("float64")
    no = pd.to_numeric(df["n_without"], errors="coerce").astype("float64")
    ok = (mw > 0) & (mo > 0) & (nw > 0) & (no > 0) & (sw >= 0) & (so >= 0)
    v = sw ** 2 / (nw * mw ** 2) + so ** 2 / (no * mo ** 2)
    v = v.where(ok & (v > 0))
    return v.astype("float64")


# ------------------------------------------------------------------------ ids
def slug(text: Any) -> str:
    """ASCII slug keeping letters, digits and underscores (``Roschewitz_2005_001``)."""
    s = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s or "unknown"


def upper_snake(text: Any) -> str:
    """Upper snake case id (``Inorganic Fertilizer-Organic Fertilizer`` -> ``INORGANIC_FERTILIZER_ORGANIC_FERTILIZER``)."""
    s = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    s = s.replace("+", " PLUS ").replace("&", " AND ")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()
    return s or "UNKNOWN"


def make_row_ids(source: str, study_ids: pd.Series) -> pd.Series:
    """``<source>:<study_id>:<n>``, ``n`` counting rows of a study in file order from 1."""
    n = study_ids.groupby(study_ids, sort=False).cumcount() + 1
    return source + ":" + study_ids.astype(str) + ":" + n.astype(str)


_DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.I)


def normalise_doi(raw: Any) -> tuple[str | None, str | None]:
    """``(doi, non_doi_identifier)``: strips ``https://doi.org/`` and lower-cases.

    Identifiers that are not DOIs (``IJPSS.2014.8.004``, URLs) come back as the
    second element so the loader can keep them in ``extra``.
    """
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None, None
    s = " ".join(str(raw).split())
    if s.lower() in _MISSING_TOKENS:
        return None, None
    m = _DOI_RE.search(s)
    if m:
        return m.group().rstrip(".,;)").lower(), None
    return None, s


def json_extra(d: dict[str, Any]) -> str | None:
    """Serialise the ``extra`` dict, dropping null values; ``None`` when empty."""
    clean = {}
    for k, v in d.items():
        if v is None or v is pd.NA:
            continue
        if isinstance(v, float) and math.isnan(v):
            continue
        if isinstance(v, (np.integer,)):
            v = int(v)
        elif isinstance(v, (np.floating,)):
            v = float(v)
        if isinstance(v, str) and v.strip() == "":
            continue
        clean[k] = v
    return json.dumps(clean, ensure_ascii=False, sort_keys=True) if clean else None


def omap(series: pd.Series, fn) -> pd.Series:
    """``series.map(fn)`` that keeps Python objects (``None`` stays ``None``).

    pandas 3 infers a string dtype and turns ``None`` into NaN on ``.map``; the
    loaders rely on ``None`` checks, so they map through this helper.
    """
    return pd.Series([fn(v) for v in series], index=series.index, dtype=object)


def clean_str(v: Any, missing: Iterable[str] = ("", "nr", "na", "n/a", "nan", "none")) -> str | None:
    """Whitespace-collapsed string, ``None`` for missing tokens."""
    if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)):
        return None
    s = " ".join(str(v).split())
    return None if s.lower() in set(missing) else s


def row_key(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Stable 64-bit key per row over ``cols`` (nulls compare equal to each other)."""
    frame = df[cols].astype(object).where(df[cols].notna(), "\x00<NA>")
    frame = frame.map(lambda v: repr(v) if isinstance(v, float) else str(v))
    return pd.util.hash_pandas_object(frame, index=False)


def mark_duplicates(df: pd.DataFrame, cols: list[str], row_ids: pd.Series) -> pd.Series:
    """``row_id`` of the first identical row (over ``cols``) for later repeats, else ``None``."""
    key = row_key(df, cols)
    first = pd.Series(row_ids.values, index=df.index).groupby(key.values).transform("first")
    is_dup = key.duplicated(keep="first")
    return pd.Series([f if d else None for f, d in zip(first, is_dup)], index=df.index, dtype=object)


# ---------------------------------------------------------------- data cards
def coverage(df: pd.DataFrame, cols: Iterable[str]) -> dict[str, float]:
    """Share of non-null values per column."""
    n = max(len(df), 1)
    return {c: round(float(df[c].notna().sum()) / n, 4) for c in cols if c in df.columns}


def render_card(
    source: str,
    title: str,
    input_files: list[str],
    rows_read: int,
    rows_kept: int,
    log: RuleLog,
    cov: dict[str, float],
    licence: str,
    provenance: list[str],
    sections: dict[str, str] | None = None,
) -> str:
    """Markdown data card for one source."""
    lines = [f"# Data card: {source} ({title})", ""]
    lines += ["**Input**: " + ", ".join(f"`{p}`" for p in input_files), ""]
    lines += [f"**Rows read** {rows_read:,} · **rows kept in the store** {rows_kept:,} · "
              f"**rows dropped** {rows_read - rows_kept:,}", ""]
    lines += ["## Rows dropped, per rule", "", "| Rule | Rows |", "|---|---:|"]
    if log.dropped:
        lines += [f"| {k} | {v:,} |" for k, v in log.dropped.items()]
    else:
        lines += ["| (none) | 0 |"]
    lines += ["", "## Parsing and mapping rules (rows affected)", "", "| Rule | Rows |", "|---|---:|"]
    lines += [f"| {k} | {v:,} |" for k, v in log.parsing.items()] or ["| (none) | 0 |"]
    lines += ["", "## Coverage of key fields (share non-null)", "", "| Field | Share |", "|---|---:|"]
    lines += [f"| `{k}` | {v:.1%} |" for k, v in cov.items()]
    lines += ["", "## Licence and provenance", "", f"- Licence tag in the store: `{licence}`"]
    lines += [f"- {p}" for p in provenance]
    if log.notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in log.notes]
    for head, body in (sections or {}).items():
        lines += ["", f"## {head}", "", body.rstrip()]
    return "\n".join(lines) + "\n"


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 text with LF line endings, creating parent folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def counts_table(series: pd.Series, header: tuple[str, str], top: int | None = None) -> str:
    """Markdown table of value counts."""
    vc = series.value_counts(dropna=False)
    if top:
        vc = vc.head(top)
    lines = [f"| {header[0]} | {header[1]} |", "|---|---:|"]
    for k, v in vc.items():
        label = "(null)" if (k is None or (isinstance(k, float) and math.isnan(k))) else str(k)
        lines.append(f"| {label} | {int(v):,} |")
    return "\n".join(lines)


def counter_md(c: Counter | dict, header: tuple[str, str]) -> str:
    """Markdown table from a counter."""
    lines = [f"| {header[0]} | {header[1]} |", "|---|---:|"]
    for k, v in sorted(dict(c).items(), key=lambda kv: (-kv[1], str(kv[0]))):
        lines.append(f"| {k} | {v:,} |")
    return "\n".join(lines)
