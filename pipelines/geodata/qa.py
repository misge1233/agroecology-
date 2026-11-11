#!/usr/bin/env python3
"""Quality checks of a release (brief E3 A1, A3), wrapping ``pipelines/features/final_qa.py``.

Per layer (``check_layer``): alignment with the country grid, dtype and nodata as
declared in ``sources.yaml``, nodata share inside the country mask against
``max_nodata_share``, values inside ``[valid_min, valid_max]``, categorical codes
inside ``classes``, and a non-constant field. Any of these failing is ``fail``.
For the 11 legacy layers ``compare_legacy`` compares the release with the current
stack (``LAYERS_DIR``) cell for cell: integers exactly, floats within 1e-3;
a difference is ``warn`` and is listed, never hidden (brief B1).

``dataset_qa`` is the model-ready dataset check of ``final_qa.py`` (missing values,
numeric ranges, cardinalities, target by indicator, ``response_ratio ==
exp(log_response_ratio)``), moved here so ``final_qa.py`` imports it.

CLI (profile any stack, e.g. the legacy one)::

    python pipelines/geodata/qa.py --dir geodata/layers --country ET
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "pipelines.geodata"

from .core import Catalog, LayerSpec, array_stats, data_sha256, load_catalog, nodata_mask, read_band  # noqa: E402
from .grid import Grid  # noqa: E402

FLOAT_TOL = 1e-3
ORDER = {"pass": 0, "warn": 1, "fail": 2}


def _worst(checks: list[dict[str, Any]]) -> str:
    return max((c["status"] for c in checks), key=lambda s: ORDER[s], default="pass")


def check_array(arr: np.ndarray, profile: dict[str, Any], spec: LayerSpec, grid: Grid,
                mask: np.ndarray | None) -> dict[str, Any]:
    """QA of one layer already in memory (``profile`` from rasterio)."""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, level: str = "fail") -> None:
        checks.append({"check": name, "status": "pass" if ok else level, "detail": detail})

    add("alignment", grid.matches(profile["transform"], (profile["height"], profile["width"]), profile["crs"]),
        f"transform {tuple(round(x, 9) for x in tuple(profile['transform'])[:6])}, "
        f"{profile['width']} x {profile['height']}, {profile['crs']}")
    add("dtype", str(profile["dtype"]) == spec.dtype, f"{profile['dtype']} (declared {spec.dtype})")
    nd = profile.get("nodata")
    add("nodata", nd is not None and float(nd) == float(spec.nodata), f"{nd} (declared {spec.nodata})")
    stats = array_stats(arr, spec, mask)
    share = stats.get("nodata_share_in_mask")
    add("nodata_share", share is not None and share <= spec.max_nodata_share,
        f"{share} inside the country mask (max {spec.max_nodata_share})")
    valid = ~nodata_mask(arr, spec.nodata)
    if spec.categorical and spec.classes:
        codes = set(int(c) for c in np.unique(arr[valid]))
        extra = sorted(codes - set(spec.classes))
        add("classes", not extra, f"codes {sorted(codes)}" + (f"; undeclared {extra}" if extra else ""))
    elif not spec.categorical:
        v = arr[valid]
        lo = spec.valid_min if spec.valid_min is not None else -np.inf
        hi = spec.valid_max if spec.valid_max is not None else np.inf
        n_out = int(((v < lo) | (v > hi)).sum()) if v.size else 0
        add("range", n_out == 0, f"{n_out} values outside [{lo}, {hi}]"
            + (f"; observed {float(v.min()):.4g} to {float(v.max()):.4g}" if v.size else ""))
        add("not_constant", v.size > 0 and float(v.std()) > 0, f"sd {float(v.std()) if v.size else float('nan'):.4g}",
            level="warn")
    return {"layer": spec.id, "status": _worst(checks), "checks": checks, "stats": stats}


def check_layer(path: Path, spec: LayerSpec, grid: Grid, mask: np.ndarray | None) -> dict[str, Any]:
    """QA of one layer file."""
    arr, prof = read_band(path)
    return check_array(arr, prof, spec, grid, mask)


def compare_arrays(new: np.ndarray, old: np.ndarray, spec: LayerSpec, mask: np.ndarray | None = None,
                   tol: float = FLOAT_TOL) -> dict[str, Any]:
    """Cell-for-cell comparison of two layers on the same grid."""
    if new.shape != old.shape:
        return {"equal": False, "detail": f"shapes differ {new.shape} vs {old.shape}"}
    nd_new, nd_old = nodata_mask(new, spec.nodata), nodata_mask(old, spec.nodata)
    nodata_mismatch = int((nd_new != nd_old).sum())
    both = ~nd_new & ~nd_old
    if spec.categorical or new.dtype.kind in "iu":
        n_diff = int((new[both] != old[both]).sum())
        max_abs = float(np.abs(new[both].astype("int64") - old[both].astype("int64")).max()) if both.any() else 0.0
    else:
        d = np.abs(new[both].astype("float64") - old[both].astype("float64"))
        n_diff = int((d > tol).sum())
        max_abs = float(d.max()) if d.size else 0.0
    out: dict[str, Any] = {"equal": nodata_mismatch == 0 and n_diff == 0,
                           "identical": data_sha256(new) == data_sha256(old), "cells_differing": n_diff,
                           "nodata_mismatch": nodata_mismatch, "newly_valid": int((~nd_new & nd_old).sum()),
                           "newly_nodata": int((nd_new & ~nd_old).sum()), "max_abs_diff": max_abs,
                           "tolerance": 0 if spec.categorical else tol, "within_tolerance": None}
    if mask is not None and not out["equal"]:
        inside = mask & both
        if spec.categorical:
            out["cells_differing_in_mask"] = int((new[inside] != old[inside]).sum())
        else:
            out["cells_differing_in_mask"] = int((np.abs(new[inside].astype("float64")
                                                         - old[inside].astype("float64")) > tol).sum())
    tol_spec = spec.raw.get("legacy_tolerance") if isinstance(spec.raw, dict) else None
    if not spec.categorical and new.dtype.kind == "f" and (tol_spec or not out["equal"]):
        region = (mask & both) if mask is not None and mask.shape == new.shape else both
        dd = np.abs(new[region].astype("float64") - old[region].astype("float64"))
        if dd.size:
            q50, q95, q99 = np.percentile(dd, [50, 95, 99])
            out["abs_diff"] = {"median": float(q50), "p95": float(q95), "p99": float(q99), "max": float(dd.max()),
                               "cells": int(dd.size), "region": "mask" if region is not both else "all"}
        del dd
    if tol_spec and out.get("abs_diff"):
        stats = out["abs_diff"]
        checks = {k: bool(stats[k.replace("_abs", "")] <= float(v)) for k, v in tol_spec.items()
                  if k in ("median_abs", "p95_abs", "p99_abs")}
        out.update(tolerance_spec=dict(tol_spec), tolerance_checks=checks, within_tolerance=all(checks.values()))
    out["accepted"] = bool(out["equal"] or out["within_tolerance"])
    return out


def compare_legacy(release_dir: Path, legacy_dir: Path, catalog: Catalog, mask: np.ndarray | None,
                   layers: list[str] | None = None) -> dict[str, Any]:
    """Compare every legacy layer of a release with the current stack."""
    out: dict[str, Any] = {}
    for lid in layers or catalog.legacy_ids():
        new_p, old_p = release_dir / f"{lid}.tif", legacy_dir / f"{lid}.tif"
        if not new_p.exists() or not old_p.exists():
            out[lid] = {"equal": False, "detail": f"missing {'release' if not new_p.exists() else 'legacy'} file"}
            continue
        new, old = read_band(new_p)[0], read_band(old_p)[0]
        out[lid] = compare_arrays(new, old, catalog.layers[lid], mask)
    return out


def summarise(layer_reports: dict[str, dict[str, Any]], legacy: dict[str, Any], catalog: Catalog,
              entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The ``qa_report.json`` body: per-layer results, legacy comparison, overall status."""
    req_fail = [lid for lid, spec in catalog.layers.items() if spec.required and (
        entries.get(lid, {}).get("status") != "built" or layer_reports.get(lid, {}).get("status") == "fail")]
    opt_fail = [lid for lid, r in layer_reports.items() if r["status"] == "fail" and lid not in req_fail]
    legacy_diff = [lid for lid, r in legacy.items() if not r.get("accepted", r.get("equal"))]
    legacy_tol = [lid for lid, r in legacy.items() if r.get("within_tolerance") and not r.get("equal")]
    status = "fail" if req_fail else ("warn" if (opt_fail or legacy_diff) else "pass")
    return {"status": status, "required_failed": req_fail, "optional_failed": opt_fail,
            "legacy_layers_differing": legacy_diff, "legacy_layers_within_tolerance": legacy_tol,
            "layers": layer_reports, "legacy_comparison": legacy,
            "not_built": {lid: {"status": e.get("status"), "reason": e.get("reason")}
                          for lid, e in entries.items() if e.get("status") != "built"}}


# ------------------------------------------------------------ final_qa.py logic (dataset)
DATASET_FEATURES = ["CSA_practices", "practice_family", "Crop_group", "crop_type", "aez_belt", "Indicator",
                    "Rainfall", "Altitude_r", "slope", "temp_mean_annual", "precip_seasonality", "lgp_days",
                    "soil_clay", "soil_ph", "land_cover", "soil_soc"]
DATASET_TARGET = "log_response_ratio"
DATASET_NUM = ["Rainfall", "Altitude_r", "slope", "temp_mean_annual", "precip_seasonality", "lgp_days",
               "soil_clay", "soil_ph", "soil_soc", "response_ratio", "log_response_ratio"]


def dataset_qa(m: Any, out=print) -> bool:
    """The model-ready dataset QA of final_qa.py; returns the response-ratio sanity result."""
    out("shape:", m.shape)
    out("total missing:", int(m.isna().sum().sum()))
    out("missing in features+target:", int(m[DATASET_FEATURES + [DATASET_TARGET]].isna().sum().sum()))
    out("exact dup rows (all cols):", int(m.duplicated().sum()))
    out("\n--- numeric ranges ---")
    for c in DATASET_NUM:
        s = m[c]
        out(f"  {c:20s} min={s.min():.3f} max={s.max():.3f} mean={s.mean():.3f}")
    out("\n--- categorical cardinality ---")
    for c in ["source", "practice_family", "Crop_group", "crop_type", "aez_belt", "Indicator", "land_cover"]:
        out(f"  {c:16s} {m[c].nunique()} levels")
    out("\n--- target by indicator ---")
    out(m.groupby("Indicator")[DATASET_TARGET].agg(["count", "mean", "std"]).round(3))
    out("\n--- rows by source ---")
    out(m.source.value_counts())
    out("\n--- practice_family ---")
    out(m.practice_family.value_counts())
    ok = bool(np.allclose(m.response_ratio, np.exp(m.log_response_ratio), rtol=1e-4))
    out("\nresponse_ratio == exp(log_response_ratio):", ok)
    out("groups (Study_No_):", m.Study_No_.nunique(), "| rows/group max", m.groupby("Study_No_").size().max())
    return ok


# ------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    from pipelines.common.country_config import load_country

    from .grid import grid_for_country

    ap = argparse.ArgumentParser(description="QA of a layer folder against sources.yaml")
    ap.add_argument("--dir", type=Path, required=True, help="folder with <layer>.tif files (release or legacy)")
    ap.add_argument("--country", default="ET")
    ap.add_argument("--out", type=Path, help="write the JSON report here")
    a = ap.parse_args(argv)
    cat = load_catalog()
    cfg = load_country(a.country, check_files=False)
    grid, _ = grid_for_country(cfg)
    mask = None
    belt = a.dir / "aez_belt.tif"
    if belt.exists():
        mask = read_band(belt)[0] > 0
    reports = {}
    for lid, spec in cat.layers.items():
        p = a.dir / f"{lid}.tif"
        if p.exists():
            reports[lid] = check_layer(p, spec, grid, mask)
            r = reports[lid]
            share = r["stats"].get("nodata_share_in_mask")
            print(f"{lid:26s} {r['status']:4s}  nodata in mask {share}  "
                  + "; ".join(f"{c['check']}={c['status']}" for c in r["checks"] if c["status"] != "pass"))
    if a.out:
        a.out.write_text(json.dumps(reports, indent=2, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
