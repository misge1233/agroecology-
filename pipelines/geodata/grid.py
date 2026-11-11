"""The country grid every layer of a release is warped onto (brief E3 A1).

Ethiopia: ``countries/ET.yaml: grid`` points to ``data/lookups/grid_definition.json``
(WGS84, 0.00225 degrees, 6800 x 5156, the grid of ``geodata/layers/aez_belt.tif``).
A country without a grid file (Kenya, draft) gets one from its bounding box at the
same resolution, by the rule that reproduces the Ethiopian file exactly:
``ncols = ceil((lon_max - lon_min) / res)``, ``nrows = ceil((lat_max - lat_min) / res)``,
origin at ``(lon_min, lat_min + nrows * res)``.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

DEFAULT_RES_DEG = 0.00225
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Grid:
    """A north-up geographic grid (EPSG:4326 by default)."""

    xmin: float
    ymax: float
    res: float
    ncols: int
    nrows: int
    crs: str = "EPSG:4326"

    # ----------------------------------------------------------- derived
    @property
    def xmax(self) -> float:
        return round(self.xmin + self.ncols * self.res, 9)

    @property
    def ymin(self) -> float:
        return round(self.ymax - self.nrows * self.res, 9)

    @property
    def shape(self) -> tuple[int, int]:
        """(rows, cols)."""
        return (self.nrows, self.ncols)

    @property
    def transform(self):
        """The :class:`affine.Affine` of the grid."""
        from rasterio.transform import from_origin

        return from_origin(self.xmin, self.ymax, self.res, self.res)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(left, bottom, right, top)."""
        return (self.xmin, self.ymin, self.xmax, self.ymax)

    def row_lats(self) -> np.ndarray:
        """Latitude of every row centre (top to bottom)."""
        return self.ymax - (np.arange(self.nrows) + 0.5) * self.res

    def padded_bounds(self, pad: float) -> tuple[float, float, float, float]:
        """Bounds grown by ``pad`` degrees (clipping sources with a margin)."""
        l, b, r, t = self.bounds
        return (l - pad, b - pad, r + pad, t + pad)

    def subgrid(self, res: float) -> "Grid":
        """A finer (or coarser) grid with the same top-left corner covering the same extent."""
        ncols = int(math.ceil(round((self.xmax - self.xmin) / res, 6)))
        nrows = int(math.ceil(round((self.ymax - self.ymin) / res, 6)))
        return Grid(self.xmin, self.ymax, res, ncols, nrows, self.crs)

    def aligned(self, res: float) -> "Grid":
        """A grid of resolution ``res`` snapped to multiples of ``res`` that covers this grid.

        With ``res = 1/1200`` (3 arc-seconds) every cell edge falls on a multiple of
        ``res``, so no cell straddles the integer-degree seams of the DEM tiles.
        """
        k = round(1.0 / res)
        x0 = math.floor(round(self.xmin * k, 6)) / k
        y1 = math.ceil(round(self.ymax * k, 6)) / k
        x1 = math.ceil(round(self.xmax * k, 6)) / k
        y0 = math.floor(round(self.ymin * k, 6)) / k
        return Grid(x0, y1, 1.0 / k, int(round((x1 - x0) * k)), int(round((y1 - y0) * k)), self.crs)

    def window_of(self, bounds: tuple[float, float, float, float], pad_cells: int = 1) -> tuple[int, int, int, int] | None:
        """(row0, col0, row1, col1) of the cells covering ``bounds`` (padded, clipped), or ``None``."""
        l, b, r, t = bounds
        c0 = int(math.floor((l - self.xmin) / self.res)) - pad_cells
        c1 = int(math.ceil((r - self.xmin) / self.res)) + pad_cells
        r0 = int(math.floor((self.ymax - t) / self.res)) - pad_cells
        r1 = int(math.ceil((self.ymax - b) / self.res)) + pad_cells
        c0, r0, c1, r1 = max(c0, 0), max(r0, 0), min(c1, self.ncols), min(r1, self.nrows)
        if c0 >= c1 or r0 >= r1:
            return None
        return r0, c0, r1, c1

    def window_transform(self, r0: int, c0: int):
        from rasterio.transform import from_origin

        return from_origin(self.xmin + c0 * self.res, self.ymax - r0 * self.res, self.res, self.res)

    def profile(self, dtype: str, nodata: Any) -> dict[str, Any]:
        """A rasterio GTiff profile on this grid."""
        return dict(driver="GTiff", height=self.nrows, width=self.ncols, count=1, dtype=dtype,
                    crs=self.crs, transform=self.transform, nodata=nodata, compress="lzw",
                    tiled=True, blockxsize=256, blockysize=256)

    # --------------------------------------------------------- identity
    def definition(self) -> dict[str, Any]:
        """The ``grid_definition.json`` mapping of this grid."""
        return {"crs": self.crs, "res_deg": self.res, "res_m_approx": round(self.res * 111320.0, 1),
                "xmin": self.xmin, "ymin": round(self.ymin, 6), "xmax": round(self.xmax, 6),
                "ymax": self.ymax, "ncols": self.ncols, "nrows": self.nrows}

    def hash(self) -> str:
        """SHA-256 of the canonical grid identity (crs, origin, resolution, shape)."""
        ident = json.dumps({k: v for k, v in asdict(self).items()}, sort_keys=True)
        return hashlib.sha256(ident.encode("utf-8")).hexdigest()

    def matches(self, transform: Any, shape: tuple[int, int], crs: Any, tol: float = 1e-9) -> bool:
        """True when a raster's transform, shape and CRS are this grid's."""
        from rasterio.crs import CRS

        t = self.transform
        same_t = all(abs(a - b) <= tol for a, b in zip(tuple(transform)[:6], tuple(t)[:6]))
        try:
            same_crs = CRS.from_user_input(crs) == CRS.from_user_input(self.crs)
        except Exception:  # noqa: BLE001
            same_crs = False
        return same_t and tuple(shape) == self.shape and same_crs


def grid_from_definition(path: Path | str) -> Grid:
    """Read a ``grid_definition.json`` file."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return Grid(xmin=float(d["xmin"]), ymax=float(d["ymax"]), res=float(d["res_deg"]),
                ncols=int(d["ncols"]), nrows=int(d["nrows"]), crs=str(d.get("crs", "EPSG:4326")))


def grid_from_bbox(lon_min: float, lon_max: float, lat_min: float, lat_max: float,
                   res: float = DEFAULT_RES_DEG) -> Grid:
    """Grid covering a bounding box (the rule of ``grid_definition.json``)."""
    ncols = int(math.ceil(round((lon_max - lon_min) / res, 6)))
    nrows = int(math.ceil(round((lat_max - lat_min) / res, 6)))
    ymax = round(lat_min + nrows * res, 9)
    return Grid(xmin=float(lon_min), ymax=ymax, res=res, ncols=ncols, nrows=nrows)


def grid_from_raster(path: Path | str) -> Grid:
    """The grid of an existing single-band raster (the legacy reference ``aez_belt.tif``)."""
    import rasterio

    with rasterio.open(path) as s:
        t = s.transform
        return Grid(xmin=t.c, ymax=t.f, res=t.a, ncols=s.width, nrows=s.height, crs=s.crs.to_string())


def grid_for_country(cfg: Any, root: Path = REPO_ROOT, res: float = DEFAULT_RES_DEG) -> tuple[Grid, str]:
    """The grid of a :class:`~pipelines.common.country_config.CountryConfig` and how it was obtained."""
    if cfg.grid:
        p = root / cfg.grid
        if p.exists():
            return grid_from_definition(p), f"grid definition {cfg.grid}"
    b = cfg.bbox
    return grid_from_bbox(b.lon_min, b.lon_max, b.lat_min, b.lat_max, res), f"bbox at {res} degrees"
