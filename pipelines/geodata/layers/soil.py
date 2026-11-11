"""Soil layers from SoilGrids (brief E3 B1 and B3).

Legacy (moved from ``pipelines/features/get_soil.py``): ``soil_clay``, ``soil_ph``,
``soil_soc`` at 0-5 cm, streamed from the public SoilGrids v2 VRTs through
``/vsicurl/`` and a :class:`rasterio.vrt.WarpedVRT` (bilinear) onto the grid.

New (B3), 0-30 cm as the thickness-weighted mean of 0-5, 5-15 and 15-30 cm
(weights 5, 10, 15): ``soil_sand``, ``soil_bulk_density``, ``soil_cec``,
``soil_nitrogen``; ``soil_awc`` by the Saxton and Rawls (2006) pedotransfer
functions; ``soil_depth_bedrock`` from the 2017 SoilGrids250m BDRICM product
(SoilGrids v2 has no depth to bedrock), optional.

Every streamed warp is cached as a grid-aligned float32 GeoTIFF in
``cache/soilgrids_v2/`` with its SHA-256, so ``--skip-download`` reruns offline.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from ..core import BuildContext, MissingInput, read_band, sha256_file, utc_now
from ..grid import Grid

logger = logging.getLogger("geodata.soil")

GROUP = "soil"
LEGACY = ("soil_clay", "soil_ph", "soil_soc")
NEW = ("soil_sand", "soil_bulk_density", "soil_cec", "soil_nitrogen", "soil_awc", "soil_depth_bedrock")
LAYERS = LEGACY + NEW
SOURCE = "soilgrids_v2"
ND = -9999.0
SG = "https://files.isric.org/soilgrids/latest/data/%s/%s_0-5cm_mean.vrt"
DEPTHS = (("0-5cm", 5.0), ("5-15cm", 10.0), ("15-30cm", 15.0))

#: out name -> (property, scale to conventional units, unit label)  (get_soil.py)
PROPS = {
    "soil_clay.tif": ("clay", 0.1, "percent"),
    "soil_ph.tif": ("phh2o", 0.1, "pH"),
    "soil_soc.tif": ("soc", 0.1, "g/kg"),
}
#: B3 properties: layer -> (SoilGrids property, scale)
PROPS_0_30 = {
    "soil_sand": ("sand", 0.1),         # g/kg -> %
    "soil_bulk_density": ("bdod", 0.01),  # cg/cm3 -> g/cm3
    "soil_cec": ("cec", 0.1),           # mmol(c)/kg -> cmol(c)/kg
    "soil_nitrogen": ("nitrogen", 0.01),  # cg/kg -> g/kg
}
GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.vrt",
                VSI_CACHE="TRUE", GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="5")


# ------------------------------------------------------------ moved logic (get_soil.py)
def warp_remote(url: str, grid: Grid, scale: float, resampling: Resampling = Resampling.bilinear) -> np.ndarray:
    """Stream a remote raster through a WarpedVRT onto the grid; scaled, -9999 for nodata (get_soil.py)."""
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open("/vsicurl/" + url) as src:
            with WarpedVRT(src, crs=grid.crs, transform=grid.transform, width=grid.ncols, height=grid.nrows,
                           resampling=resampling) as vrt:
                a = vrt.read(1).astype("float32")
                src_nd = src.nodata
    valid = np.ones(a.shape, bool) if src_nd is None else (a != src_nd)
    return np.where(valid, a * scale, ND).astype("float32")


# ------------------------------------------------------------ new: depth means and AWC
def depth_weighted(layers: list[np.ndarray], weights: list[float]) -> np.ndarray:
    """Thickness-weighted mean; -9999 where any depth is missing."""
    stack = np.stack(layers)
    ok = (stack > ND).all(axis=0)
    w = np.asarray(weights, dtype="float32")[:, None, None]
    mean = (np.where(stack > ND, stack, 0) * w).sum(axis=0) / w.sum()
    return np.where(ok, mean, ND).astype("float32")


def saxton_rawls_awc(sand_pct: np.ndarray, clay_pct: np.ndarray, om_pct: np.ndarray,
                     bulk_density: np.ndarray) -> np.ndarray:
    """Available water capacity (mm/m) by Saxton and Rawls (2006), with the density adjustment.

    Eq. 1: theta_1500; eq. 2: theta_33; eq. 3: theta_(S-33); eq. 5: theta_S; eq. 6:
    rho_N; density factor DF = rho_measured / rho_N bounded to 0.9-1.3 (their range);
    eqs. 7-8: theta_S-DF, theta_33-DF. AWC = theta_33-DF - theta_1500 (eq. 1 is not
    density-adjusted). Organic matter is capped at 8% (the calibration range).
    """
    S = np.asarray(sand_pct, dtype="float32") / 100.0  # float32 throughout: the coefficients have 3 digits
    C = np.asarray(clay_pct, dtype="float32") / 100.0
    OM = np.clip(np.asarray(om_pct, dtype="float32"), 0, 8)
    t1500t = -0.024 * S + 0.487 * C + 0.006 * OM + 0.005 * S * OM - 0.013 * C * OM + 0.068 * S * C + 0.031
    t1500 = t1500t + (0.14 * t1500t - 0.02)
    t33t = -0.251 * S + 0.195 * C + 0.011 * OM + 0.006 * S * OM - 0.027 * C * OM + 0.452 * S * C + 0.299
    t33 = t33t + (1.283 * t33t ** 2 - 0.374 * t33t - 0.015)
    ts33t = 0.278 * S + 0.034 * C + 0.022 * OM - 0.018 * S * OM - 0.027 * C * OM - 0.584 * S * C + 0.078
    ts33 = ts33t + (0.636 * ts33t - 0.107)
    ts = t33 + ts33 - 0.097 * S + 0.043
    rho_n = (1 - ts) * 2.65
    df = np.clip(np.asarray(bulk_density, dtype="float32") / rho_n, 0.9, 1.3)
    rho_df = rho_n * df
    ts_df = 1 - rho_df / 2.65
    t33_df = t33 - 0.2 * (ts - ts_df)
    awc = np.clip(t33_df - t1500, 0, None) * 1000.0
    return awc.astype("float32")


def awc_layer(sand: np.ndarray, clay: np.ndarray, soc_gkg: np.ndarray, bd: np.ndarray,
              rows: int = 256) -> np.ndarray:
    """AWC (mm/m) on the grid; organic matter = SOC (g/kg) / 10 x 1.724; -9999 where an input is missing.

    Computed in float32 and in blocks of ``rows`` rows: the pedotransfer needs about 20
    temporaries, which at full-grid float64 size cost 5 GB (the E3 run's MemoryError).
    """
    out = np.full(sand.shape, ND, dtype="float32")
    for r0 in range(0, sand.shape[0], rows):
        sl = slice(r0, r0 + rows)
        s_, c_, o_, b_ = sand[sl], clay[sl], soc_gkg[sl], bd[sl]
        ok = (s_ > ND) & (c_ > ND) & (o_ > ND) & (b_ > 0)
        om = np.where(ok, o_, 0) / 10.0 * 1.724
        blk = saxton_rawls_awc(np.where(ok, s_, 0), np.where(ok, c_, 0), om, np.where(ok, b_, 1.3))
        out[sl] = np.where(ok, blk, ND)
    return out


# ------------------------------------------------------------ cached fetch
def fetch(ctx: BuildContext, prop: str, depth: str, scale: float, source: str = SOURCE,
          url: str | None = None) -> tuple[np.ndarray, dict[str, Any]]:
    """One SoilGrids property/depth on the grid (cached clip, or a streamed warp)."""
    url = url or ctx.catalog.source(source)["url_template"].format(prop=prop, depth=depth)
    name = f"{prop}_{depth}__{ctx.country.code}_{ctx.grid.hash()[:8]}.tif"
    p = ctx.downloader.path(source, name)
    if p.exists() and ctx.downloader.verify(source, name):
        return read_band(p)[0], ctx.downloader.input_entry(source, name)
    if ctx.downloader.offline:
        raise MissingInput(f"{p} is not cached (--skip-download)")
    logger.info("  streaming %s %s from %s (a few minutes)", prop, depth, url.rsplit("/", 1)[-1])
    a = warp_remote(url, ctx.grid, scale)
    ctx.downloader.folder(source)
    prof = ctx.grid.profile("float32", ND)
    prof.update(compress="deflate")
    tmp = p.with_suffix(".part.tif")
    with rasterio.open(tmp, "w", **prof) as d:
        d.write(a, 1)
    os.replace(tmp, p)
    ctx.downloader.record(source, name, url=url, sha256=sha256_file(p), bytes=p.stat().st_size, status="ok",
                          downloaded_utc=utc_now(), method="vsicurl WarpedVRT bilinear onto the grid", scale=scale)
    return a, ctx.downloader.input_entry(source, name)


# ------------------------------------------------------------ build
def build(ctx: BuildContext, wanted: set[str]) -> None:
    """Build the soil layers in ``wanted`` that are not already staged."""
    todo = {lid for lid in wanted if lid in LAYERS and not ctx.done(lid)}
    if not todo:
        return
    for out, (prop, scale, _unit) in PROPS.items():
        lid = Path(out).stem
        if lid in todo:
            a, inp = fetch(ctx, prop, "0-5cm", scale)
            ctx.emit(lid, a, [inp])
    cache: dict[str, tuple[np.ndarray, list[dict[str, Any]]]] = {}

    def p030(prop: str, scale: float) -> tuple[np.ndarray, list[dict[str, Any]]]:
        if prop not in cache:
            parts = [fetch(ctx, prop, d, scale) for d, _ in DEPTHS]
            cache[prop] = (depth_weighted([a for a, _ in parts], [w for _, w in DEPTHS]), [i for _, i in parts])
        return cache[prop]

    for lid, (prop, scale) in PROPS_0_30.items():
        if lid in todo:
            a, inp = p030(prop, scale)
            ctx.emit(lid, a, inp, notes="0-30 cm, thickness-weighted (5, 10, 15 cm)")
    if "soil_awc" in todo:
        sand, i1 = p030("sand", 0.1)
        clay, i2 = p030("clay", 0.1)
        soc, i3 = p030("soc", 0.1)
        bd, i4 = p030("bdod", 0.01)
        ctx.emit("soil_awc", awc_layer(sand, clay, soc, bd), i1 + i2 + i3 + i4,
                 notes="Saxton and Rawls (2006), 0-30 cm, OM = SOC x 1.724, density factor from bdod")
    if "soil_depth_bedrock" in todo:
        src = ctx.catalog.source("soilgrids_2017_bdricm")
        try:
            a, inp = fetch(ctx, "BDRICM", "M_250m", 1.0, source="soilgrids_2017_bdricm", url=src["url"])
            ctx.emit("soil_depth_bedrock", a, [inp], notes="SoilGrids250m 2017 (v2 has no depth-to-bedrock layer)")
        except Exception as exc:  # noqa: BLE001  optional layer: record and continue
            logger.warning("  soil_depth_bedrock unavailable: %s", exc)
            ctx.mark("soil_depth_bedrock", "optional-missing", f"{type(exc).__name__}: {exc}")
