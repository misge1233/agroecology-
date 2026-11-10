"""Frozen schema of the unified evidence store (``evidence_rows``).

Implements roadmap Appendix A (``docs/roadmap/AE+_enhancement_roadmap.md``)
exactly, plus the optional columns added by the E1 brief
(``hlpe_principle``, ``mfl_domain``, ``extra``) and ``direction_reviewed``
(brief C2: a row whose outcome direction has not been reviewed by a human
carries ``direction = null`` and ``direction_reviewed = False`` and is excluded
from any ranking use).

Representation choices (documented in ``data/evidence/README.md``):

* ``practice_components`` is a ``list[str]`` in the roadmap; it is stored as a
  ``;``-joined string (dtype ``strlist``) so the Parquet file and the CSV
  mirror round-trip identically.
* ``extra`` is a JSON object serialised to a string, for source fields that
  have no column yet.
* ``ctx_*`` columns other than the five fixed ``ctx_reported_*``/``ctx_release``
  columns are not fixed here; E3 adds them and they are validated by prefix.

Public API: :data:`EVIDENCE_COLUMNS`, :data:`SCHEMA_VERSION`,
:func:`validate`, :func:`write_store`, :func:`read_store`.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import math
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: 1.1 (E2): taxonomy `objective_group` gains "climate"; outcome statuses `excluded`,
#: `context_dependent`, `merged` (their rows carry direction null, direction_reviewed false).
SCHEMA_VERSION = "1.1"
SCHEMA_HISTORY = {"1.0": "E1, 10 Nov 2026", "1.1": "E2: climate objective group; outcome review statuses"}

STORE_PARQUET = "evidence_rows.parquet"
STORE_CSV = "evidence_rows.csv"
STORE_MANIFEST = "store_manifest.json"

SOURCES = ("ERA", "CSA", "HAB", "WOCAT", "other")
LOC_PRECISION = ("exact", "site", "district", "country", "none")
LOC_METHOD = ("reported", "geocoded_llm_checked", "geocoded_llm_unchecked", "none")
QUALITY_FLAGS = ("High", "Medium", "Low", "NR")
DIRECTIONS = (1, -1)

#: dtype vocabulary used below.
#:   str      Python str (pandas object / string)
#:   strlist  ';'-joined list of str
#:   json     JSON object serialised to str
#:   float    float64
#:   int      nullable integer (pandas Int64)
#:   bool     boolean
DTYPES = ("str", "strlist", "json", "float", "int", "bool")


@dataclass(frozen=True)
class Column:
    """One schema column: dtype, nullability and (optional) allowed values."""

    dtype: str
    nullable: bool
    allowed: tuple[Any, ...] | None = None


def _c(dtype: str, nullable: bool = True, allowed: tuple[Any, ...] | None = None) -> Column:
    return Column(dtype, nullable, allowed)


#: Ordered mapping column -> (dtype, nullable, allowed values). Appendix A order.
EVIDENCE_COLUMNS: dict[str, Column] = {
    "row_id": _c("str", False),
    "source": _c("str", False, SOURCES),
    "study_id": _c("str", False),
    "doi": _c("str"),
    "citation": _c("str", False),
    "year": _c("int"),
    "country": _c("str"),  # ISO 3166-1 alpha-2; null only when unmapped (counted in the card)
    "lat": _c("float"),
    "lon": _c("float"),
    "loc_precision": _c("str", False, LOC_PRECISION),
    "loc_method": _c("str", False, LOC_METHOD),
    "site_name": _c("str"),
    "practice_id": _c("str"),  # null while the label waits in a review sheet
    "practice_raw": _c("str", False),
    "practice_components": _c("strlist"),
    "practice_family": _c("str"),
    "comparator": _c("str"),
    "crop_group": _c("str"),
    "crop": _c("str"),
    "outcome_id": _c("str"),  # null while the label waits in a review sheet
    "outcome_raw": _c("str", False),
    "direction": _c("int", True, DIRECTIONS),
    "unit": _c("str"),
    "mean_with": _c("float"),
    "mean_without": _c("float"),
    "sd_with": _c("float"),
    "sd_without": _c("float"),
    "se_with": _c("float"),
    "se_without": _c("float"),
    "n_with": _c("int"),
    "n_without": _c("int"),
    "lrr": _c("float"),
    "var_lrr": _c("float"),
    "weight": _c("float", False),
    "duration_years": _c("float"),
    "study_design": _c("str"),
    "replication": _c("str"),
    "scale": _c("str"),
    "quality_flag": _c("str", False, QUALITY_FLAGS),
    "ctx_reported_rain_mm": _c("float"),
    "ctx_reported_altitude_m": _c("float"),
    "ctx_reported_soil": _c("str"),
    "ctx_reported_aez": _c("str"),
    "ctx_release": _c("str"),
    "evidence_text": _c("str"),
    "extraction_locator": _c("str"),
    "licence": _c("str", False),
    # --- optional columns added by the E1 brief -----------------------------
    "hlpe_principle": _c("str"),
    "mfl_domain": _c("str"),
    "extra": _c("json"),
    # --- brief C2: explicit review state of `direction` ---------------------
    "direction_reviewed": _c("bool", False),
}

CTX_PREFIX = "ctx_"
ROW_ID_RE = re.compile(r"^(?P<source>[A-Za-z]+):(?P<study_id>[^:]+):(?P<n>[1-9][0-9]*)$")
LRR_TOL = 1e-9


class SchemaError(ValueError):
    """Raised by :func:`validate` in strict mode when the frame has errors."""

    def __init__(self, report: "ValidationReport") -> None:
        super().__init__(report.summary())
        self.report = report


@dataclass
class ValidationReport:
    """Counts per violation type (``check -> n``), plus examples for each."""

    n_rows: int = 0
    errors: Counter = field(default_factory=Counter)
    examples: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True when no violation was counted."""
        return not self.errors

    @property
    def n_errors(self) -> int:
        """Total number of violations across checks."""
        return int(sum(self.errors.values()))

    def add(self, check: str, count: int, examples: Iterable[Any] = ()) -> None:
        """Record ``count`` violations of ``check`` (no-op when zero)."""
        if count <= 0:
            return
        self.errors[check] += int(count)
        ex = self.examples.setdefault(check, [])
        for item in examples:
            if len(ex) >= 5:
                break
            ex.append(str(item))

    def summary(self) -> str:
        """One line per violation, for logs and exceptions."""
        if self.ok:
            return f"evidence schema {SCHEMA_VERSION}: {self.n_rows} rows, 0 errors"
        lines = [f"evidence schema {SCHEMA_VERSION}: {self.n_rows} rows, {self.n_errors} errors"]
        for check, n in sorted(self.errors.items()):
            lines.append(f"  {check}: {n}  e.g. {self.examples.get(check, [])[:3]}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly form (stored in the manifest)."""
        return {"n_rows": self.n_rows, "n_errors": self.n_errors, "errors": dict(self.errors)}


# --------------------------------------------------------------------- helpers
def empty_frame() -> pd.DataFrame:
    """An empty frame with every schema column in order and the right dtypes."""
    return coerce(pd.DataFrame({c: [] for c in EVIDENCE_COLUMNS}))


def coerce(df: pd.DataFrame) -> pd.DataFrame:
    """Cast schema columns to their storage dtypes and order them.

    Unknown non-``ctx_`` columns are kept at the end (``validate`` reports
    them). Values are not altered except for dtype casts.
    """
    out = df.copy()
    for col, spec in EVIDENCE_COLUMNS.items():
        if col not in out.columns:
            out[col] = None
        s = out[col]
        if spec.dtype == "float":
            out[col] = pd.to_numeric(s, errors="coerce").astype("float64")
        elif spec.dtype == "int":
            out[col] = pd.to_numeric(s, errors="coerce").round().astype("Int64")
        elif spec.dtype == "bool":
            out[col] = pd.array([_to_bool(v) for v in s], dtype="boolean")
        else:
            # list comprehension, not .map: pandas 3 would turn None back into NaN
            out[col] = pd.Series([_to_str(v) for v in s], index=s.index, dtype=object)
    fixed = list(EVIDENCE_COLUMNS)
    rest = [c for c in out.columns if c not in EVIDENCE_COLUMNS]
    return out[fixed + rest]


def _to_str(v: Any) -> Any:
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
        return None
    if isinstance(v, (list, tuple)):
        return ";".join(str(x) for x in v) if v else None
    s = str(v)
    return s if s != "" else None


def _to_bool(v: Any) -> Any:
    if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)):
        return pd.NA
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)


def _isnull(s: pd.Series) -> pd.Series:
    return s.isna()


# ------------------------------------------------------------------- validate
def validate(
    df: pd.DataFrame,
    strict: bool = True,
    outcome_directions: Mapping[str, int | None] | None = None,
) -> ValidationReport:
    """Validate ``df`` against the schema; raise :class:`SchemaError` on any error.

    Checks: column presence and dtypes, nullability, enums (``source``,
    ``loc_precision``, ``loc_method``, ``quality_flag``, ``direction``),
    ``row_id`` uniqueness and pattern ``<source>:<study_id>:<n>``, ``lrr ==
    ln(mean_with / mean_without)`` within 1e-9 wherever both means are positive
    (and ``lrr`` null otherwise), ``var_lrr`` null unless both SDs and Ns exist,
    ``weight > 0``, JSON validity of ``extra``, and ``direction`` consistent
    with the outcome taxonomy.

    ``outcome_directions`` maps ``outcome_id`` to its *reviewed* direction
    (``None`` when the direction is not yet reviewed). When given, every row
    must carry exactly that direction and ``direction_reviewed`` must be True
    iff the outcome's direction is reviewed. Without it, only internal
    consistency is checked (``direction`` null iff not reviewed).

    ``strict=False`` returns the report without raising.
    """
    rep = ValidationReport(n_rows=len(df))

    # --- columns ------------------------------------------------------------
    missing = [c for c in EVIDENCE_COLUMNS if c not in df.columns]
    rep.add("missing_column", len(missing), missing)
    unknown = [c for c in df.columns if c not in EVIDENCE_COLUMNS and not c.startswith(CTX_PREFIX)]
    rep.add("unknown_column", len(unknown), unknown)
    if missing:
        if strict:
            raise SchemaError(rep)
        return rep

    # --- dtypes and nullability ---------------------------------------------
    for col, spec in EVIDENCE_COLUMNS.items():
        s = df[col]
        nulls = _isnull(s)
        if not spec.nullable:
            rep.add(f"null:{col}", int(nulls.sum()), df.loc[nulls, "row_id"].head(5) if col != "row_id" else [])
        vals = s[~nulls]
        if vals.empty:
            continue
        bad = _dtype_violations(vals, spec.dtype)
        rep.add(f"dtype:{col}", int(bad.sum()), vals[bad].head(5))
        if spec.allowed is not None:
            ok_vals = vals[~bad]
            if spec.dtype == "int":
                notin = ~ok_vals.astype("int64").isin(spec.allowed)
            else:
                notin = ~ok_vals.isin(spec.allowed)
            rep.add(f"enum:{col}", int(notin.sum()), ok_vals[notin].head(5))

    # --- row_id --------------------------------------------------------------
    rid = df["row_id"].astype("string")
    dup = rid.duplicated(keep=False) & rid.notna()
    rep.add("row_id_duplicate", int(dup.sum()), rid[dup].head(5))
    parsed = rid.str.extract(ROW_ID_RE)
    bad_pat = parsed["source"].isna() & rid.notna()
    rep.add("row_id_pattern", int(bad_pat.sum()), rid[bad_pat].head(5))
    ok_pat = ~bad_pat & rid.notna()
    mism = ok_pat & (
        (parsed["source"] != df["source"].astype("string"))
        | (parsed["study_id"] != df["study_id"].astype("string"))
    )
    rep.add("row_id_mismatch", int(mism.fillna(False).sum()), rid[mism.fillna(False)].head(5))

    # --- lrr -----------------------------------------------------------------
    mw = pd.to_numeric(df["mean_with"], errors="coerce")
    mo = pd.to_numeric(df["mean_without"], errors="coerce")
    lrr = pd.to_numeric(df["lrr"], errors="coerce")
    both_pos = (mw > 0) & (mo > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        expect = np.log(mw / mo)
    wrong = both_pos & ~((lrr - expect).abs() <= LRR_TOL)
    rep.add("lrr_mismatch", int(wrong.sum()), df.loc[wrong, "row_id"].head(5))
    spurious = ~both_pos & lrr.notna()
    rep.add("lrr_without_positive_means", int(spurious.sum()), df.loc[spurious, "row_id"].head(5))

    # --- var_lrr -------------------------------------------------------------
    var = pd.to_numeric(df["var_lrr"], errors="coerce")
    have_disp = (
        df["sd_with"].notna() & df["sd_without"].notna()
        & df["n_with"].notna() & df["n_without"].notna()
    )
    bad_var = var.notna() & ~(have_disp & lrr.notna())
    rep.add("var_lrr_without_sd_n", int(bad_var.sum()), df.loc[bad_var, "row_id"].head(5))
    nonpos_var = var.notna() & ~(var > 0)
    rep.add("var_lrr_not_positive", int(nonpos_var.sum()), df.loc[nonpos_var, "row_id"].head(5))

    # --- weight --------------------------------------------------------------
    w = pd.to_numeric(df["weight"], errors="coerce")
    badw = w.notna() & ~((w > 0) & np.isfinite(w))
    rep.add("weight_not_positive", int(badw.sum()), df.loc[badw, "row_id"].head(5))

    # --- extra is JSON -------------------------------------------------------
    bad_json = df["extra"].dropna().map(_bad_json)
    rep.add("extra_not_json_object", int(bad_json.sum()), df.loc[bad_json[bad_json].index, "row_id"].head(5))

    # --- direction vs taxonomy -----------------------------------------------
    d = pd.to_numeric(df["direction"], errors="coerce")
    reviewed = df["direction_reviewed"].astype("boolean").fillna(False).astype(bool)
    incons = (reviewed & d.isna()) | (~reviewed & d.notna())
    rep.add("direction_review_state", int(incons.sum()), df.loc[incons, "row_id"].head(5))
    if outcome_directions is not None:
        exp = df["outcome_id"].map(lambda o: outcome_directions.get(o) if isinstance(o, str) else None)
        exp_num = pd.to_numeric(exp, errors="coerce")
        unknown_out = df["outcome_id"].notna() & ~df["outcome_id"].isin(list(outcome_directions))
        rep.add("outcome_id_not_in_taxonomy", int(unknown_out.sum()), df.loc[unknown_out, "outcome_id"].head(5))
        mismatch = ~unknown_out & ~((d == exp_num) | (d.isna() & exp_num.isna()))
        rep.add("direction_vs_taxonomy", int(mismatch.sum()), df.loc[mismatch, "row_id"].head(5))

    if not rep.ok:
        logger.warning(rep.summary())
        if strict:
            raise SchemaError(rep)
    else:
        logger.info(rep.summary())
    return rep


def _bad_json(v: Any) -> bool:
    try:
        return not isinstance(json.loads(v), dict)
    except (TypeError, ValueError):
        return True


def _dtype_violations(vals: pd.Series, dtype: str) -> pd.Series:
    """Boolean mask of non-null values that do not fit ``dtype``."""
    if dtype in ("str", "strlist", "json"):
        return ~vals.map(lambda v: isinstance(v, str))
    if dtype == "float":
        return ~vals.map(lambda v: isinstance(v, (float, int, np.floating, np.integer)) and not isinstance(v, bool))
    if dtype == "int":
        def bad_int(v: Any) -> bool:
            if isinstance(v, bool):
                return True
            if isinstance(v, (int, np.integer)):
                return False
            if isinstance(v, (float, np.floating)):
                return not float(v).is_integer()
            return True
        return vals.map(bad_int)
    if dtype == "bool":
        return ~vals.map(lambda v: isinstance(v, (bool, np.bool_)))
    raise ValueError(f"unknown dtype {dtype}")


# ------------------------------------------------------------------ read/write
def _git_commit(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=10, check=False
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def file_sha256(path: Path) -> str:
    """SHA-256 of a file, streamed."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_store(
    df: pd.DataFrame,
    out_dir: Path | str,
    input_files: Iterable[Path] = (),
    extra_manifest: Mapping[str, Any] | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Write ``evidence_rows.parquet`` (pyarrow, zstd), a CSV mirror and the manifest.

    The manifest records the schema version, row counts per source, build
    time (UTC), git commit, SHA-256 of every input file and anything passed in
    ``extra_manifest``. Returns the manifest.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame = coerce(df)
    frame.to_parquet(out / STORE_PARQUET, engine="pyarrow", compression="zstd", index=False)
    frame.to_csv(out / STORE_CSV, index=False, lineterminator="\n", encoding="utf-8")
    repo = repo_root or Path(__file__).resolve().parents[2]
    inputs = {}
    for p in input_files:
        p = Path(p)
        if p.exists():
            try:
                key = p.resolve().relative_to(repo.resolve()).as_posix()
            except ValueError:
                key = p.name
            inputs[key] = file_sha256(p)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "built_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(repo),
        "n_rows": int(len(frame)),
        "rows_per_source": {str(k): int(v) for k, v in frame["source"].value_counts().sort_index().items()},
        "columns": list(frame.columns),
        "input_files": inputs,
    }
    if extra_manifest:
        manifest.update(extra_manifest)
    (out / STORE_MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("wrote store: %s (%d rows)", out / STORE_PARQUET, len(frame))
    return manifest


def read_store(in_dir: Path | str) -> pd.DataFrame:
    """Read the store (Parquet) back into a schema-typed frame."""
    p = Path(in_dir) / STORE_PARQUET
    if not p.exists():
        raise FileNotFoundError(
            f"{p} not found: build it with `python pipelines/evidence/build_evidence_store.py`"
        )
    return coerce(pd.read_parquet(p, engine="pyarrow"))
