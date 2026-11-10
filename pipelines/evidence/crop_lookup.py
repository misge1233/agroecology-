#!/usr/bin/env python3
"""Crop harmonisation lookup: raw crop label -> (``crop_type``, ``Crop_group``).

The rule that produced ``crop_type`` and ``Crop_group`` in the frozen dataset
(``docs/reports/ERA_preprocessing_report.md`` steps 7-8,
``dataset_preprocessing_report.md`` steps 7-8) was applied by a script that is
not in the repository; ``pipelines/dataset/`` holds no crop-group function. The
rule survives only in the frozen per-source files
``data/processed/ERA_Ethiopia_model_ready.csv`` and
``data/processed/CSA_practices_model_ready.csv``. This module recovers it as
data, not code: it applies the documented scope and drop rules to the raw rows
(which reproduces those files row for row, asserted), pairs each raw crop label
with the harmonised value on the same row, and asserts that every raw label maps
to exactly one ``(crop_type, Crop_group)`` pair. The result is
``data/taxonomy/crop_harmonisation.csv`` (in git); loaders read it, and raw
labels not in it keep their raw name with ``crop_group = null`` (counted).

Usage::

    python pipelines/evidence/crop_lookup.py [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.evidence import common  # noqa: E402

logger = logging.getLogger(__name__)

LOOKUP_PATH = common.TAXONOMY_DIR / "crop_harmonisation.csv"
ERA_MODEL_READY = common.DATA_DIR / "processed" / "ERA_Ethiopia_model_ready.csv"
CSA_MODEL_READY = common.DATA_DIR / "processed" / "CSA_practices_model_ready.csv"
COLUMNS = ["source", "crop_raw", "crop", "crop_group", "n_rows", "method"]


@dataclass
class CropLookup:
    """``(source, raw label) -> (crop, crop_group)``."""

    table: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)

    def get(self, source: str, raw: str | None) -> tuple[str, str] | None:
        """Mapped pair, or ``None`` when the raw label is not in the lookup."""
        if raw is None:
            return None
        return self.table.get((source, " ".join(str(raw).split())))

    def __len__(self) -> int:
        return len(self.table)

    def crops(self) -> dict[str, str]:
        """Harmonised crop name (lower case) -> crop group, over all sources."""
        return {c.lower(): g for (c, g) in self.table.values()}


def load_lookup(path: Path = LOOKUP_PATH, missing_ok: bool = False) -> CropLookup:
    """Read the lookup CSV (empty lookup when absent and ``missing_ok``)."""
    if not path.exists():
        if missing_ok:
            logger.warning("crop lookup %s missing: crops kept raw, crop_group null", path)
            return CropLookup()
        raise FileNotFoundError(f"{path} missing: run `python pipelines/evidence/crop_lookup.py`")
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    return CropLookup({(r.source, r.crop_raw): (r.crop, r.crop_group) for r in t.itertuples()})


def _pairs(raw_crop: pd.Series, final: pd.DataFrame, source: str) -> pd.DataFrame:
    pairs = pd.DataFrame({
        "source": source,
        "crop_raw": raw_crop.values,
        "crop": final["crop_type"].values,
        "crop_group": final["Crop_group"].values,
    })
    g = pairs.groupby(["source", "crop_raw"])
    n_pairs = g[["crop", "crop_group"]].nunique()
    amb = n_pairs[(n_pairs["crop"] > 1) | (n_pairs["crop_group"] > 1)]
    if len(amb):
        raise AssertionError(f"{source}: raw crop labels with several harmonised values: {list(amb.index)}")
    out = g.agg(crop=("crop", "first"), crop_group=("crop_group", "first"), n_rows=("crop", "size")).reset_index()
    out["method"] = "derived_from_frozen_model_ready"
    return out


def derive() -> pd.DataFrame:
    """Rebuild the lookup from the raw files and the frozen per-source files."""
    from pipelines.evidence import load_csa, load_era, reconcile

    empty = CropLookup()
    era, _, _ = load_era.load(crops=empty)
    csa, _, _ = load_csa.load(crops=empty)
    era_kept = reconcile.legacy_era(era, dedup=False)
    csa_kept = reconcile.legacy_csa(csa, dedup=False)
    era_mr = pd.read_csv(ERA_MODEL_READY)
    csa_mr = pd.read_csv(CSA_MODEL_READY)
    for name, kept, mr, sid in (("ERA", era_kept, era_mr, "ERA_" + era_mr["Study_No_"].astype(str)),
                                ("CSA", csa_kept, csa_mr, "CSA_" + csa_mr["Study_No_"].astype(str))):
        if len(kept) != len(mr):
            raise AssertionError(f"{name}: legacy filter gives {len(kept)} rows, model-ready file has {len(mr)}")
        same = (
            (kept["study_id"].values == sid.values).all()
            and (kept["practice_raw"].values == mr["CSA_practices"].values).all()
            and ((kept["lrr"].values - mr["log_response_ratio"].values).__abs__() < 1e-6).all()
        )
        if not same:
            raise AssertionError(f"{name}: filtered rows are not aligned with {name} model-ready rows")
    era_tab = _pairs(era_kept["crop"], era_mr, "ERA")
    csa_tab = _pairs(csa_kept["crop"], csa_mr, "CSA")
    return pd.concat([era_tab, csa_tab], ignore_index=True)[COLUMNS]


def main(argv: list[str] | None = None) -> int:
    """CLI: derive and write ``data/taxonomy/crop_harmonisation.csv``."""
    ap = argparse.ArgumentParser(description="Derive the crop harmonisation lookup from the frozen files.")
    ap.add_argument("--dry-run", action="store_true", help="derive and print, write nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    common.setup_logging(args.verbose)
    tab = derive()
    print(f"crop lookup: {len(tab)} raw labels ({(tab.source == 'ERA').sum()} ERA, {(tab.source == 'CSA').sum()} CSA)")
    if args.dry_run:
        print(tab.to_string(index=False))
        return 0
    LOOKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    tab.to_csv(LOOKUP_PATH, index=False, lineterminator="\n", encoding="utf-8")
    print(f"wrote {LOOKUP_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
