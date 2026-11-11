"""add_context eligibility and the ctx_* range checks of schema.validate (brief E3 C3)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import rasterio

from pipelines.evidence import add_context, schema
from pipelines.geodata.extract import ContextExtractor
from pipelines.geodata.grid import Grid

GRID = Grid(38.7, 9.05, 0.00225, 5, 5)
RANGES = {"soil_sand": {"kind": "continuous", "valid_min": 0, "valid_max": 100},
          "aez_belt": {"kind": "categorical", "classes": [1, 2]}}


def _tif(path, arr, nodata):
    prof = dict(driver="GTiff", height=5, width=5, count=1, dtype=arr.dtype.name, crs="EPSG:4326",
                transform=GRID.transform, nodata=nodata)
    with rasterio.open(path, "w", **prof) as d:
        d.write(arr, 1)


def make_release(tmp_path):
    belt = np.ones((5, 5), "int16")
    belt[:, 4] = 0  # last column outside the country
    _tif(tmp_path / "aez_belt.tif", belt, 0)
    _tif(tmp_path / "soil_sand.tif", np.full((5, 5), 40.0, "float32"), -9999.0)
    manifest = {"release_id": "ET/test.1", "layers": {
        "aez_belt": {"status": "built", "file": "aez_belt.tif", "kind": "categorical"},
        "soil_sand": {"status": "built", "file": "soil_sand.tif", "kind": "continuous"}}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return ContextExtractor(tmp_path, max_radius_px=120)


def cell(r, c):
    return 9.05 - (r + 0.5) * 0.00225, 38.7 + (c + 0.5) * 0.00225


def test_add_context_eligibility_mask_and_release(tmp_path):
    ext = make_release(tmp_path)
    pts = [cell(1, 1), cell(1, 4), cell(2, 2), cell(2, 2), (None, None)]
    df = pd.DataFrame({
        "lat": [p[0] for p in pts], "lon": [p[1] for p in pts],
        "loc_precision": ["site", "district", "site", "country", "site"],
        "loc_method": ["reported", "geocoded_llm_checked", "geocoded_llm_unchecked", "none", "reported"],
        "source": ["ERA", "HAB", "HAB", "CSA", "ERA"],
        "ctx_reported_rain_mm": [600.0, None, None, None, None],
        "ctx_old_layer": [1.0] * 5,
    })
    out, counts = add_context.add_context(df, ext)
    assert "ctx_old_layer" not in out.columns and "ctx_reported_rain_mm" in out.columns
    assert counts["eligible"] == 2 and counts["written"] == 1 and counts["outside_country_mask"] == 1
    assert counts["not_eligible"] == {"precision_country_or_none": 1, "geocoded_llm_unchecked": 1, "no_coordinates": 1}
    assert out["ctx_soil_sand"].tolist()[0] == 40.0 and out["ctx_soil_sand"].isna().tolist()[1:] == [True] * 4
    assert out["ctx_release"].iloc[0] == "ET/test.1" and out["ctx_release"].iloc[1:].isna().all()


def test_ctx_range_checks():
    df = pd.DataFrame({"ctx_soil_sand": [10.0, 120.0, None], "ctx_aez_belt": [1.0, 3.0, 2.0],
                       "ctx_reported_slope_pct": [5.0, 400.0, None], "ctx_mystery": [1.0, None, None],
                       "ctx_release": ["ET/2026.1", None, None]})
    rep = schema.ValidationReport(n_rows=3)
    schema.validate_ctx(df, rep, RANGES)
    assert rep.errors["ctx_range:ctx_soil_sand"] == 1 and rep.errors["ctx_class:ctx_aez_belt"] == 1
    assert rep.errors["ctx_unknown_layer"] == 1
    assert not any("reported" in k for k in rep.errors)  # reported values: numeric only
    bad = pd.DataFrame({"ctx_soil_sand": ["forty"]})
    rep2 = schema.ValidationReport(n_rows=1)
    schema.validate_ctx(bad, rep2, RANGES)
    assert rep2.errors["dtype:ctx_soil_sand"] == 1


def test_ctx_ranges_come_from_sources_yaml():
    r = schema.ctx_layer_ranges()
    assert r["soil_clay"]["valid_max"] == 100 and r["land_cover"]["kind"] == "categorical"
    assert 40 in r["land_cover"]["classes"] and r["aridity_index"]["valid_min"] == 0
