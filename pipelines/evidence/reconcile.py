"""Reconciliation of the store with the frozen model-ready dataset (brief B1, B2).

Applying the documented legacy scope filter and drop rules to the loaded frame
must reproduce the ERA (7,250) and CSA (1,414) rows of
``data/processed/CSA_ERA_final_model_ready.csv``: same
``(study_id, practice_raw, Indicator, crop)`` multiset and ``lrr`` equal within
1e-9.

Legacy rules (``docs/reports/ERA_preprocessing_report.md``,
``dataset_preprocessing_report.md``, ``merged_dataset_notes.md``), in order:

ERA
  1. scope: ``Out.SubInd`` in the 7 mapped indicators;
  2. both means > 0;
  3. ``response_ratio <= 20``;
  4. merge-time duplicate removal (see below).

CSA
  1. scope: normalised ``Indicator`` in the 7 shared indicators (``net income``
     -> ``income``; the bare ``income`` label was not in the 10-indicator scope);
  2. exact duplicate workbook rows removed (keep first);
  3. zero/missing coordinates removed; 4. outside the stack extent removed;
  5. both means > 0; 6. ``response_ratio <= 20``;
  7. rows with a blank ``Crop_type`` removed (**not written in the report**,
     which says "blank -> Unspecified"; the frozen file holds no
     ``Unspecified`` crop and all 110 blank-crop rows in scope are absent);
  8. merge-time duplicate removal.

Merge-time duplicate removal (``merged_dataset_notes.md``, "681 exact
duplicates identical across all features + target") was applied to every
column **except** ``Study_No_``: rows of two different studies with the same
site, practice, crop, indicator and ratio were collapsed, keeping the first in
file order. Verified on the frozen files: dropping duplicates on all columns
reproduces 7,264 ERA rows (14 too many), on all columns but ``Study_No_``
exactly 7,250. Here the key is ``(lat, lon, practice_raw, crop, crop_group,
Indicator, lrr)`` with exact float equality, as the original in-memory pandas dedup; the 10 raster features of the frozen file are
functions of ``(lat, lon)`` so they add nothing to the key.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pipelines.evidence import common

logger = logging.getLogger(__name__)

FINAL_PATH = common.DATA_DIR / "processed" / "CSA_ERA_final_model_ready.csv"
ERA_SCOPE = {
    "Crop Yield": "yield", "Biomass Yield": "biomass yield", "Net Return": "income",
    "Water Use Efficiency": "water use efficiency", "Soil Organic Matter": "SOM content",
    "Erosion": "soil loss", "Runoff": "runoff",
}
CSA_SCOPE = {
    "yield": "yield", "biomass yield": "biomass yield", "net income": "income",
    "water use efficiency": "water use efficiency", "som content": "SOM content",
    "soil loss": "soil loss", "runoff": "runoff",
}
MAX_RATIO = 20.0
STACK_BBOX = {"lat_min": 3.3, "lat_max": 14.9, "lon_min": 32.9, "lon_max": 48.2}
DEDUP_KEY = ["lat", "lon", "practice_raw", "crop", "crop_group", "Indicator", "_lrr_exact"]


def _extra(df: pd.DataFrame, key: str) -> pd.Series:
    return df["extra"].map(lambda s: json.loads(s).get(key) if isinstance(s, str) else None)


def _cross_study_dedup(df: pd.DataFrame, steps: list[tuple[str, int]]) -> pd.DataFrame:
    work = df.assign(_lrr_exact=df["lrr"])
    keyed = common.row_key(work, DEDUP_KEY)
    keep =~keyed.duplicated(keep="first")
    steps.append(("merge_duplicates_ignoring_study_id", int((~keep).sum())))
    return df[keep.values]


def legacy_era(df: pd.DataFrame, dedup: bool = True, steps: list | None = None) -> pd.DataFrame:
    """ERA rows the frozen dataset kept, with a legacy ``Indicator`` column."""
    steps = steps if steps is not None else []
    out = df.assign(Indicator=_extra(df, "Out.SubInd").map(ERA_SCOPE))
    n0 = len(out)
    out = out[out["Indicator"].notna()]
    steps.append(("out_of_7_indicator_scope", n0 - len(out)))
    n0 = len(out)
    out = out[(out["mean_with"] > 0) & (out["mean_without"] > 0)]
    steps.append(("mean_not_positive", n0 - len(out)))
    n0 = len(out)
    out = out[(out["mean_with"] / out["mean_without"]) <= MAX_RATIO]
    steps.append(("response_ratio_gt_20", n0 - len(out)))
    if dedup:
        out = _cross_study_dedup(out, steps)
    return out


def legacy_csa(df: pd.DataFrame, dedup: bool = True, steps: list | None = None) -> pd.DataFrame:
    """CSA rows the frozen dataset kept, with a legacy ``Indicator`` column."""
    steps = steps if steps is not None else []
    key = _extra(df, "Indicator_normalised")
    out = df.assign(Indicator=key.map(CSA_SCOPE), _dup=_extra(df, "dup_of"))
    n0 = len(out)
    out = out[out["Indicator"].notna()]
    steps.append(("out_of_7_indicator_scope", n0 - len(out)))
    n0 = len(out)
    out = out[out["_dup"].isna()]
    steps.append(("exact_duplicate_workbook_row", n0 - len(out)))
    n0 = len(out)
    out = out[out["lat"].notna() & out["lon"].notna()]
    steps.append(("zero_or_missing_coordinates", n0 - len(out)))
    n0 = len(out)
    b = STACK_BBOX
    out = out[out["lat"].between(b["lat_min"], b["lat_max"]) & out["lon"].between(b["lon_min"], b["lon_max"])]
    steps.append(("outside_stack_extent", n0 - len(out)))
    n0 = len(out)
    out = out[(out["mean_with"] > 0) & (out["mean_without"] > 0)]
    steps.append(("mean_not_positive", n0 - len(out)))
    n0 = len(out)
    out = out[(out["mean_with"] / out["mean_without"]) <= MAX_RATIO]
    steps.append(("response_ratio_gt_20", n0 - len(out)))
    n0 = len(out)
    out = out[out["crop"].notna()]
    steps.append(("blank_crop_type (undocumented rule, see module docstring)", n0 - len(out)))
    out = out.drop(columns=["_dup"])
    if dedup:
        out = _cross_study_dedup(out, steps)
    return out


@dataclass
class ReconResult:
    """Outcome of one reconciliation."""

    source: str
    n_expected: int
    n_reproduced: int
    only_in_store: int
    only_in_frozen: int
    max_abs_lrr_diff: float
    steps: list[tuple[str, int]] = field(default_factory=list)
    cross_study_examples: list[dict[str, Any]] = field(default_factory=list)

    @property
    def exact(self) -> bool:
        """True when the multisets agree and lrr agrees within 1e-9."""
        return (self.only_in_store == 0 and self.only_in_frozen == 0
                and self.n_expected == self.n_reproduced and self.max_abs_lrr_diff <= 1e-9)

    def markdown(self) -> str:
        """Card section."""
        lines = [
            f"Legacy rules applied to the store's {self.source} rows, in order:", "",
            "| Step | Rows removed |", "|---|---:|",
        ]
        lines += [f"| {k} | {v:,} |" for k, v in self.steps]
        lines += [
            "",
            f"- Frozen dataset ({FINAL_PATH.relative_to(common.REPO_ROOT).as_posix()}): "
            f"**{self.n_expected:,}** {self.source} rows; reproduced: **{self.n_reproduced:,}**.",
            f"- Multiset `(study_id, practice_raw, Indicator, crop)` with `lrr` rounded to 1e-9: "
            f"{self.only_in_store} rows only in the store, {self.only_in_frozen} only in the frozen file.",
            f"- Max |lrr difference| over matched rows: {self.max_abs_lrr_diff:.3g}.",
            f"- **Result: {'EXACT MATCH' if self.exact else 'RESIDUAL DIFFERENCES (see below)'}**",
        ]
        if self.cross_study_examples:
            lines += ["", "Rows collapsed by the merge-time duplicate rule across *different* studies "
                      "(the frozen file kept the first study in file order):", "",
                      "| Kept | Dropped | Practice | Crop | Indicator | lrr |", "|---|---|---|---|---|---:|"]
            for e in self.cross_study_examples:
                lines.append(f"| {e['kept']} | {e['dropped']} | {e['practice']} | {e['crop']} | "
                             f"{e['indicator']} | {e['lrr']:.6f} |")
        return "\n".join(lines)


def _keys(df: pd.DataFrame, study: str, prac: str, crop: str, lrr: str) -> Counter:
    return Counter(zip(df[study], df[prac], df["Indicator"], df[crop], df[lrr].round(9)))


def _cross_study(pre: pd.DataFrame) -> list[dict[str, Any]]:
    work = pre.assign(_lrr_exact=pre["lrr"])
    keyed = common.row_key(work, DEDUP_KEY)
    out = []
    for _, grp in work.groupby(keyed.values, sort=False):
        if len(grp) < 2 or grp["study_id"].nunique() < 2:
            continue
        first = grp.iloc[0]
        for _, r in grp.iloc[1:].iterrows():
            if r["study_id"] != first["study_id"]:
                out.append({"kept": first["row_id"], "dropped": r["row_id"], "practice": r["practice_raw"],
                            "crop": r["crop"], "indicator": r["Indicator"], "lrr": float(r["lrr"])})
    return out


def reconcile(df: pd.DataFrame, source: str, final_path: Path = FINAL_PATH) -> ReconResult:
    """Apply the legacy rules for ``source`` to ``df`` and compare with the frozen file."""
    final = pd.read_csv(final_path)
    fin = final[final["source"] == source]
    steps: list[tuple[str, int]] = []
    fn = legacy_era if source == "ERA" else legacy_csa
    pre = fn(df, dedup=False)
    kept = fn(df, dedup=True, steps=steps)
    a = _keys(kept, "study_id", "practice_raw", "crop", "lrr")
    b = _keys(fin, "Study_No_", "CSA_practices", "crop_type", "log_response_ratio")
    merged = kept.sort_values(["study_id", "practice_raw", "Indicator", "crop", "lrr"])
    fin_sorted = fin.sort_values(["Study_No_", "CSA_practices", "Indicator", "crop_type", "log_response_ratio"])
    diff = np.nan
    if len(merged) == len(fin_sorted):
        diff = float(np.max(np.abs(merged["lrr"].values - fin_sorted["log_response_ratio"].values))) if len(merged) else 0.0
    res = ReconResult(
        source=source, n_expected=len(fin), n_reproduced=len(kept),
        only_in_store=int(sum((a - b).values())), only_in_frozen=int(sum((b - a).values())),
        max_abs_lrr_diff=diff if not np.isnan(diff) else float("inf"), steps=steps,
        cross_study_examples=_cross_study(pre),
    )
    logger.info("%s reconciliation: expected %d, reproduced %d, exact=%s",
                source, res.n_expected, res.n_reproduced, res.exact)
    return res
