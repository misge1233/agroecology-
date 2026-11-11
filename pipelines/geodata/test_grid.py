"""Grid construction (brief E3 Part E)."""
from __future__ import annotations

import json

import pytest

from pipelines.common.country_config import load_country
from pipelines.geodata.core import REPO_ROOT
from pipelines.geodata.grid import Grid, grid_for_country, grid_from_bbox, grid_from_definition


def test_bbox_rule_reproduces_the_ethiopian_grid_definition():
    d = json.loads((REPO_ROOT / "data" / "lookups" / "grid_definition.json").read_text(encoding="utf-8"))
    g = grid_from_bbox(32.9, 48.2, 3.3, 14.9)
    assert (g.ncols, g.nrows) == (d["ncols"], d["nrows"]) == (6800, 5156)
    assert g.xmin == d["xmin"] and abs(g.ymax - d["ymax"]) < 1e-9
    assert g.hash() == grid_from_definition(REPO_ROOT / "data" / "lookups" / "grid_definition.json").hash()


def test_country_grids_et_from_file_ke_from_bbox():
    et, how = grid_for_country(load_country("ET", check_files=False))
    assert "grid definition" in how and et.shape == (5156, 6800)
    ke, how = grid_for_country(load_country("KE", check_files=False))
    assert "bbox" in how and ke.res == 0.00225 and ke.xmin == 33.9
    assert ke.ymin == pytest.approx(-4.7) and ke.ymax >= 5.0 and ke.xmax >= 41.9


def test_transform_bounds_and_row_latitudes(grid5):
    t = grid5.transform
    assert (t.a, t.e, t.c, t.f) == (0.00225, -0.00225, 38.7, 9.05)
    l, b, r, top = grid5.bounds
    assert r == pytest.approx(38.71125) and b == pytest.approx(9.03875)
    assert grid5.row_lats()[0] == pytest.approx(9.05 - 0.001125)
    assert grid5.matches(t, (5, 5), "EPSG:4326")
    assert not grid5.matches(t, (5, 6), "EPSG:4326")


def test_aligned_grid_snaps_to_tile_seams_and_covers_the_grid():
    g = grid_from_bbox(32.9, 48.2, 3.3, 14.9)
    f = g.aligned(1 / 1200)
    assert round(f.xmin * 1200, 6).is_integer() and round(f.ymax * 1200, 6).is_integer()
    assert f.xmin <= g.xmin and f.ymax >= g.ymax and f.xmax >= g.xmax and f.ymin <= g.ymin
    assert (f.ncols, f.nrows) == (18360, 13922)


def test_window_of_clips_to_the_grid(grid5):
    assert grid5.window_of((38.0, 8.0, 38.1, 8.1)) is None
    r0, c0, r1, c1 = grid5.window_of((38.70226, 9.04, 38.705, 9.0475), pad_cells=0)
    assert (r0, c0) == (1, 1) and r1 <= 5 and c1 <= 5
    full = Grid(0, 1, 0.5, 2, 2)
    assert full.window_of((-10, -10, 10, 10)) == (0, 0, 2, 2)
