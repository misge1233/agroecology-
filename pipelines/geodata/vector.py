"""Minimal ESRI shapefile reader and rasterizer (polygons only).

The national belt shapefile is the anchor of the Ethiopian stack
(``geodata/sources/agroecology_belt/agroecology.shp``, UTM 37N). No vector
library (fiona, pyogrio, pyshp) is installed in the backend venv, and the
formats are small and stable, so this module reads them directly:

* ``.shp``: polygon records (shape types 5, 15, 25); rings are grouped into
  polygons by orientation (clockwise outer rings, counter-clockwise holes);
* ``.dbf``: dBASE III attribute records;
* ``.prj``: ESRI WKT, handed to GDAL through :class:`rasterio.crs.CRS`.

:func:`rasterize_shapefile` reprojects the polygons with
:func:`rasterio.warp.transform_geom` and burns one attribute with
:func:`rasterio.features.rasterize` (cell-centre rule, ``all_touched=False``).
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Iterator

import numpy as np

POLYGON_TYPES = (5, 15, 25)


def read_dbf(path: Path | str) -> list[dict[str, Any]]:
    """Read a dBASE III table into a list of dicts (numbers parsed, strings stripped)."""
    data = Path(path).read_bytes()
    n, hlen, rlen = struct.unpack("<IHH", data[4:12])
    fields: list[tuple[str, str, int]] = []
    pos = 32
    while data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b"\0")[0].decode("ascii")
        fields.append((name, chr(data[pos + 11]), data[pos + 16]))
        pos += 32
    rows: list[dict[str, Any]] = []
    for i in range(n):
        rec = data[hlen + i * rlen: hlen + (i + 1) * rlen]
        if rec[:1] == b"*":  # deleted record
            continue
        off = 1
        row: dict[str, Any] = {}
        for name, ftype, length in fields:
            raw = rec[off:off + length].decode("latin-1").strip()
            off += length
            if ftype in "NF":
                try:
                    num = float(raw)
                    row[name] = int(num) if ftype == "N" and num.is_integer() and "." not in raw else num
                except ValueError:
                    row[name] = None
            else:
                row[name] = raw
        rows.append(row)
    return rows


def _signed_area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))


def read_shp_polygons(path: Path | str) -> Iterator[dict[str, Any] | None]:
    """Yield one GeoJSON-like geometry per record (``None`` for null shapes)."""
    data = Path(path).read_bytes()
    code, = struct.unpack(">i", data[0:4])
    if code != 9994:
        raise ValueError(f"{path}: not a shapefile")
    pos = 100
    while pos + 8 <= len(data):
        _, content_words = struct.unpack(">ii", data[pos:pos + 8])
        rec = data[pos + 8: pos + 8 + content_words * 2]
        pos += 8 + content_words * 2
        stype, = struct.unpack("<i", rec[:4])
        if stype == 0:
            yield None
            continue
        if stype not in POLYGON_TYPES:
            raise ValueError(f"{path}: shape type {stype} is not a polygon")
        n_parts, n_points = struct.unpack("<ii", rec[36:44])
        parts = list(struct.unpack(f"<{n_parts}i", rec[44:44 + 4 * n_parts]))
        p0 = 44 + 4 * n_parts
        pts = np.frombuffer(rec[p0:p0 + 16 * n_points], dtype="<f8").reshape(n_points, 2)
        polys: list[list[list[tuple[float, float]]]] = []
        for k, start in enumerate(parts):
            end = parts[k + 1] if k + 1 < n_parts else n_points
            ring = pts[start:end]
            coords = [(float(x), float(y)) for x, y in ring]
            if _signed_area(ring) <= 0 or not polys:  # clockwise = outer ring
                polys.append([coords])
            else:
                polys[-1].append(coords)
        yield {"type": "MultiPolygon", "coordinates": polys}


def read_prj(path: Path | str) -> str:
    """ESRI WKT of the ``.prj`` beside a shapefile."""
    return Path(path).read_text(encoding="latin-1").strip()


def rasterize_shapefile(shp: Path | str, attribute: str, transform: Any, shape: tuple[int, int],
                        dst_crs: str = "EPSG:4326", dtype: str = "int16", fill: int = 0,
                        all_touched: bool = False) -> np.ndarray:
    """Burn ``attribute`` of every polygon of ``shp`` onto a grid (cell-centre rule)."""
    from rasterio.crs import CRS
    from rasterio.features import rasterize
    from rasterio.warp import transform_geom

    shp = Path(shp)
    src_crs = CRS.from_wkt(read_prj(shp.with_suffix(".prj")))
    rows = read_dbf(shp.with_suffix(".dbf"))
    shapes = []
    for geom, row in zip(read_shp_polygons(shp), rows):
        if geom is None or row.get(attribute) is None:
            continue
        g = transform_geom(src_crs, dst_crs, geom) if src_crs != CRS.from_string(dst_crs) else geom
        shapes.append((g, int(row[attribute])))
    return rasterize(shapes, out_shape=shape, transform=transform, fill=fill, dtype=dtype,
                     all_touched=all_touched)
