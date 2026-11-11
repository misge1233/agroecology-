"""Fixtures of the geodata tests: tiny synthetic grids and rasters (5 x 5 and up)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio

from pipelines.geodata.grid import Grid


def write_tif(path: Path, arr: np.ndarray, grid: Grid, nodata, dtype: str | None = None) -> Path:
    prof = grid.profile(dtype or arr.dtype.name, nodata)
    prof.update(tiled=False)
    prof.pop("blockxsize"), prof.pop("blockysize")
    with rasterio.open(path, "w", **prof) as d:
        d.write(arr.astype(prof["dtype"]), 1)
    return path


@pytest.fixture
def grid5() -> Grid:
    """5 x 5 cells of 0.00225 degrees near Addis Ababa."""
    return Grid(xmin=38.7, ymax=9.05, res=0.00225, ncols=5, nrows=5)


@pytest.fixture
def tif(tmp_path):
    def make(name: str, arr: np.ndarray, grid: Grid, nodata, dtype: str | None = None) -> Path:
        return write_tif(tmp_path / name, arr, grid, nodata, dtype)
    return make
