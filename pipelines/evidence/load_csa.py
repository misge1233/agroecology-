#!/usr/bin/env python3
"""Load the Adimassu et al. CSA compilation into the evidence schema.

Input ``data/raw/CSA_practices_by_Agroecology.xlsx`` (Sheet1, 3,344 rows). Every
row is kept; the legacy scope and drop rules are applied only by the
reconciliation (:mod:`pipelines.evidence.reconcile`).

Practice label (decision, recorded in the E1 report): the brief names
``CSA_practi`` as "the frozen label", but the frozen ``CSA_practices`` values of
the 1,414 CSA rows in ``CSA_ERA_final_model_ready.csv`` are the ``CSA_catago``
categories (``Conservation tillage``, ``Physical SWC measures`` ...; 20 of the
100 frozen labels), not the 338 ``CSA_practi`` names. ``practice_raw`` therefore
carries ``CSA_catago`` (what the data contract and the reconciliation need) and
the finer ``CSA_practi`` name is kept in ``extra.CSA_practi`` for later
taxonomy work.

References come from ``data/processed/csa_study_references.json`` (built by
``pipelines/dataset/build_csa_references.py``; read, never rebuilt here).

Usage::

    python pipelines/evidence/load_csa.py [--dry-run] [--input PATH]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.evidence import common, crop_lookup  # noqa: E402
from pipelines.evidence.common import RuleLog  # noqa: E402

logger = logging.getLogger(__name__)

SOURCE = "CSA"
RAW_PATH = common.DATA_DIR / "raw" / "CSA_practices_by_Agroecology.xlsx"
REFS_PATH = common.DATA_DIR / "processed" / "csa_study_references.json"
LICENCE = "Adimassu-compilation-internal"
CARD_PATH = common.CARDS_DIR / "CSA.md"
RAW_COLUMNS = [
    "Study_No_", "Reference", "CSA_practi", "CSA_catago", "duration_o", "Scale", "study_site",
    "Latitude", "Longitude", "Region", "Rainfall", "Altitude_r", "Slope____", "Soil_type",
    "Crop_type", "CSA_Pilar", "Indicator", "With", "without", "unit", "Agro_zone",
]


def _s(v) -> str | None:
    return common.clean_str(v, missing=("", "nan"))


def normalise_indicator(v) -> str | None:
    """Case/whitespace-insensitive key used by the legacy scope filter and the aliases."""
    s = _s(v)
    return " ".join(s.lower().split()) if s else None


def read_raw(path: Path = RAW_PATH) -> pd.DataFrame:
    """Read Sheet1 untouched."""
    if not path.exists():
        raise FileNotFoundError(f"CSA input not found: {path}")
    raw = pd.read_excel(path, sheet_name="Sheet1")
    missing = [c for c in RAW_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"CSA workbook is missing columns {missing}")
    return raw


def read_references(path: Path = REFS_PATH) -> dict:
    """Study references keyed by ``CSA_<n>`` (plus ``_compilation``)."""
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run `python pipelines/dataset/build_csa_references.py`")
    return json.loads(path.read_text(encoding="utf-8"))


def load(path: Path = RAW_PATH, crops: crop_lookup.CropLookup | None = None,
         refs: dict | None = None) -> tuple[pd.DataFrame, RuleLog, pd.DataFrame]:
    """Return ``(frame, rule_log, raw)`` for the CSA workbook."""
    raw = read_raw(path)
    refs = refs if refs is not None else read_references()
    crops = crops if crops is not None else crop_lookup.load_lookup(missing_ok=True)
    log = RuleLog()
    df = pd.DataFrame(index=raw.index)
    df["source"] = SOURCE
    df["study_id"] = "CSA_" + raw["Study_No_"].astype(str).str.strip()
    comp = refs.get("_compilation", {})
    comp_cit = comp.get("citation") or "Adimassu et al. (2024) CSA compilation."

    def ref(sid: str, key: str):
        e = refs.get(sid)
        return e.get(key) if isinstance(e, dict) else None

    df["citation"] = [ref(s, "citation") or comp_cit for s in df["study_id"]]
    log.parse("citation_from_csa_study_references", int(sum(ref(s, "citation") is not None for s in df["study_id"])))
    log.parse("citation_fallback_compilation", int(sum(ref(s, "citation") is None for s in df["study_id"])))
    df["doi"] = [common.normalise_doi(ref(s, "doi"))[0] for s in df["study_id"]]
    df["year"] = pd.array([ref(s, "year") for s in df["study_id"]], dtype="Int64")
    df["country"] = "ET"

    lat = pd.to_numeric(raw["Latitude"], errors="coerce")
    lon = pd.to_numeric(raw["Longitude"], errors="coerce")
    has = lat.notna() & lon.notna() & (lat != 0) & (lon != 0)
    df["lat"], df["lon"] = lat.where(has), lon.where(has)
    df["loc_precision"] = np.where(has, "site", "country")
    df["loc_method"] = np.where(has, "reported", "none")
    log.parse("loc_site_reported_coordinates", int(has.sum()))
    log.parse("loc_zero_or_missing_coordinates_set_null", int((~has).sum()))
    df["site_name"] = common.omap(raw["study_site"], _s)

    df["practice_raw"] = common.omap(raw["CSA_catago"], _s)
    df["comparator"] = None
    df["outcome_raw"] = common.omap(raw["Indicator"], _s).fillna("(blank)")
    df["_outcome_key"] = common.omap(raw["Indicator"], normalise_indicator).fillna("(blank)")
    log.parse("outcome_raw_blank_indicator", int(common.omap(raw["Indicator"], _s).isna().sum()))
    df["unit"] = common.omap(raw["unit"], _s)
    df["mean_with"] = pd.to_numeric(raw["With"], errors="coerce")
    df["mean_without"] = pd.to_numeric(raw["without"], errors="coerce")
    for c in ("sd_with", "sd_without", "se_with", "se_without"):
        df[c] = np.nan
    df["n_with"] = pd.array([pd.NA] * len(df), dtype="Int64")
    df["n_without"] = pd.array([pd.NA] * len(df), dtype="Int64")

    crop_raw = common.omap(raw["Crop_type"], _s)
    mapped = common.omap(crop_raw, lambda c: crops.get(SOURCE, c) if crops else None)
    df["crop"] = [m[0] if m else c for m, c in zip(mapped, crop_raw)]
    df["crop_group"] = [m[1] if m else None for m in mapped]
    log.parse("crop_harmonised_by_lookup", int(mapped.notna().sum()))
    log.parse("crop_not_in_lookup_kept_raw_group_null", int((mapped.isna() & crop_raw.notna()).sum()))
    log.parse("crop_blank", int(crop_raw.isna().sum()))

    df["duration_years"] = pd.to_numeric(raw["duration_o"], errors="coerce")
    df["study_design"] = None
    df["replication"] = None
    df["scale"] = common.omap(raw["Scale"], _s)
    df["quality_flag"] = "NR"
    df["ctx_reported_rain_mm"] = pd.to_numeric(raw["Rainfall"], errors="coerce").where(lambda s: s > 0)
    df["ctx_reported_altitude_m"] = pd.to_numeric(raw["Altitude_r"], errors="coerce").where(lambda s: s > 0)
    df["ctx_reported_slope_pct"] = pd.to_numeric(raw["Slope____"], errors="coerce")
    df["ctx_reported_soil"] = common.omap(raw["Soil_type"], _s)
    df["ctx_reported_aez"] = common.omap(raw["Agro_zone"], _s)
    log.parse("ctx_rain_or_altitude_zero_set_null",
              int(((pd.to_numeric(raw["Rainfall"], errors="coerce") <= 0)
                   | (pd.to_numeric(raw["Altitude_r"], errors="coerce") <= 0)).sum()))
    df["ctx_release"] = None
    df["evidence_text"] = None
    df["extraction_locator"] = None
    df["licence"] = LICENCE
    df["hlpe_principle"] = None
    df["mfl_domain"] = None

    df["row_id"] = common.make_row_ids(SOURCE, df["study_id"])
    dup_of = common.mark_duplicates(raw, RAW_COLUMNS, df["row_id"])
    log.parse("exact_duplicate_of_earlier_row_flagged_in_extra", int(dup_of.notna().sum()))
    df["extra"] = [
        common.json_extra({
            "CSA_practi": _s(p), "CSA_Pilar": _s(pl), "Region": _s(rg),
            "Crop_type": c, "Reference": _s(rf) if not ref(sid, "citation") else None,
            "Indicator_normalised": k, "dup_of": d,
        })
        for p, pl, rg, c, rf, sid, k, d in zip(
            raw["CSA_practi"], raw["CSA_Pilar"], raw["Region"], crop_raw, raw["Reference"],
            df["study_id"], df["_outcome_key"], dup_of,
        )
    ]
    df["lrr"] = common.lrr_series(df["mean_with"], df["mean_without"])
    df["var_lrr"] = np.nan
    log.parse("lrr_computable_both_means_positive", int(df["lrr"].notna().sum()))
    log.parse("lrr_null_mean_missing_or_not_positive", int(df["lrr"].isna().sum()))
    log.drop("rows_dropped_by_loader", 0)
    log.note("The workbook reports no dispersion or sample sizes: `sd_*`, `se_*`, `n_*`, `var_lrr` are null "
             "and `weight` is the quality-based default.")
    log.note("`practice_raw` is `CSA_catago` (the frozen `CSA_practices` label of the CSA rows); "
             "`CSA_practi` is in `extra`.")
    logger.info("CSA: %d rows read, %d kept", len(raw), len(df))
    return df, log, raw


def main(argv: list[str] | None = None) -> int:
    """CLI: load and summarise."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", type=Path, default=RAW_PATH)
    ap.add_argument("--dry-run", action="store_true", help="load and report only (default for this loader)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    common.setup_logging(args.verbose)
    df, log, _ = load(args.input)
    print(f"CSA rows: {len(df):,}; studies {df.study_id.nunique()}; lrr {df.lrr.notna().sum():,}")
    for k, v in log.parsing.items():
        print(f"  {k}: {v:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
