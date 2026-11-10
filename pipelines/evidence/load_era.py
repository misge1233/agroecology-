#!/usr/bin/env python3
"""Load ERA Ethiopia (all outcomes, not only the 7 indicators) into the evidence schema.

Input ``data/raw/ERA_Ethiopia_dataset.csv`` (14,792 rows, 137 columns, 306
studies). Every row is kept: rows the model cannot use (non-positive means,
outcomes outside the 7 legacy indicators) stay in the store with ``lrr`` null or
their own ``outcome_id``; the legacy scope and drop rules are applied only by the
reconciliation (:mod:`pipelines.evidence.reconcile`).

Mapping (brief B1): ``study_id = "ERA_" + Code`` (identical to ``Study_No_``);
``practice_raw = PrName``; ``outcome_raw = Partial.Outcome.Name`` when it names a
partial outcome, else the ERA outcome name (``Out.SubInd``) for ``Outcode``;
``mean_with = MeanT``, ``mean_without = MeanC``; SE converted to SD with ``Rep``;
``lrr = ln(MeanT / MeanC)`` always (``MeanFlip`` kept in ``extra``, never applied).

Usage::

    python pipelines/evidence/load_era.py [--dry-run] [--input PATH]
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.evidence import common, crop_lookup, schema  # noqa: E402
from pipelines.evidence.common import RuleLog  # noqa: E402

logger = logging.getLogger(__name__)

SOURCE = "ERA"
RAW_PATH = common.DATA_DIR / "raw" / "ERA_Ethiopia_dataset.csv"
LICENCE = "ERA-Dataverse-terms"
CARD_PATH = common.CARDS_DIR / "ERA.md"

#: ``Mean.Error.Type`` -> how the error columns are stored.
SD_TYPES = {"SD (Standard Deviation)", "Grouped SD (Standard Deviation)"}
SE_TYPES = {"SE (Standard Error)", "Grouped SE (Standard Error)", "Grouped SEM (Standard Error of Mean)"}
# CV and SED are not convertible to a per-group SD without more information: extra only.

ISO3_TO_ISO2 = {"ETH": "ET", "KEN": "KE"}
TREATMENT_CODE_COLS = [f"T{i}" for i in range(1, 15)]
CONTROL_CODE_COLS = [f"C{i}" for i in range(1, 15)]
MAX_DURATION_YEARS = 50.0
NOT_PARTIAL = {"not assessed", ""}


def _s(v) -> str | None:
    return common.clean_str(v, missing=("", "nan", "na"))


def _codes(row: pd.Series, cols: list[str]) -> list[str]:
    out = []
    for c in cols:
        v = _s(row.get(c))
        if v:
            out.append(v)
    return out


def read_raw(path: Path = RAW_PATH) -> pd.DataFrame:
    """Read the raw ERA CSV untouched (strings kept as read by pandas)."""
    if not path.exists():
        raise FileNotFoundError(f"ERA input not found: {path}")
    return pd.read_csv(path, low_memory=False)


def load(path: Path = RAW_PATH, crops: crop_lookup.CropLookup | None = None) -> tuple[pd.DataFrame, RuleLog, pd.DataFrame]:
    """Return ``(frame, rule_log, raw)``: the ERA rows in the evidence schema.

    ``frame`` has ``practice_id``/``outcome_id``/``direction`` unset (the
    taxonomies fill them in :mod:`build_evidence_store`); the private column
    ``_outcome_key`` (the ERA outcome name) is what the outcome aliases match.
    """
    raw = read_raw(path)
    log = RuleLog()
    crops = crops if crops is not None else crop_lookup.load_lookup(missing_ok=True)
    n = len(raw)
    df = pd.DataFrame(index=raw.index)

    df["source"] = SOURCE
    df["study_id"] = "ERA_" + raw["Code"].astype(str).str.strip()
    dois = common.omap(raw["DOI"], common.normalise_doi)
    df["doi"] = common.omap(dois, lambda t: t[0])
    doi_other = common.omap(dois, lambda t: t[1])
    log.parse("doi_normalised", int(df["doi"].notna().sum()))
    log.parse("doi_non_doi_identifier_to_extra", int(doi_other.notna().sum()))
    df["citation"] = [
        f"{_s(a) or 'Unknown'} ({int(d) if pd.notna(d) else 'n.d.'}). {_s(j) or ''}".strip().rstrip(".") + "."
        for a, d, j in zip(raw["Author"], raw["Date"], raw["Journal"])
    ]
    df["year"] = pd.to_numeric(raw["Date"], errors="coerce").astype("Int64")
    df["country"] = raw["ISO.3166.1.alpha.3"].map(ISO3_TO_ISO2)
    log.parse("country_from_iso3", int(df["country"].notna().sum()))

    lat = pd.to_numeric(raw["Latitude"], errors="coerce")
    lon = pd.to_numeric(raw["Longitude"], errors="coerce")
    both = lat.notna() & lon.notna()
    df["lat"], df["lon"] = lat.where(both), lon.where(both)
    df["loc_precision"] = np.where(both, "site", "country")
    df["loc_method"] = np.where(both, "reported", "none")
    log.parse("loc_site_reported_coordinates", int(both.sum()))
    log.parse("loc_country_no_coordinates", int((~both).sum()))
    df["site_name"] = common.omap(raw["Site.ID"], _s)

    df["practice_raw"] = common.omap(raw["PrName"], _s)
    df["comparator"] = common.omap(raw["C.Descrip"], _s)

    out_name = common.omap(raw["Out.SubInd"], _s)
    partial = common.omap(raw["Partial.Outcome.Name"], _s)
    has_partial = partial.notna() & ~partial.fillna("").str.lower().isin(NOT_PARTIAL)
    df["outcome_raw"] = partial.where(has_partial, out_name)
    df["_outcome_key"] = out_name
    log.parse("outcome_raw_from_partial_outcome_name", int(has_partial.sum()))
    log.parse("outcome_raw_from_era_outcome_name", int((~has_partial).sum()))
    df["unit"] = common.omap(raw["Units"], _s)

    mt = pd.to_numeric(raw["MeanT"], errors="coerce")
    mc = pd.to_numeric(raw["MeanC"], errors="coerce")
    df["mean_with"], df["mean_without"] = mt, mc
    rep = pd.to_numeric(raw["Rep"], errors="coerce")
    rep = rep.where(rep > 0)
    df["n_with"] = rep.astype("Int64")
    df["n_without"] = rep.astype("Int64")

    etype = common.omap(raw["Mean.Error.Type"], _s)
    et = pd.to_numeric(raw["MeanT.Error"], errors="coerce")
    ec = pd.to_numeric(raw["MeanC.Error"], errors="coerce")
    is_sd = etype.isin(SD_TYPES)
    is_se = etype.isin(SE_TYPES)
    sqrt_n = np.sqrt(rep.astype("float64"))
    df["sd_with"] = et.where(is_sd)
    df["sd_without"] = ec.where(is_sd)
    df["se_with"] = et.where(is_se)
    df["se_without"] = ec.where(is_se)
    # SE -> SD with Rep (brief B1): sd = se * sqrt(n).
    conv_t = is_se & et.notna() & rep.notna()
    conv_c = is_se & ec.notna() & rep.notna()
    df.loc[conv_t, "sd_with"] = et[conv_t] * sqrt_n[conv_t]
    df.loc[conv_c, "sd_without"] = ec[conv_c] * sqrt_n[conv_c]
    log.parse("error_type_sd", int(is_sd.sum()))
    log.parse("error_type_se_converted_to_sd_with_rep", int((conv_t | conv_c).sum()))
    log.parse("error_type_cv_or_sed_kept_in_extra", int((etype.notna() & ~is_sd & ~is_se).sum()))

    crop_raw = common.omap(raw["Product.Simple"], _s)
    mapped = common.omap(crop_raw, lambda c: crops.get(SOURCE, c) if crops else None)
    df["crop"] = [m[0] if m else c for m, c in zip(mapped, crop_raw)]
    df["crop_group"] = [m[1] if m else None for m in mapped]
    log.parse("crop_harmonised_by_lookup", int(mapped.notna().sum()))
    log.parse("crop_not_in_lookup_kept_raw_group_null", int((mapped.isna() & crop_raw.notna()).sum()))

    dur = pd.to_numeric(raw["Duration"], errors="coerce")
    too_long = dur > MAX_DURATION_YEARS
    df["duration_years"] = dur.where(~too_long)
    log.parse(f"duration_gt_{int(MAX_DURATION_YEARS)}_not_years_set_null", int(too_long.sum()))

    df["study_design"] = None
    df["replication"] = None
    df["scale"] = None
    df["quality_flag"] = "NR"
    df["ctx_reported_rain_mm"] = pd.to_numeric(raw["MAP"], errors="coerce")
    df["ctx_reported_altitude_m"] = raw["Elevation"].map(lambda v: common.parse_number(v, kind="context"))
    tex = common.omap(raw["Soil.Texture"], _s)
    ph = pd.to_numeric(raw["Soil.pH"], errors="coerce")
    df["ctx_reported_soil"] = [
        "; ".join(p for p in (t, f"pH {p_:g}" if pd.notna(p_) else None) if p) or None
        for t, p_ in zip(tex, ph)
    ]
    df["ctx_reported_aez"] = common.omap(raw["AEZ16simple"], _s)
    df["ctx_release"] = None
    df["evidence_text"] = None
    df["extraction_locator"] = common.omap(raw["DataLoc"], _s)
    df["licence"] = LICENCE
    df["hlpe_principle"] = None
    df["mfl_domain"] = None

    df["row_id"] = common.make_row_ids(SOURCE, df["study_id"])
    dup_cols = [c for c in raw.columns if c not in ("Unnamed: 0", "Index")]
    dup_of = common.mark_duplicates(raw, dup_cols, df["row_id"])
    log.parse("exact_duplicate_of_earlier_row_flagged_in_extra", int(dup_of.notna().sum()))

    yi = pd.to_numeric(raw["yi"], errors="coerce")
    extras = []
    for i in raw.index:
        r = raw.loc[i]
        extras.append(common.json_extra({
            "Outcode": f"{r['Outcode']:g}" if pd.notna(r["Outcode"]) else None,
            "Out.SubInd": out_name[i],
            "Out.Ind": _s(r["Out.Ind"]),
            "Out.Pillar": _s(r["Out.Pillar"]),
            "SubPrName": _s(r["SubPrName"]),
            "Theme": _s(r["Theme"]),
            "T_codes": _codes(r, TREATMENT_CODE_COLS) or None,
            "C_codes": _codes(r, CONTROL_CODE_COLS) or None,
            "Tree": _s(r["Tree"]),
            "T.Descrip": _s(r["T.Descrip"]),
            "Product": _s(r["Product"]),
            "Product.Simple": crop_raw[i],
            "MeanFlip": _s(r["MeanFlip"]),
            "Mean.Error.Type": etype[i],
            "MeanT.Error": None if pd.isna(et[i]) else float(et[i]),
            "MeanC.Error": None if pd.isna(ec[i]) else float(ec[i]),
            "Upper": _s(r["Upper"]),
            "Lower": _s(r["Lower"]),
            "Duration": None if pd.isna(dur[i]) else float(dur[i]),
            "Mean.Annual.Precip": _s(r["Mean.Annual.Precip"]),
            "MAT": _s(r["MAT"]),
            "AEZ16": _s(r["AEZ16"]),
            "Site.Type": _s(r["Site.Type"]),
            "ERA_Index": int(r["Index"]),
            "yi": None if pd.isna(yi[i]) else float(yi[i]),
            "doi_raw": doi_other[i],
            "dup_of": dup_of[i],
        }))
    df["extra"] = extras

    df["lrr"] = common.lrr_series(df["mean_with"], df["mean_without"])
    log.parse("lrr_computable_both_means_positive", int(df["lrr"].notna().sum()))
    log.parse("lrr_null_mean_missing_or_not_positive", int(df["lrr"].isna().sum()))
    df["var_lrr"] = common.var_lrr_series(df)
    log.parse("var_lrr_delta_method", int(df["var_lrr"].notna().sum()))
    flip = common.omap(raw["MeanFlip"], _s).notna()
    log.parse("meanflip_flag_kept_in_extra_not_applied", int(flip.sum()))
    yi_ok = yi.notna() & df["lrr"].notna()
    yi_diff = (yi[yi_ok] - df.loc[yi_ok, "lrr"]).abs()
    log.note(
        f"ERA's own effect size `yi` is present on {int(yi.notna().sum()):,} rows; where both exist "
        f"it equals ln(MeanT/MeanC) within 1e-6 on {int((yi_diff <= 1e-6).sum()):,} of {int(yi_ok.sum()):,} rows "
        f"(max |diff| {float(yi_diff.max()) if len(yi_diff) else 0:.3g}). The store uses ln(MeanT/MeanC)."
    )
    log.note(
        "`MeanFlip = N` marks rows where ERA notes that lower values are better for the outcome. "
        "The store never flips a mean: `lrr` is always ln(mean_with/mean_without) and the outcome "
        "taxonomy carries the direction."
    )
    for rule in ("rows_dropped_by_loader",):
        log.drop(rule, 0)
    logger.info("ERA: %d rows read, %d kept", n, len(df))
    return df, log, raw


def main(argv: list[str] | None = None) -> int:
    """CLI: load and summarise (``--dry-run`` writes nothing; the store is written by the builder)."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", type=Path, default=RAW_PATH)
    ap.add_argument("--dry-run", action="store_true", help="load and report only (default for this loader)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    common.setup_logging(args.verbose)
    df, log, _ = load(args.input)
    print(f"ERA rows: {len(df):,}; studies {df.study_id.nunique()}; lrr {df.lrr.notna().sum():,}; "
          f"var_lrr {df.var_lrr.notna().sum():,}")
    for k, v in log.parsing.items():
        print(f"  {k}: {v:,}")
    if not args.dry_run:
        print("(the store is written by build_evidence_store.py; this loader only reports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
