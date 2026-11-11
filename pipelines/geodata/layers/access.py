"""Access (brief E3 B5): ``travel_time_to_city_min`` from the Malaria Atlas Project 2015
accessibility-to-cities raster (Weiss et al. 2018, CC BY 4.0).

The global GeoTIFF is a large zip; the MAP geoserver's WCS 2.0.1 ``GetCoverage``
returns the native 30 arc-second cells of the padded country box (~15 MB), which is
what the cache keeps. Warped bilinear onto the grid; negative values are nodata.
"""
from __future__ import annotations

import logging

import numpy as np
import rasterio

from ..core import BuildContext, nodata_mask
from .climate_worldclim import ND, to_grid

logger = logging.getLogger("geodata.access")

GROUP = "access"
LAYERS = ("travel_time_to_city_min",)
SOURCE = "map_travel_time_2015"


def wcs_url(template: str, bounds: tuple[float, float, float, float]) -> str:
    l, b, r, t = bounds
    return template.format(lon_min=round(l, 4), lon_max=round(r, 4), lat_min=round(b, 4), lat_max=round(t, 4))


def build(ctx: BuildContext, wanted: set[str]) -> None:
    """Fetch the WCS clip (cached) and warp it onto the grid."""
    if "travel_time_to_city_min" not in wanted or ctx.done("travel_time_to_city_min"):
        return
    src = ctx.catalog.source(SOURCE)
    bounds = ctx.grid.padded_bounds(ctx.pad)
    url = wcs_url(src["url_template"], bounds)
    name = f"travel_time_2015__{ctx.country.code}_{ctx.grid.hash()[:8]}.tif"
    p = ctx.downloader.fetch(SOURCE, url, name)
    with rasterio.open(p) as s:
        a = s.read(1).astype("float32")
        a[nodata_mask(a, s.nodata) | (a < 0)] = np.nan
        tr, crs = s.transform, s.crs
    ctx.emit("travel_time_to_city_min", to_grid(a, tr, crs, ctx.grid), [ctx.downloader.input_entry(SOURCE, name)])
    _ = ND
