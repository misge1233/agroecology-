"""Koppen-Geiger class (brief E3 B6) from Beck et al. (2018), present-day 1 km map.

``Beck_KG_V1.zip`` is on figshare, which answers scripted clients with a browser
challenge, so the source is ``manual: true``: the owner downloads the zip once from
https://doi.org/10.6084/m9.figshare.6396959 into ``cache/koppen_beck2018/``. The
member ``Beck_KG_V1_present_0p0083.tif`` is read through GDAL's ``/vsizip/``,
clipped and resampled with nearest neighbour onto the grid (categorical).
"""
from __future__ import annotations

import logging

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

from ..core import BuildContext, clip_to_bounds

logger = logging.getLogger("geodata.koppen")

GROUP = "koppen"
LAYERS = ("koppen_class",)
SOURCE = "koppen_beck2018"

#: Beck et al. (2018) legend, class code -> (symbol, description).
LEGEND: dict[int, tuple[str, str]] = {
    1: ("Af", "Tropical, rainforest"), 2: ("Am", "Tropical, monsoon"), 3: ("Aw", "Tropical, savannah"),
    4: ("BWh", "Arid, desert, hot"), 5: ("BWk", "Arid, desert, cold"), 6: ("BSh", "Arid, steppe, hot"),
    7: ("BSk", "Arid, steppe, cold"), 8: ("Csa", "Temperate, dry summer, hot summer"),
    9: ("Csb", "Temperate, dry summer, warm summer"), 10: ("Csc", "Temperate, dry summer, cold summer"),
    11: ("Cwa", "Temperate, dry winter, hot summer"), 12: ("Cwb", "Temperate, dry winter, warm summer"),
    13: ("Cwc", "Temperate, dry winter, cold summer"), 14: ("Cfa", "Temperate, no dry season, hot summer"),
    15: ("Cfb", "Temperate, no dry season, warm summer"), 16: ("Cfc", "Temperate, no dry season, cold summer"),
    17: ("Dsa", "Cold, dry summer, hot summer"), 18: ("Dsb", "Cold, dry summer, warm summer"),
    19: ("Dsc", "Cold, dry summer, cold summer"), 20: ("Dsd", "Cold, dry summer, very cold winter"),
    21: ("Dwa", "Cold, dry winter, hot summer"), 22: ("Dwb", "Cold, dry winter, warm summer"),
    23: ("Dwc", "Cold, dry winter, cold summer"), 24: ("Dwd", "Cold, dry winter, very cold winter"),
    25: ("Dfa", "Cold, no dry season, hot summer"), 26: ("Dfb", "Cold, no dry season, warm summer"),
    27: ("Dfc", "Cold, no dry season, cold summer"), 28: ("Dfd", "Cold, no dry season, very cold winter"),
    29: ("ET", "Polar, tundra"), 30: ("EF", "Polar, frost"),
}


def to_grid_nearest(a: np.ndarray, tr, crs, grid, nodata: int = 0) -> np.ndarray:
    dst = np.full(grid.shape, nodata, dtype="uint8")
    reproject(source=a, destination=dst, src_transform=tr, src_crs=crs, src_nodata=nodata,
              dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=nodata, resampling=Resampling.nearest)
    return dst


def build(ctx: BuildContext, wanted: set[str]) -> None:
    """Clip the present-day map from the (manually cached) zip and resample nearest."""
    if "koppen_class" not in wanted or ctx.done("koppen_class"):
        return
    src = ctx.catalog.source(SOURCE)
    zname = src.get("filename", "Beck_KG_V1.zip")
    zpath = ctx.downloader.fetch(SOURCE, src["url"], zname, manual=bool(src.get("manual")),
                                 approx_mb=src.get("approx_mb"), landing=src.get("landing_page"))
    clip = ctx.downloader.folder(SOURCE) / "clips" / f"koppen_present__{ctx.country.code}.tif"
    clip_to_bounds(f"/vsizip/{zpath}/{src['member']}", ctx.grid.padded_bounds(ctx.pad), clip)
    with rasterio.open(clip) as s:
        a = s.read(1).astype("uint8")
        tr, crs = s.transform, s.crs
    ctx.emit("koppen_class", to_grid_nearest(a, tr, crs, ctx.grid), [ctx.downloader.input_entry(SOURCE, zname)],
             notes="legend: pipelines/geodata/layers/koppen.py LEGEND")
