"""QA rules, manifest writing, diffing, the refresh run end to end (with fake layer
groups), and ContextExtractor (brief E3 Part E)."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio

from pipelines.common.country_config import load_country
from pipelines.geodata import qa, refresh, release
from pipelines.geodata.core import load_catalog
from pipelines.geodata.extract import ContextExtractor, nearest_valid
from pipelines.geodata.grid import Grid

from .conftest import write_tif

YAML = """
schema: 1
defaults: {dtype: float32, nodata: -9999, kind: continuous, max_nodata_share: 0.2, required: false, manual: false}
settings: {pad_deg: 0.1}
sources:
  fake: {name: fake source, kind: local, path: none, version: "1", licence: CC BY 4.0, citation: Fake 2026}
layers:
  aez_belt: {group: aez, sources: [fake], source_name: fake belt, resampling: nearest, dtype: int16, nodata: 0,
             kind: categorical, classes: [1, 2], unit: code, update_cadence: static, required: true, legacy: true,
             max_nodata_share: 0.0}
  precip_annual: {group: other, sources: [fake], source_name: fake rain, resampling: bilinear, unit: mm/yr,
                  update_cadence: static, required: true, legacy: true, valid_min: 0, valid_max: 5000}
  soil_sand: {group: other, sources: [fake], source_name: fake sand, resampling: bilinear, unit: percent,
              update_cadence: occasional, valid_min: 0, valid_max: 100}
"""


def belt_array(shape):
    b = np.ones(shape, "int16")
    b[:, shape[1] // 2:] = 2
    b[0, 0] = 0
    return b


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """A fake catalogue (belt, rain, sand), a 6 x 8 grid and fake layer groups."""
    yml = tmp_path / "sources.yaml"
    yml.write_text(YAML, encoding="utf-8")
    cat = load_catalog(yml)
    grid = Grid(38.7, 9.05, 0.00225, 8, 6)
    state = {"rain": 800.0, "calls": []}

    class Aez:
        @staticmethod
        def build(ctx, wanted):
            state["calls"].append("aez")
            if not ctx.done("aez_belt"):
                ctx.emit("aez_belt", belt_array(grid.shape))

    class Other:
        @staticmethod
        def build(ctx, wanted):
            state["calls"].append("other")
            if "precip_annual" in wanted and not ctx.done("precip_annual"):
                ctx.emit("precip_annual", np.full(grid.shape, state["rain"], "float32"))
            if "soil_sand" in wanted and not ctx.done("soil_sand"):
                ctx.emit("soil_sand", np.full(grid.shape, 40.0, "float32"))

    monkeypatch.setattr(refresh, "load_catalog", lambda: cat)
    monkeypatch.setattr(refresh, "grid_for_country", lambda cfg: (grid, "test grid"))
    monkeypatch.setattr(refresh, "GROUPS", {"aez": Aez, "other": Other})
    monkeypatch.setenv("GEODATA_CACHE", str(tmp_path / "cache"))
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    write_tif(legacy / "aez_belt.tif", belt_array(grid.shape), grid, 0)
    write_tif(legacy / "precip_annual.tif", np.full(grid.shape, 800.0, "float32"), grid, -9999.0)
    return SimpleNamespace(cat=cat, grid=grid, state=state, root=tmp_path / "geodata", legacy=legacy)


def run(s, *extra):
    # --in-process: the fake groups are monkeypatched into this process; a worker process would not see them
    return refresh.main(["--country", "ET", "--geodata-root", str(s.root), "--legacy-dir", str(s.legacy),
                         "--in-process", *extra])


# ------------------------------------------------------------------ QA rules
def test_qa_rules_catch_range_nodata_classes_and_alignment(setup):
    s = setup
    spec = s.cat.layers["soil_sand"]
    prof = {"transform": s.grid.transform, "height": 6, "width": 8, "crs": "EPSG:4326", "dtype": "float32",
            "nodata": -9999.0}
    ok = qa.check_array(np.full(s.grid.shape, 40.0, "float32"), prof, spec, s.grid, None)
    assert ok["status"] == "warn"  # constant field: only a warning
    bad = np.full(s.grid.shape, 40.0, "float32")
    bad[0, 0] = 150
    bad[1, :] = -9999
    r = qa.check_array(bad, prof, spec, s.grid, None)
    checks = {c["check"]: c["status"] for c in r["checks"]}
    assert r["status"] == "fail" and checks["range"] == "fail" and checks["nodata_share"] == "pass"
    worse = bad.copy()
    worse[2:4, :] = -9999
    assert {c["check"]: c["status"] for c in qa.check_array(worse, prof, spec, s.grid, None)["checks"]}[
        "nodata_share"] == "fail"
    shifted = dict(prof, transform=Grid(38.8, 9.05, 0.00225, 8, 6).transform)
    ok_arr = np.arange(48, dtype="float32").reshape(6, 8)
    checks = qa.check_array(ok_arr, shifted, spec, s.grid, None)["checks"]
    assert {c["check"]: c["status"] for c in checks}["alignment"] == "fail"
    belt = s.cat.layers["aez_belt"]
    b = belt_array(s.grid.shape)
    b[3, 3] = 7
    r = qa.check_array(b, dict(prof, dtype="int16", nodata=0), belt, s.grid, b > 0)
    assert {c["check"]: c["status"] for c in r["checks"]}["classes"] == "fail"
    assert ok_arr.std() > 0


def test_compare_arrays_tolerance(setup):
    spec = setup.cat.layers["precip_annual"]
    a = np.full((3, 3), 100.0, "float32")
    b = a + 5e-4
    assert qa.compare_arrays(a, b, spec)["equal"]
    b[1, 1] += 1
    r = qa.compare_arrays(a, b, spec)
    assert not r["equal"] and r["cells_differing"] == 1 and r["max_abs_diff"] == pytest.approx(1.0005, rel=1e-4)


# ------------------------------------------------------------------ refresh end to end
def test_refresh_writes_a_complete_immutable_release(setup):
    s = setup
    assert run(s) == 0
    d = s.root / "ET" / "2026.1"
    for f in ("aez_belt.tif", "precip_annual.tif", "soil_sand.tif", "stack.vrt", "manifest.json", "qa_report.json",
              "README.md", "diff_vs_legacy.md"):
        assert (d / f).exists(), f
    assert not list(d.glob("*.layer.json")) and not (s.root / "ET" / ".2026.1.partial").exists()
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    assert m["release_id"] == "ET/2026.1" and m["sources_yaml_sha256"] == s.cat.sha256 and m["grid_hash"] == s.grid.hash()
    e = m["layers"]["precip_annual"]
    assert e["status"] == "built" and e["licence"] == "CC BY 4.0" and len(e["file_sha256"]) == 64
    assert e["legacy_equal"] is True and e["qa_status"] in ("pass", "warn")
    with rasterio.open(d / "soil_sand.tif") as src:
        assert src.profile["compress"].lower() == "lzw" and src.crs.to_epsg() == 4326
    with rasterio.open(d / "stack.vrt") as vrt:
        assert vrt.count == 3 and vrt.descriptions[1] == "precip_annual"
    assert "identical" in (d / "diff_vs_legacy.md").read_text(encoding="utf-8")
    with pytest.raises(release.ReleaseExists):
        run(s)  # immutable


def test_refresh_second_release_diff_and_layer_carry(setup):
    s = setup
    assert run(s) == 0
    s.state["rain"] = 900.0
    s.state["calls"].clear()
    assert run(s, "--release", "2026.2", "--layers", "precip_annual") == 0
    d2 = s.root / "ET" / "2026.2"
    m = json.loads((d2 / "manifest.json").read_text(encoding="utf-8"))
    assert m["previous_release"] == "2026.1" and m["layers"]["soil_sand"]["carried_from"] == "ET/2026.1"
    diff = (d2 / "diff_vs_2026.1.md").read_text(encoding="utf-8")
    assert "| `precip_annual` | changed | +100" in diff and "| `soil_sand` | identical |" in diff
    lc = json.loads((d2 / "qa_report.json").read_text(encoding="utf-8"))["legacy_comparison"]["precip_annual"]
    assert lc["equal"] is False and lc["cells_differing"] == 48  # differences are listed, not hidden
    assert release.list_releases("ET", s.root) == ["2026.1", "2026.2"]


def test_refresh_fails_on_required_layer_and_resumes(setup, monkeypatch):
    s = setup

    class Broken:
        @staticmethod
        def build(ctx, wanted):
            raise RuntimeError("source down")

    groups = dict(refresh.GROUPS)
    monkeypatch.setattr(refresh, "GROUPS", {"aez": groups["aez"], "other": Broken})
    assert run(s) == 1
    staging = s.root / "ET" / ".2026.1.partial"
    assert (staging / "aez_belt.tif").exists() and not (s.root / "ET" / "2026.1").exists()
    rep = json.loads((staging / "qa_report.json").read_text(encoding="utf-8"))
    assert "precip_annual" in rep["required_failed"]
    monkeypatch.setattr(refresh, "GROUPS", groups)
    s.state["calls"].clear()
    assert run(s) == 0  # resumes: the belt is reused from staging
    assert (s.root / "ET" / "2026.1" / "manifest.json").exists()


def test_dry_run_writes_nothing(setup, capsys):
    s = setup
    assert run(s, "--dry-run") == 0
    assert "PLAN ET/2026.1" in capsys.readouterr().out and not s.root.exists()


def test_release_id_rules(tmp_path):
    with pytest.raises(ValueError):
        release.check_new("ET", "v1", tmp_path)
    assert release.previous_release("ET", "2026.1", tmp_path) is None


# ------------------------------------------------------------------ extractor
def test_extractor_nearest_valid_fallback_and_batch(tmp_path, grid5, tif):
    a = np.arange(25, dtype="float32").reshape(5, 5)
    a[2, 2] = -9999
    p = tif("soil_clay.tif", a, grid5, -9999.0)
    tif("aez_belt.tif", np.full((5, 5), 3, "int16"), grid5, 0)
    ext = ContextExtractor(tmp_path, max_radius_px=2)
    lon, lat = 38.7 + 2.5 * 0.00225, 9.05 - 2.5 * 0.00225
    v = ext.at(lat, lon)
    assert v["soil_clay"] in (7.0, 11.0, 13.0, 17.0) and v["aez_belt"] == 3 and v["release_id"] is None
    with rasterio.open(p) as src:
        assert nearest_valid(src, lon, lat, -9999.0, 0) is None  # radius 0: the cell itself
    import pandas as pd

    df = pd.DataFrame({"lat": [lat, None, 9.0499], "lon": [lon, 38.7, 38.7001]})
    out = ext.batch(df)
    assert list(out.columns) == ["ctx_aez_belt", "ctx_soil_clay"]
    assert out["ctx_soil_clay"].isna().tolist() == [False, True, False] and out["ctx_soil_clay"][2] == 0.0


def test_legacy_context_equals_recommend_extract_context(tmp_path, grid5, monkeypatch):
    """The backend adapter returns exactly what the canonical engine computes from the same rasters."""
    from pipelines.geodata.core import REPO_ROOT

    rng = np.random.default_rng(3)
    names = ["precip_annual", "temp_mean_annual", "precip_seasonality", "elevation", "slope", "soil_clay",
             "lgp_days", "soil_ph", "soil_soc"]
    for n in names:
        a = rng.uniform(1, 500, (5, 5)).astype("float32")
        a[2, 2] = -9999
        write_tif(tmp_path / f"{n}.tif", a, grid5, -9999.0)
    write_tif(tmp_path / "land_cover.tif", np.full((5, 5), 40, "uint8"), grid5, 0)
    belt = np.full((5, 5), 7, "int16")
    belt[2, 2] = 0
    write_tif(tmp_path / "aez_belt.tif", belt, grid5, 0)
    backend = REPO_ROOT / "app" / "backend"
    monkeypatch.syspath_prepend(str(backend))
    if not (backend / "aez_belt_lookup.csv").exists():
        pytest.skip("backend lookup missing")
    engine = importlib.import_module("recommend")
    monkeypatch.setattr(engine, "LAYER_DIR", str(tmp_path))
    from pipelines.geodata.extract import load_aez_lookup

    monkeypatch.setattr(engine, "_load", lambda: (None, None, load_aez_lookup(backend / "aez_belt_lookup.csv")))
    ext = ContextExtractor(tmp_path, max_radius_px=120, aez_lookup=load_aez_lookup(backend / "aez_belt_lookup.csv"))
    for lat, lon in [(9.05 - 2.5 * 0.00225, 38.7 + 2.5 * 0.00225), (9.049, 38.701)]:
        expected = engine.extract_context(lat, lon)
        got = ext.legacy_context(lat, lon, with_extended=False)
        assert got == expected
    full = ext.legacy_context(9.049, 38.701)
    assert full["release"] is None and full["extended"] == {}
    sys.modules.pop("recommend", None)
