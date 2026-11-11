#!/usr/bin/env python3
"""Write geodata context into the evidence store (brief E3 C3).

    python pipelines/evidence/add_context.py --release ET/2026.1 [--dry-run]

For every store row with ``loc_precision`` in (``site``, ``district``) and
``loc_method`` not ``geocoded_llm_unchecked``, the ``ctx_<layer>`` columns of every
built layer of the release are written (nearest-valid fallback within 120 cells, the
rule of ``recommend.py``) and ``ctx_release`` is set. Rows whose point falls outside
the country mask (``aez_belt`` > 0 at the cell itself, no fallback) keep nulls and are
counted. Earlier ``ctx_<layer>`` columns are replaced; ``ctx_reported_*`` are kept.

Reconciliation: for the 7,250 legacy ERA rows of
``data/processed/CSA_ERA_final_model_ready.csv`` the six legacy numeric features
(``Rainfall``, ``Altitude_r``, ``temp_mean_annual``, ``precip_seasonality``,
``slope``, ``soil_clay``) are re-read from the release at the rows' coordinates and
compared with the frozen values (tolerance 1e-3); every difference is reported in
``data/evidence/cards/context_<CC>_<release>.md``.

The store is validated (``schema.validate``, including the ``ctx_*`` range checks
against ``pipelines/geodata/sources.yaml``) before it is written.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "pipelines.evidence"

from pipelines.evidence import common, schema  # noqa: E402
from pipelines.geodata.extract import LEGACY_RADIUS, ContextExtractor  # noqa: E402

logger = logging.getLogger("add_context")

ELIGIBLE_PRECISION = ("site", "district")
EXCLUDED_METHOD = "geocoded_llm_unchecked"
LEGACY_DATASET = common.REPO_ROOT / "data" / "processed" / "CSA_ERA_final_model_ready.csv"
#: frozen dataset column -> release layer (the six legacy numeric features)
RECONCILE = {"Rainfall": "precip_annual", "Altitude_r": "elevation", "temp_mean_annual": "temp_mean_annual",
             "precip_seasonality": "precip_seasonality", "slope": "slope", "soil_clay": "soil_clay"}
TOL = 1e-3


def eligible_mask(df: pd.DataFrame) -> pd.Series:
    """Rows that get context: site/district precision, not an unchecked LLM geocode, coordinates present."""
    return (df["loc_precision"].isin(ELIGIBLE_PRECISION) & (df["loc_method"] != EXCLUDED_METHOD)
            & df["lat"].notna() & df["lon"].notna())


def in_country(ext: ContextExtractor, df: pd.DataFrame) -> pd.Series:
    """True where the row's own cell is inside the country mask (belt > 0, no fallback)."""
    if "aez_belt" not in ext.layers:
        return pd.Series(True, index=df.index)
    belt = ext.batch(df, "lat", "lon", layers=["aez_belt"], max_radius_px=0)["ctx_aez_belt"]
    return belt.fillna(0) > 0


def add_context(df: pd.DataFrame, ext: ContextExtractor) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return the store with ``ctx_<layer>`` and ``ctx_release`` written, and the counts."""
    out = df.copy()
    old = [c for c in out.columns if c.startswith(schema.CTX_PREFIX) and c not in schema.EVIDENCE_COLUMNS
           and not c.startswith(schema.CTX_REPORTED_PREFIX)]
    out = out.drop(columns=old)
    elig = eligible_mask(out)
    inside = pd.Series(False, index=out.index)
    inside[elig] = in_country(ext, out[elig])
    write = elig & inside
    ctx = ext.batch(out[write], "lat", "lon", max_radius_px=LEGACY_RADIUS)
    for col in ctx.columns:
        out[col] = np.nan
        out.loc[write, col] = ctx[col]
    out["ctx_release"] = [ext.release_id if w else None for w in write]
    counts = {
        "release": ext.release_id, "rows": int(len(out)), "eligible": int(elig.sum()),
        "written": int(write.sum()), "outside_country_mask": int((elig & ~inside).sum()),
        "not_eligible": {
            "precision_country_or_none": int((~out["loc_precision"].isin(ELIGIBLE_PRECISION)).sum()),
            "geocoded_llm_unchecked": int((out["loc_precision"].isin(ELIGIBLE_PRECISION)
                                           & (out["loc_method"] == EXCLUDED_METHOD)).sum()),
            "no_coordinates": int((out["loc_precision"].isin(ELIGIBLE_PRECISION)
                                   & (out["loc_method"] != EXCLUDED_METHOD)
                                   & (out["lat"].isna() | out["lon"].isna())).sum()),
        },
        "written_by_source": {str(k): int(v) for k, v in out.loc[write, "source"].value_counts().sort_index().items()},
        "columns": list(ctx.columns),
        "null_after_fallback": {c: int(out.loc[write, c].isna().sum()) for c in ctx.columns
                                if int(out.loc[write, c].isna().sum())},
    }
    return out, counts


def reconcile_legacy(ext: ContextExtractor, dataset: Path = LEGACY_DATASET) -> dict[str, Any]:
    """Six legacy features of the frozen ERA rows re-read from the release (tolerance 1e-3)."""
    if not dataset.exists():
        return {"available": False}
    d = pd.read_csv(dataset)
    era = d[d["source"] == "ERA"].reset_index(drop=True)
    ctx = ext.batch(era, "latitude", "longitude", layers=list(RECONCILE.values()), max_radius_px=LEGACY_RADIUS)
    res: dict[str, Any] = {"available": True, "rows": int(len(era)),
                           "coordinates": int(era[["latitude", "longitude"]].drop_duplicates().shape[0]),
                           "features": {}}
    for col, lid in RECONCILE.items():
        diff = (ctx[f"ctx_{lid}"] - pd.to_numeric(era[col], errors="coerce")).abs()
        res["features"][col] = {"layer": lid, "max_abs_diff": float(diff.max()), "rows_over_tol": int((diff > TOL).sum()),
                                "rows_null": int(diff.isna().sum())}
    res["within_tolerance"] = all(f["rows_over_tol"] == 0 and f["rows_null"] == 0 for f in res["features"].values())
    return res


def summary_stats(df: pd.DataFrame, cols: list[str]) -> dict[str, dict[str, float]]:
    out = {}
    for c in cols:
        v = pd.to_numeric(df[c], errors="coerce").dropna()
        if v.size:
            out[c] = {"n": int(v.size), "min": float(v.min()), "median": float(v.median()), "max": float(v.max())}
    return out


def card_markdown(counts: dict[str, Any], recon: dict[str, Any], stats: dict[str, Any]) -> str:
    lines = [f"# Context from geodata release {counts['release']}", "",
             "Written by `pipelines/evidence/add_context.py` (brief E3 C3). Rows with `loc_precision` site or "
             "district and `loc_method` other than `geocoded_llm_unchecked` get every `ctx_<layer>` of the "
             "release (nearest valid cell within 120 cells, the rule of `recommend.py`).", "",
             f"- rows in the store: {counts['rows']:,}",
             f"- eligible: {counts['eligible']:,}; written: {counts['written']:,}; "
             f"outside the country mask (kept null): {counts['outside_country_mask']:,}",
             f"- not eligible: country/none precision {counts['not_eligible']['precision_country_or_none']:,}, "
             f"unchecked LLM geocode {counts['not_eligible']['geocoded_llm_unchecked']:,}, "
             f"no coordinates {counts['not_eligible']['no_coordinates']:,}",
             "- written by source: " + ", ".join(f"{k} {v:,}" for k, v in counts["written_by_source"].items()), ""]
    if counts.get("null_after_fallback"):
        lines.append("Null after the fallback (no valid cell within 120 cells): "
                     + ", ".join(f"`{k}` {v}" for k, v in counts["null_after_fallback"].items()))
        lines.append("")
    lines += ["## Reconciliation with the frozen dataset (7,250 legacy ERA rows)", ""]
    if not recon.get("available"):
        lines.append("Frozen dataset not found; not run.")
    else:
        lines += [f"{recon['rows']:,} rows at {recon['coordinates']} coordinates; tolerance {TOL}. "
                  f"Result: **{'within tolerance' if recon['within_tolerance'] else 'DIFFERENCES (listed below)'}**.", "",
                  "| Feature | Layer | Max abs diff | Rows over tolerance | Rows null |", "|---|---|---|---|---|"]
        for col, f in recon["features"].items():
            lines.append(f"| `{col}` | `{f['layer']}` | {f['max_abs_diff']:.2e} | {f['rows_over_tol']} | {f['rows_null']} |")
    lines += ["", "## Written values (rows with context)", "", "| Column | n | min | median | max |", "|---|---|---|---|---|"]
    for c, s in stats.items():
        lines.append(f"| `{c}` | {s['n']:,} | {s['min']:.4g} | {s['median']:.4g} | {s['max']:.4g} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write geodata context columns into the evidence store")
    ap.add_argument("--release", required=True, help="e.g. ET/2026.1 (under --geodata-dir)")
    ap.add_argument("--geodata-dir", type=Path, default=common.REPO_ROOT / "geodata")
    ap.add_argument("--store-dir", type=Path, default=common.EVIDENCE_DIR)
    ap.add_argument("--dry-run", action="store_true", help="compute, validate and report; write nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    common.setup_logging(a.verbose)
    from pipelines.taxonomy import taxonomy_io as tio

    ext = ContextExtractor.for_release(a.release, a.geodata_dir, max_radius_px=LEGACY_RADIUS)
    store = schema.read_store(a.store_dir)
    out, counts = add_context(store, ext)
    report = schema.validate(out, strict=False, outcome_directions=tio.Taxonomy.load().outcome_directions())
    recon = reconcile_legacy(ext)
    stats = summary_stats(out[out["ctx_release"].notna()], counts["columns"])
    print(json.dumps({k: v for k, v in counts.items() if k != "columns"}, indent=1))
    print("validation:", report.summary())
    if recon.get("available"):
        for col, f in recon["features"].items():
            print(f"  reconcile {col:20s} max|d| {f['max_abs_diff']:.2e}  over tol {f['rows_over_tol']}  null {f['rows_null']}")
    if not report.ok:
        logger.error("store does not validate; nothing written")
        return 1
    if a.dry_run:
        return 0
    manifest_path = a.store_dir / schema.STORE_MANIFEST
    old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    keep = {k: v for k, v in old.items() if k not in ("schema_version", "built_at", "git_commit", "n_rows",
                                                      "rows_per_source", "columns")}
    rel_manifest = ext.dir / "manifest.json"
    keep["context"] = {**{k: v for k, v in counts.items() if k != "columns"},
                       "release_manifest_sha256": schema.file_sha256(rel_manifest) if rel_manifest.exists() else None,
                       "reconciliation_within_tolerance": recon.get("within_tolerance")}
    schema.write_store(out, a.store_dir, extra_manifest=keep)
    card = common.CARDS_DIR / f"context_{a.release.replace('/', '_')}.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(card_markdown(counts, recon, stats), encoding="utf-8")
    print(f"wrote {a.store_dir / schema.STORE_PARQUET} and {card}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
