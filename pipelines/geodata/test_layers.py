"""Layer computations on tiny synthetic rasters (brief E3 Part E): warping, the moved
WorldClim logic, terrain (slope, S, LS, TPI, TWI, distance, D8), pedotransfer, CHIRPS
statistics, cropland counting."""
from __future__ import annotations

import math

import numpy as np
import pytest
from rasterio.enums import Resampling
from rasterio.transform import from_origin

from pipelines.geodata.core import clip_to_bounds
from pipelines.geodata.grid import Grid
from pipelines.geodata.layers import climate_chirps as ch
from pipelines.geodata.layers import climate_worldclim as wc
from pipelines.geodata.layers import landcover as lc
from pipelines.geodata.layers import soil
from pipelines.geodata.layers import terrain as tr

ND = -9999.0


# ------------------------------------------------------------------ warping
def test_to_grid_identity_and_clip_equivalence(tmp_path, tif):
    src_grid = Grid(38.0, 10.0, 0.01, 60, 60)
    rng = np.random.default_rng(1)
    a = rng.uniform(0, 100, src_grid.shape).astype("float32")
    a[5, 5] = -3.4e38
    src = tif("src.tif", a, src_grid, -3.4e38)
    target = Grid(38.2, 9.8, 0.00225, 40, 40)
    full = wc.align_stack([src], target)[0]
    clip = clip_to_bounds(str(src), target.padded_bounds(0.05), tmp_path / "clip.tif")
    clipped = wc.align_stack([clip], target)[0]
    np.testing.assert_allclose(full, clipped, atol=1e-5)  # clipping first changes nothing
    same = wc.to_grid(a.copy(), src_grid.transform, "EPSG:4326", src_grid, src_nodata=float(np.float32(-3.4e38)))
    inner = (slice(1, -1), slice(1, -1))
    ok = a[inner] > -1e30
    np.testing.assert_allclose(same[inner][ok], a[inner][ok], atol=1e-4)


def test_sum_and_mean_months_treat_nodata_as_nan(tmp_path, grid5, tif):
    files = []
    for m in range(12):
        arr = np.full(grid5.shape, float(m + 1), "float32")
        arr[0, 0] = -1.0
        files.append(tif(f"m{m}.tif", arr, grid5, -1.0))
    total, _, _ = wc.sum_months(files)
    mean, _, _ = wc.mean_months(files)
    assert total[2, 2] == 78 and np.isnan(total[0, 0])
    assert mean[2, 2] == pytest.approx(6.5) and np.isnan(mean[0, 0])


def test_seasonality_cv_and_lgp():
    aligned = np.stack([np.full((2, 2), v, "float32") for v in (10, 30) * 6])
    cv = wc.seasonality_cv(aligned)
    assert cv[0, 0] == pytest.approx(50.0)  # population SD 10 / mean 20
    precip = np.full((12, 1, 2), 200.0, "float32")
    tavg = np.full((12, 1, 2), 20.0, "float32")
    tavg[:, 0, 1] = 3.0  # too cold: no growing month
    lgp = wc.compute_lgp(precip, tavg, np.array([9.0]))
    assert lgp[0, 0] == 365 and lgp[0, 1] == 0


def test_extraterrestrial_radiation_and_hargreaves():
    ra = wc.extraterrestrial_radiation(np.array([0.0, 9.0, -9.0]))
    assert ra.shape == (12, 3)
    assert 33 < ra[:, 0].min() and ra[:, 0].max() < 39  # FAO-56 Annex 2: 35-38 MJ m-2 d-1 at the equator
    assert ra[5, 1] > ra[5, 2]  # June: north is sunnier
    pet = wc.hargreaves_month(np.array([[20.0]]), np.array([[12.0]]), np.array([36.0]), 30.0)
    assert pet[0, 0] == pytest.approx(0.0023 * 0.408 * 36 * 37.8 * math.sqrt(12) * 30, rel=1e-5)


# ------------------------------------------------------------------ terrain
def plane(rows: int, cols: int, res: float, lat0: float, grade: float) -> tuple[np.ndarray, object]:
    """z falls southwards with tan(slope) = grade."""
    t = from_origin(38.0, lat0, res, res)
    dy = res * tr.M_PER_DEG
    z = (grade * dy * (rows - np.arange(rows)))[:, None].repeat(cols, 1).astype("float32")
    return z, t


def test_slopes_on_an_inclined_plane():
    z, t = plane(20, 20, 1 / 3600, 9.0, 0.09)
    tanb = tr.tan_slope(z, t)
    assert np.allclose(tanb, 0.09, atol=1e-4)
    assert np.allclose(tr.slope_percent(z, t), 9.0, atol=1e-2)
    assert np.allclose(tr.s_factor(tanb), 1.0, atol=0.01)  # 9% is the RUSLE unit-plot slope


def test_ls_twi_and_sca():
    sca = np.array([[22.13, 1000.0]], "float32")
    s = np.array([[1.0, 2.0]], "float32")
    ls = tr.ls_factor(sca, s, max_sca=300)
    assert ls[0, 0] == pytest.approx(1.0) and ls[0, 1] == pytest.approx((300 / 22.13) ** 0.4 * 2, rel=1e-5)
    t = tr.twi(np.array([[100.0, 100.0]]), np.array([[0.1, 0.0]]))
    assert t[0, 0] == pytest.approx(math.log(1000)) and t[0, 1] == pytest.approx(math.log(1e5))
    g = Grid(38.0, 9.0, 1 / 1200, 2, 2)
    a = tr.specific_catchment_area(np.ones((2, 2), "float32"), g)
    dx, _, dy = tr.cell_geometry(g)
    assert a[0, 0] == pytest.approx(1e6 / math.sqrt(dx[0] * dy), rel=1e-5)


def test_tpi_peak_positive_and_flat_zero():
    z = np.zeros((11, 11), "float32")
    z[5, 5] = 100
    t = tr.tpi(z, 3)
    assert t[5, 5] == pytest.approx(100 - 100 / 9, rel=1e-5) and t[5, 7] == pytest.approx(0)
    z[0, 0] = np.nan
    assert np.isnan(tr.tpi(z, 3)[0, 0])
    assert tr.window_cells(1000, Grid(0, 0, 1 / 1200, 1, 1)) == 11


def test_distance_to_streams():
    g = Grid(38.0, 0.001, 1 / 1200, 5, 5)
    streams = np.zeros((5, 5), bool)
    streams[:, 0] = True
    valid = np.ones((5, 5), bool)
    valid[4, 4] = False
    d = tr.distance_to_streams(streams, g, valid)
    dx = g.res * tr.M_PER_DEG * math.cos(math.radians(0.5 * (g.ymin + g.ymax)))
    assert d[2, 0] == 0 and d[2, 3] == pytest.approx(3 * dx, rel=1e-4) and np.isnan(d[4, 4])


@pytest.mark.skipif(tr.whitebox_exe() is None, reason="WhiteboxTools binary not installed (never downloaded by tests)")
def test_d8_upstream_area_and_streams_on_a_plane(tmp_path):
    g = Grid(38.0, 9.0, 1 / 1200, 6, 8)
    z, _ = plane(8, 6, g.res, 9.0, 0.05)
    z += np.linspace(0, 0.01, 6)[None, :].astype("float32")  # break ties
    acc = tr.d8_upstream_area(z, g)
    _, area, _ = tr.cell_geometry(g)
    assert np.nanmin(acc) > 0
    assert np.nanmax(acc) >= 7 * area.mean()  # a column drains to the bottom row
    assert np.nansum(acc[0]) == pytest.approx(area[0] * 6, rel=0.2)  # the top row only holds itself
    streams = tr.extract_streams(acc, g, threshold_km2=float(4 * area.mean()), workdir=tmp_path)
    assert streams.dtype == bool and streams[-1].any() and not streams[0].any()
    rec = tr.whitebox_tool_record()
    assert rec["name"] == "WhiteboxTools" and rec["python_package"].startswith("whitebox ")


def test_whitebox_missing_degrades_to_layer_unavailable(monkeypatch, tmp_path):
    from pipelines.geodata.core import LayerUnavailable

    monkeypatch.setattr(tr, "whitebox_exe", lambda: None)
    with pytest.raises(LayerUnavailable, match="WhiteboxTools"):
        tr.whitebox_tools(allow_download=False)


# ------------------------------------------------------------------ soil
def test_depth_weighted_mean_and_missing():
    a, b, c = (np.array([[10.0, ND]], "float32"), np.array([[20.0, 5.0]], "float32"), np.array([[30.0, 5.0]], "float32"))
    out = soil.depth_weighted([a, b, c], [5, 10, 15])
    assert out[0, 0] == pytest.approx((50 + 200 + 450) / 30) and out[0, 1] == ND


def test_saxton_rawls_awc_is_plausible_by_texture():
    awc = soil.saxton_rawls_awc(np.array([92.0, 40.0, 20.0, 10.0]), np.array([3.0, 20.0, 30.0, 50.0]),
                                np.array([2.5, 2.5, 2.5, 2.5]), np.array([1.6, 1.4, 1.35, 1.25]))
    sand, loam, clay_loam, clay = awc
    assert 30 < sand < 90 and 110 < loam < 180 and 110 < clay_loam < 200 and 90 < clay < 200
    assert sand < loam  # coarse soils hold less plant-available water
    dense = soil.saxton_rawls_awc(np.array([40.0]), np.array([20.0]), np.array([2.5]), np.array([1.8]))
    assert dense[0] < loam  # compaction lowers field capacity
    lay = soil.awc_layer(np.array([[40.0, ND]]), np.array([[20.0, 20.0]]), np.array([[14.5, 14.5]]),
                         np.array([[1.4, 1.4]]))
    assert lay[0, 1] == ND and 110 < lay[0, 0] < 180


# ------------------------------------------------------------------ CHIRPS
def test_chirps_climatology_dry_months_and_aridity():
    annual = np.array([[[800.0]], [[1000.0]], [[1200.0]]], "float32")
    monthly = np.array([[[v]] for v in [0, 0, 30, 60, 90, 300, 600, 600, 300, 60, 30, 0]], "float32") * 3
    st = ch.climatology(annual, monthly, 3)
    assert st["mean"][0, 0] == pytest.approx(1000) and st["cv"][0, 0] == pytest.approx(20.0, rel=1e-5)
    assert ch.dry_months(st["monthly_mean"], 50)[0, 0] == 5
    nanm = st["monthly_mean"].copy()
    nanm[3] = np.nan
    assert ch.dry_months(nanm, 50)[0, 0] == ND
    ai = ch.aridity(np.array([[600.0, ND, 600.0]], "float32"), np.array([[1200.0, 1200.0, 0.0]], "float32"))
    assert ai[0, 0] == pytest.approx(0.5) and ai[0, 1] == ND and ai[0, 2] == ND


def test_chirps_file_names():
    names = ch.file_names((1991, 2020))
    assert len(names) == 360 and names[0][2] == "chirps-v2.0.1991.01.tif.gz" and names[-1][:2] == (2020, 12)


# ------------------------------------------------------------------ cropland share
def test_cropland_counts_per_cell_and_box():
    g = Grid(0.0, 0.0, 27 / 12000, 2, 2)  # 27 x 27 WorldCover pixels per cell
    res = 1 / 12000
    a = np.full((54, 54), 30, "uint8")
    a[:27, :27] = 40           # top-left cell all cropland
    a[27:, 27:40] = 40         # bottom-right: 13 of 27 columns
    a[27:, :27] = 0            # bottom-left: no data
    crop, valid = np.zeros(g.shape, "int32"), np.zeros(g.shape, "int32")
    lc.count_into(g, a[:30], from_origin(0, 0, res, res), 40, crop, valid)  # two strips
    lc.count_into(g, a[30:], from_origin(0, -30 * res, res, res), 40, crop, valid)
    assert crop.tolist() == [[729, 0], [0, 13 * 27]] and valid.tolist() == [[729, 729], [0, 729]]
    w = lc.box_weights(1000, Grid(0, 0, 0.00225, 1, 1))
    assert w.tolist() == [0.5, 1, 1, 1, 0.5]
    f = lc.box_fraction(crop, valid, np.ones(1))
    assert f[0, 0] == 1 and f[1, 0] == -9999 and f[1, 1] == pytest.approx(13 / 27)
    assert lc.tile_name(3, 30) == "ESA_WorldCover_10m_2021_v200_N03E030_Map"
    assert tr.tile_name(-5, 33) == "Copernicus_DSM_COG_10_S05_00_E033_00_DEM"
    _ = Resampling
