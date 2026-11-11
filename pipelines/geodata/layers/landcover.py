"""Land-cover layers from ESA WorldCover 2021 (brief E3 B1 and B5).

* ``land_cover`` (legacy, moved from ``pipelines/features/get_landcover.py``): every
  3x3 degree tile warped onto the grid with mode resampling and composited;
* ``cropland_fraction_1km`` (new): the share of 10 m cropland pixels (class 40) among
  valid pixels in a 1 km box centred on each cell. Each 10 m pixel is counted in the
  grid cell that contains its centre (27 x 27 pixels per cell on the Ethiopian grid),
  then a separable box of 1 km (weights 0.5, 1, 1, 1, 0.5 cells for 4 cells per km)
  sums the counts.
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window

from ..core import BuildContext
from ..grid import Grid

logger = logging.getLogger("geodata.landcover")

GROUP = "landcover"
LAYERS = ("land_cover", "cropland_fraction_1km")
SOURCE = "worldcover_2021"
ND = 0
S3 = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
M_PER_DEG = 111320.0


# ------------------------------------------------------------ moved logic (get_landcover.py)
def tile_name(lat: int, lon: int) -> str:
    """WorldCover tile name of the 3-degree cell with lower-left corner (lat, lon)."""
    ns = "N%02d" % lat if lat >= 0 else "S%02d" % (-lat)
    ew = "E%03d" % lon if lon >= 0 else "W%03d" % (-lon)
    return "ESA_WorldCover_10m_2021_v200_%s%s_Map" % (ns, ew)


def tiles_for(grid: Grid) -> list[tuple[int, int]]:
    """Candidate 3-degree tiles in the order get_landcover.py visits them."""
    l, b, r, t = grid.bounds
    lat0, lat1 = int(math.floor(b / 3) * 3), int(math.floor(t / 3) * 3)
    lon0, lon1 = int(math.floor(l / 3) * 3), int(math.floor(r / 3) * 3)
    return [(la, lo) for la in range(lat0, lat1 + 1, 3) for lo in range(lon0, lon1 + 1, 3)]


def mode_tile(path: str, grid: Grid) -> np.ndarray:
    """One tile read through a WarpedVRT with mode resampling onto the grid (get_landcover.py)."""
    with rasterio.open(path) as src:
        with WarpedVRT(src, crs=grid.crs, transform=grid.transform, width=grid.ncols, height=grid.nrows,
                       resampling=Resampling.mode) as vrt:
            return vrt.read(1)


# ------------------------------------------------------------ new: cropland share
def count_into(grid: Grid, a: np.ndarray, transform: Any, target_class: int,
               crop_n: np.ndarray, valid_n: np.ndarray) -> None:
    """Add the class and valid pixel counts of ``a`` (one window) to the grid count arrays."""
    h, w = a.shape
    xc = transform.c + (np.arange(w) + 0.5) * transform.a
    yc = transform.f + (np.arange(h) + 0.5) * transform.e
    gc = np.floor((xc - grid.xmin) / grid.res).astype(np.int64)
    gr = np.floor((grid.ymax - yc) / grid.res).astype(np.int64)
    rs = np.r_[0, np.flatnonzero(np.diff(gr)) + 1]
    cs = np.r_[0, np.flatnonzero(np.diff(gc)) + 1]
    rows, cols = gr[rs], gc[cs]
    rk = (rows >= 0) & (rows < grid.nrows)
    ck = (cols >= 0) & (cols < grid.ncols)
    if not rk.any() or not ck.any():
        return
    for mask, out in (((a == target_class), crop_n), ((a > 0), valid_n)):
        s = np.add.reduceat(mask.view(np.uint8), rs, axis=0, dtype=np.uint16)
        s = np.add.reduceat(s, cs, axis=1, dtype=np.uint32)
        out[np.ix_(rows[rk], cols[ck])] += s[np.ix_(rk, ck)].astype(out.dtype)


def box_weights(window_m: float, grid: Grid) -> np.ndarray:
    """Per-axis weights of a box ``window_m`` wide centred on a cell (half weights at the ends)."""
    n = max(1, int(round(window_m / (grid.res * M_PER_DEG))))
    if n % 2 == 1:
        return np.ones(n, dtype="float64")
    return np.r_[0.5, np.ones(n - 1), 0.5]


def box_fraction(crop_n: np.ndarray, valid_n: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted box sum of the class counts over the weighted box sum of valid counts; -9999 where empty."""
    from scipy.ndimage import correlate1d

    def box(x: np.ndarray) -> np.ndarray:
        y = correlate1d(x.astype("float64"), weights, axis=0, mode="constant")
        return correlate1d(y, weights, axis=1, mode="constant")

    c, v = box(crop_n), box(valid_n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(v > 0, c / v, -9999.0).astype("float32")


# ------------------------------------------------------------ build
def build(ctx: BuildContext, wanted: set[str]) -> None:
    """Build the land-cover layers in ``wanted`` that are not already staged."""
    todo = {lid for lid in wanted if lid in LAYERS and not ctx.done(lid)}
    if not todo:
        return
    g = ctx.grid
    src = ctx.catalog.source(SOURCE)
    tiles = tiles_for(g)
    out = np.full(g.shape, ND, dtype="uint8")
    crop_n = np.zeros(g.shape, dtype="int32")
    valid_n = np.zeros(g.shape, dtype="int32")
    inputs, got, fetched = [], 0, []
    target = int(ctx.settings.get("cropland_class", 40))
    for la, lo in tiles:
        name = tile_name(la, lo)
        url = "%s/%s.tif" % (S3, name)
        p = ctx.downloader.fetch(SOURCE, url, name + ".tif", absent_ok=True)
        if p is None:
            logger.info("  (no tile %s)", name)
            continue
        got += 1
        fetched.append(name + ".tif")
        inputs.append(ctx.downloader.input_entry(SOURCE, name + ".tif"))
        if "land_cover" in todo:
            a = mode_tile(str(p), g)
            m = a > 0
            out[m] = a[m]
        if "cropland_fraction_1km" in todo:
            with rasterio.open(p) as s:
                strip = 1080
                for r0 in range(0, s.height, strip):
                    win = Window(0, r0, s.width, min(strip, s.height - r0))
                    count_into(g, s.read(1, window=win), s.window_transform(win), target, crop_n, valid_n)
        logger.info("  merged %s (%d/%d)", name, got, len(tiles))
        if ctx.prune:
            ctx.downloader.prune(SOURCE, [name + ".tif"])
    if "land_cover" in todo:
        ctx.emit("land_cover", out, inputs)
    if "cropland_fraction_1km" in todo:
        wts = box_weights(float(ctx.settings.get("cropland_window_m", 1000)), g)
        ctx.emit("cropland_fraction_1km", box_fraction(crop_n, valid_n, wts), inputs,
                 notes=f"box weights per axis {wts.tolist()} (cells of {g.res} degrees)")
