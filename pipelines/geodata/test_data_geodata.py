"""Data tests of brief E3 (``@pytest.mark.data``; skipped when the inputs are absent).

Run now, against the current stack (``geodata/layers``):

* the belt rasterized from the shapefile by the legacy rule equals ``aez_belt.tif``;
* ``slope_percent`` of the legacy elevation equals ``slope.tif``;
* the frozen training features of all 8,664 rows (7,250 ERA) re-read through
  ``ContextExtractor`` equal the dataset within 1e-3;
* ``extract_features.py --clean`` returns the legacy values for the demo points.

Run once ``geodata/ET/2026.1`` exists: the 11 legacy layers equal the current stack
(elevation and slope within the statistical tolerance the reviewer accepted on 11 Nov 2026,
``legacy_tolerance`` in ``sources.yaml``, ``docs/decisions/geodata_v2.md``: the GLO-30 tiles
were re-issued after the legacy stack was built); ``extract_features.py --clean`` on the demo
points is identical from the release (elevation and slope within that tolerance); the legacy
feature reconciliation from the release; the store's ``ctx_*`` columns validate.
"""
from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from pipelines.geodata.core import LEGACY_LAYERS_DIR, REPO_ROOT, load_catalog, read_band
from pipelines.geodata.extract import LEGACY_RADIUS, TRAINING_CONTEXT, ContextExtractor

pytestmark = pytest.mark.data

LEGACY = LEGACY_LAYERS_DIR
RELEASE = REPO_ROOT / "geodata" / "ET" / "2026.1"
DATASET = REPO_ROOT / "data" / "processed" / "CSA_ERA_final_model_ready.csv"
DEMO = REPO_ROOT / "data" / "lookups" / "demo_points.csv"
SHP = REPO_ROOT / "geodata" / "sources" / "agroecology_belt" / "agroecology.shp"
CLI = REPO_ROOT / "pipelines" / "features" / "extract_features.py"
need_legacy = pytest.mark.skipif(not (LEGACY / "aez_belt.tif").exists(), reason="legacy stack absent")
need_release = pytest.mark.skipif(not (RELEASE / "manifest.json").exists(), reason="release ET/2026.1 not built")


@need_legacy
@pytest.mark.skipif(not SHP.exists(), reason="belt shapefile absent")
def test_belt_from_shapefile_equals_legacy_raster():
    from pipelines.geodata.grid import grid_from_raster
    from pipelines.geodata.layers.aez import rasterize_belt

    g = grid_from_raster(LEGACY / "aez_belt.tif")
    legacy = read_band(LEGACY / "aez_belt.tif")[0]
    assert np.array_equal(rasterize_belt(str(SHP), g, holes=False), legacy)
    holes = rasterize_belt(str(SHP), g, holes=True)
    assert np.array_equal(holes > 0, legacy > 0) and int((holes != legacy).sum()) == 93_119


@need_legacy
def test_slope_from_legacy_elevation_equals_legacy_slope():
    from pipelines.geodata.layers.terrain import slope_percent

    elev, prof = read_band(LEGACY / "elevation.tif")
    np.testing.assert_allclose(slope_percent(elev, prof["transform"]), read_band(LEGACY / "slope.tif")[0], atol=1e-4)


def _tolerance_layers(cat) -> dict[str, dict]:
    """Legacy layers accepted under a statistical tolerance instead of equality.

    ``legacy_tolerance: {median_abs, p99_abs}`` in ``sources.yaml`` (elevation and slope,
    reviewer 11 Nov 2026); every other legacy layer must be equal (floats within 1e-3).
    """
    out = {}
    for lid in cat.legacy_ids():
        raw = cat.layers[lid].raw
        if isinstance(raw, dict) and raw.get("legacy_tolerance"):
            out[lid] = dict(raw["legacy_tolerance"])
    return out


def _reconcile(layer_dir):
    """The frozen dataset, the max abs difference per training column, and the abs differences."""
    d = pd.read_csv(DATASET)
    ext = ContextExtractor(layer_dir, max_radius_px=LEGACY_RADIUS)
    ctx = ext.batch(d, "latitude", "longitude", layers=sorted(set(TRAINING_CONTEXT.values())))
    out, diffs = {}, {}
    for col, lid in TRAINING_CONTEXT.items():
        new = ctx[f"ctx_{lid}"]
        if col == "aez_belt":
            new = new.map(lambda v: ext.aez_lookup.get(int(v)))
            out[col] = int((new != d[col]).sum())
        else:
            diffs[col] = (new - d[col]).abs()
            out[col] = float(diffs[col].max())
    return d, out, diffs


@need_legacy
@pytest.mark.skipif(not DATASET.exists(), reason="frozen dataset absent")
def test_frozen_training_features_reproduce_from_the_legacy_stack():
    d, out, _ = _reconcile(LEGACY)
    assert (d["source"] == "ERA").sum() == 7250
    assert out.pop("aez_belt") == 0
    assert max(out.values()) <= 1e-3, out


@need_legacy
@pytest.mark.skipif(not DEMO.exists(), reason="demo points absent")
def test_extract_features_clean_on_demo_points(tmp_path):
    out = tmp_path / "demo.csv"
    subprocess.run([sys.executable, str(CLI), "--csv", str(DEMO), "--clean", "--layers", str(LEGACY), "--out",
                    str(out)], check=True, capture_output=True)
    df = pd.read_csv(out)
    assert list(df.columns)[3:] == ["aez_name", "precip_annual", "temp_mean_annual", "precip_seasonality", "lgp_days",
                                    "elevation", "slope", "soil_clay", "soil_ph", "soil_soc", "land_cover"]
    addis = df.iloc[0]
    assert addis["aez_name"] == "Moist Dega" and addis["land_cover"] == "Built-up"
    assert addis["precip_annual"] == pytest.approx(1143.3060302734375)


# ------------------------------------------------------------------ after the release
@need_release
@need_legacy
def test_release_legacy_layers_equal_the_current_stack():
    from pipelines.geodata import qa

    cat = load_catalog()
    tol = _tolerance_layers(cat)
    mask = read_band(LEGACY / "aez_belt.tif")[0] > 0
    res = qa.compare_legacy(RELEASE, LEGACY, cat, mask)
    assert set(res) == set(cat.legacy_ids())
    strict = {k: v for k, v in res.items() if k not in tol}
    assert all(r["equal"] for r in strict.values()), {k: v for k, v in strict.items() if not v["equal"]}
    for lid in tol:  # elevation, slope: median and p99 |diff| over the mask, no cell lost
        r = res[lid]
        assert r["accepted"] and r["within_tolerance"] and all(r["tolerance_checks"].values()), (lid, r)
        assert r["newly_nodata"] == 0, (lid, r)


@need_release
@need_legacy
def test_extract_features_identical_from_release(tmp_path):
    a, b = tmp_path / "legacy.csv", tmp_path / "release.csv"
    for src, out in ((["--layers", str(LEGACY)], a), (["--release", "ET/2026.1"], b)):
        subprocess.run([sys.executable, str(CLI), "--csv", str(DEMO), "--clean", *src, "--out", str(out)], check=True,
                       capture_output=True)
    a_df, b_df = pd.read_csv(a), pd.read_csv(b)
    tol = _tolerance_layers(load_catalog())
    loose = [c for c in a_df.columns if c in tol]  # elevation, slope
    pd.testing.assert_frame_equal(a_df.drop(columns=loose), b_df.drop(columns=loose), atol=1e-3)
    for c in loose:  # per point: within the layer's p99 bound (observed: 0.5 m, 0.15 %)
        assert (a_df[c] - b_df[c]).abs().max() <= tol[c]["p99_abs"], (c, a_df[c].tolist(), b_df[c].tolist())


@need_release
def test_release_manifest_complete_and_required_new_layers_present():
    m = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
    assert m["qa_status"] in ("pass", "warn")
    for lid, e in m["layers"].items():
        assert e.get("source_name") and e.get("licence") is not None or e["status"] != "built", lid
        if e["status"] == "built":
            assert len(e["file_sha256"]) == 64 and (RELEASE / e["file"]).exists()
    required_new = ["slope_length_factor", "tpi", "twi", "flow_accumulation", "dist_to_stream_m", "soil_sand",
                    "soil_bulk_density", "soil_awc", "soil_cec", "rain_mean_1991_2020", "rain_cv_interannual",
                    "dry_season_length_months", "aridity_index", "cropland_fraction_1km",
                    "travel_time_to_city_min", "koppen_class"]
    missing = [l for l in required_new if m["layers"].get(l, {}).get("status") != "built"]
    assert not missing, missing


@need_release
@pytest.mark.skipif(not DATASET.exists(), reason="frozen dataset absent")
def test_legacy_feature_reconciliation_from_the_release():
    _, out, diffs = _reconcile(RELEASE)
    tol = _tolerance_layers(load_catalog())
    assert out.pop("aez_belt") == 0
    six = ("Rainfall", "Altitude_r", "temp_mean_annual", "precip_seasonality", "slope", "soil_clay")
    strict = {k: out[k] for k in six if TRAINING_CONTEXT[k] not in tol}
    assert max(strict.values()) <= 1e-3, strict
    for col in six:  # Altitude_r (elevation) and slope: the accepted statistical tolerance, per row
        lid = TRAINING_CONTEXT[col]
        if lid in tol:
            d = diffs[col]
            assert d.median() <= tol[lid]["median_abs"] and d.quantile(0.99) <= tol[lid]["p99_abs"], (col, d.describe())


@need_release
def test_store_context_validates():
    from pipelines.evidence import common, schema
    from pipelines.taxonomy import taxonomy_io as tio

    df = schema.read_store(common.EVIDENCE_DIR)
    if "ctx_precip_annual" not in df.columns:
        pytest.skip("add_context.py not run yet")
    assert schema.validate(df, outcome_directions=tio.Taxonomy.load().outcome_directions()).ok
    assert (df["ctx_release"].dropna() == "ET/2026.1").all()
