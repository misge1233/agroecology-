"""Recent climate normals from CHIRPS v2.0 monthly, 1991-2020 (brief E3 B4).

* ``rain_mean_1991_2020``: mean of the 30 annual totals (each the sum of 12 monthly files);
* ``rain_cv_interannual``: 100 x sample SD (ddof 1) / mean of the 30 annual totals;
* ``dry_season_length_months``: calendar months whose 1991-2020 mean is below
  ``settings.dry_month_mm`` (50 mm), counted on the grid after warping the 12
  climatological months bilinear (so the count follows the smooth rainfall field);
* ``aridity_index``: ``rain_mean_1991_2020 / pet_hargreaves_annual`` (UNEP P/PET).

Statistics are computed at the native 0.05 degree resolution on the padded country
clip and warped bilinear onto the grid. The 360 files (~1.5 GB) stay gzip-compressed
in the cache and are read through GDAL's ``/vsigzip/``.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import Resampling
from rasterio.windows import Window, from_bounds

from ..core import BuildContext, nodata_mask
from .climate_worldclim import ND, to_grid

logger = logging.getLogger("geodata.chirps")

GROUP = "climate_chirps"
LAYERS = ("rain_mean_1991_2020", "rain_cv_interannual", "dry_season_length_months", "aridity_index")
SOURCE = "chirps_monthly_africa"


def file_names(years: tuple[int, int]) -> list[tuple[int, int, str]]:
    """(year, month, file name) for the window."""
    return [(y, m, f"chirps-v2.0.{y}.{m:02d}.tif.gz") for y in range(years[0], years[1] + 1) for m in range(1, 13)]


def read_clip(path: str, bounds: tuple[float, float, float, float]) -> tuple[np.ndarray, Any, Any]:
    """Window of a CHIRPS file covering ``bounds`` (NaN for nodata and negative values)."""
    with rasterio.open(f"/vsigzip/{path}") as s:
        w = from_bounds(*bounds, transform=s.transform)
        c0, r0 = max(int(np.floor(w.col_off)), 0), max(int(np.floor(w.row_off)), 0)
        c1 = min(int(np.ceil(w.col_off + w.width)), s.width)
        r1 = min(int(np.ceil(w.row_off + w.height)), s.height)
        win = Window(c0, r0, c1 - c0, r1 - r0)
        a = s.read(1, window=win).astype("float32")
        a[nodata_mask(a, s.nodata) | (a < 0)] = np.nan
        return a, s.window_transform(win), s.crs


def climatology(annual: np.ndarray, monthly_sum: np.ndarray, n_years: int) -> dict[str, np.ndarray]:
    """Native-resolution statistics from the (years, h, w) annual totals and the 12 monthly sums."""
    mean = annual.mean(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        cv = np.where(mean > 0, 100.0 * annual.std(axis=0, ddof=1) / mean, np.nan)
    return {"mean": mean.astype("float32"), "cv": cv.astype("float32"),
            "monthly_mean": (monthly_sum / n_years).astype("float32")}


def dry_months(monthly_on_grid: np.ndarray, threshold_mm: float) -> np.ndarray:
    """Number of months below ``threshold_mm``; -9999 where any month is missing."""
    valid = ~np.isnan(monthly_on_grid).any(axis=0)
    count = (np.nan_to_num(monthly_on_grid, nan=np.inf) < threshold_mm).sum(axis=0)
    return np.where(valid, count, ND).astype("int16")


def aridity(rain: np.ndarray, pet: np.ndarray) -> np.ndarray:
    """P / PET with -9999 where either is missing or PET is not positive."""
    ok = (rain > ND) & (pet > 0) & ~np.isnan(rain) & ~np.isnan(pet)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(ok, rain / np.where(ok, pet, 1), ND).astype("float32")


def build(ctx: BuildContext, wanted: set[str]) -> None:
    """Build the CHIRPS layers in ``wanted`` that are not already staged."""
    todo = {lid for lid in wanted if lid in LAYERS and not ctx.done(lid)}
    if not todo:
        return
    g = ctx.grid
    src = ctx.catalog.source(SOURCE)
    years = tuple(int(y) for y in ctx.settings.get("chirps_years", (1991, 2020)))
    bounds = g.padded_bounds(ctx.pad)
    files = file_names(years)
    n_years = years[1] - years[0] + 1
    annual = None
    monthly_sum = None
    inputs = []
    tr = crs = None
    for i, (y, m, name) in enumerate(files):
        url = src["url_template"].format(year=y, month=m)
        p = ctx.downloader.fetch(SOURCE, url, name, throttle_s=float(src.get("throttle_s", 0)))
        if p is None:
            raise FileNotFoundError(f"CHIRPS {name} is absent on the server")
        inputs.append(ctx.downloader.input_entry(SOURCE, name))
        a, tr, crs = read_clip(str(p), bounds)
        if annual is None:
            annual = np.zeros((n_years,) + a.shape, dtype="float32")
            monthly_sum = np.zeros((12,) + a.shape, dtype="float32")
        annual[y - years[0]] += a
        monthly_sum[m - 1] += a
        if (i + 1) % 60 == 0:
            logger.info("  CHIRPS %d/%d files read", i + 1, len(files))
    st = climatology(annual, monthly_sum, n_years)
    notes = f"{len(files)} monthly files, {years[0]}-{years[1]}"
    rain = to_grid(st["mean"], tr, crs, g)
    if "rain_mean_1991_2020" in todo:
        ctx.emit("rain_mean_1991_2020", rain, inputs, notes=notes)
    if "rain_cv_interannual" in todo:
        ctx.emit("rain_cv_interannual", to_grid(st["cv"], tr, crs, g), inputs, notes=notes)
    if "dry_season_length_months" in todo:
        monthly = np.stack([to_grid(st["monthly_mean"][k], tr, crs, g, dst_nodata=np.nan) for k in range(12)])
        ctx.emit("dry_season_length_months", dry_months(monthly, float(ctx.settings.get("dry_month_mm", 50))),
                 inputs, notes=notes)
        del monthly
    if "aridity_index" in todo:
        if "pet_hargreaves_annual" not in ctx.entries or ctx.entries["pet_hargreaves_annual"].get("status") != "built":
            raise RuntimeError("aridity_index needs pet_hargreaves_annual (climate_worldclim group) first")
        pet = ctx.staged_array("pet_hargreaves_annual")
        pet_inputs = ctx.entries["pet_hargreaves_annual"].get("inputs", [])
        ctx.emit("aridity_index", aridity(rain, pet), [*inputs[:1], *pet_inputs],
                 notes=f"CHIRPS {years[0]}-{years[1]} mean / Hargreaves PET from WorldClim 2.1 (1970-2000)")
    _ = Resampling  # bilinear is the to_grid default
