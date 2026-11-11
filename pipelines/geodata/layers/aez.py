"""The national agro-ecological belt (brief E3 B1): ``aez_belt``, and the country mask.

``geodata/layers/aez_belt.tif`` was rasterized from
``geodata/sources/agroecology_belt/agroecology.shp`` (UTM 37N) by burning each
polygon's ``OBJECTID`` with its **outer rings only**, in file order: verified cell for
cell (0 of 35,060,800 cells differ). Honouring the polygon holes would change
93,119 cells (0.5% of the country), the belt islands enclosed by another belt. The
release reproduces the legacy rule (the model was trained on it);
``rasterize_belt(..., holes=True)`` gives the hole-aware raster for a future release
(owner decision, ``docs/decisions/geodata_v2.md``); every manifest records the count.

A country without a national anchor (``countries/<cc>.yaml: aez.anchor_raster: null``
and no belt source) has no belt layer: :class:`LayerUnavailable`.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from ..core import BuildContext, LayerUnavailable, REPO_ROOT, sha256_file
from ..grid import Grid
from ..vector import read_dbf, read_prj, read_shp_polygons

logger = logging.getLogger("geodata.aez")

GROUP = "aez"
LAYERS = ("aez_belt",)
SOURCE = "belt_shapefile"


def rasterize_belt(shp: str, grid: Grid, holes: bool = False, attribute: str = "OBJECTID") -> np.ndarray:
    """Belt codes on the grid (cell-centre rule); ``holes=False`` is the legacy rule."""
    from rasterio.crs import CRS
    from rasterio.features import rasterize
    from rasterio.warp import transform_geom

    src_crs = CRS.from_wkt(read_prj(shp[:-4] + ".prj"))
    rows = read_dbf(shp[:-4] + ".dbf")
    shapes = []
    for geom, row in zip(read_shp_polygons(shp), rows):
        if geom is None:
            continue
        if not holes:
            geom = {"type": "MultiPolygon", "coordinates": [[p[0]] for p in geom["coordinates"]]}
        shapes.append((transform_geom(src_crs, grid.crs, geom), int(row[attribute])))
    return rasterize(shapes, out_shape=grid.shape, transform=grid.transform, fill=0, dtype="int16")


def has_anchor(country: Any) -> bool:
    """True when the country has a national AEZ anchor (Ethiopia's belt map)."""
    return bool(getattr(country.aez, "anchor_raster", None))


def build(ctx: BuildContext, wanted: set[str]) -> None:
    """Rasterize the belt shapefile and set the country mask (belt > 0)."""
    if "aez_belt" not in wanted:
        return
    if not has_anchor(ctx.country):
        raise LayerUnavailable("no national anchor: belt attribute unavailable; Koppen class and GAEZ zones "
                               "will stand in")
    if not ctx.done("aez_belt"):
        rel = ctx.catalog.source(SOURCE)["path"]
        shp = REPO_ROOT / rel
        belt = rasterize_belt(str(shp), ctx.grid, holes=False)
        holes = rasterize_belt(str(shp), ctx.grid, holes=True)
        n_diff = int((belt != holes).sum())
        inputs = [{"source": SOURCE, "file": p.name, "sha256": sha256_file(p), "bytes": p.stat().st_size,
                   "path": str(p.relative_to(REPO_ROOT)).replace("\\", "/")}
                  for p in sorted(shp.parent.glob(shp.stem + ".*")) if p.suffix in (".shp", ".dbf", ".prj", ".shx")]
        ctx.emit("aez_belt", belt, inputs, extra={"hole_aware_cells_differing": n_diff},
                 notes=f"outer rings only (legacy rule); a hole-aware rasterization differs on {n_diff} cells")
    ctx.mask = ctx.staged_array("aez_belt") > 0
