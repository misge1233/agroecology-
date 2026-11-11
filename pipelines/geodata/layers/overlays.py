"""Omo-Gibe overlays (brief E3 B7, placeholder; no modelling use in E3).

``countries/ET.yaml: overlays.omo_gibe.rasters`` names a path (file or folder) for
``hotspot_coldspot`` and ``typology``. When a GeoTIFF exists there it is warped onto
the grid with nearest neighbour as ``overlay_hotspot_coldspot.tif`` /
``overlay_typology.tif``, and ``mask_omo_gibe.tif`` marks the cells where either
overlay has data (the basin extent from the raster footprint). When absent, the
manifest records the layer as ``pending``.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

from ..core import REPO_ROOT, BuildContext, nodata_mask, sha256_file

logger = logging.getLogger("geodata.overlays")

GROUP = "overlays"
LAYERS = ("overlay_hotspot_coldspot", "overlay_typology", "mask_omo_gibe")
KEYS = {"overlay_hotspot_coldspot": "hotspot_coldspot", "overlay_typology": "typology"}
ND = -9999


def find_raster(rel: str | None, root: Path = REPO_ROOT) -> Path | None:
    """The configured GeoTIFF, or the first ``*.tif`` in the configured folder."""
    if not rel:
        return None
    p = root / rel
    if p.is_file() and p.suffix.lower() in (".tif", ".tiff"):
        return p
    if p.is_dir():
        hits = sorted(list(p.glob("*.tif")) + list(p.glob("*.tiff")))
        return hits[0] if hits else None
    return None


def warp_nearest(path: Path, grid) -> np.ndarray:
    with rasterio.open(path) as s:
        dst = np.full(grid.shape, ND, dtype="int16")
        a = s.read(1)
        valid = ~nodata_mask(a, s.nodata)
        src = np.where(valid, a, ND).astype("int16")
        reproject(source=src, destination=dst, src_transform=s.transform, src_crs=s.crs, src_nodata=ND,
                  dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=ND, resampling=Resampling.nearest)
    return dst


def build(ctx: BuildContext, wanted: set[str]) -> None:
    """Warp the overlays that exist; record the rest as pending."""
    todo = [lid for lid in LAYERS if lid in wanted and not ctx.done(lid)]
    if not todo:
        return
    cfg = (ctx.country.overlays or {}).get("omo_gibe") or {}
    rasters = cfg.get("rasters") or {}
    built: dict[str, np.ndarray] = {}
    for lid, key in KEYS.items():
        p = find_raster(rasters.get(key))
        if p is None:
            if lid in todo:
                ctx.mark(lid, "pending", f"no GeoTIFF at countries/{ctx.country.code}.yaml overlays.omo_gibe."
                                         f"rasters.{key} = {rasters.get(key)!r}")
            continue
        arr = warp_nearest(p, ctx.grid)
        built[lid] = arr
        if lid in todo:
            ctx.emit(lid, arr, [{"source": f"overlay:{key}", "file": str(p.relative_to(REPO_ROOT)),
                                 "sha256": sha256_file(p), "bytes": p.stat().st_size}])
    if "mask_omo_gibe" in todo:
        if built:
            mask = np.zeros(ctx.grid.shape, dtype="uint8")
            for arr in built.values():
                mask[arr != ND] = 1
            ctx.emit("mask_omo_gibe", mask, notes=f"footprint of {sorted(built)}")
        else:
            ctx.mark("mask_omo_gibe", "pending", "no overlay raster present")
