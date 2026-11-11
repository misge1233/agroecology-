"""Read context values from a geodata release: one library for serving, training and the
evidence store (brief E3 C1).

``ContextExtractor(release_dir)`` opens a release (``geodata/ET/2026.1``, read from its
``manifest.json``) or, for comparison, a legacy layer folder without a manifest
(``geodata/layers``: every ``*.tif`` except ``stack_*``).

* :meth:`ContextExtractor.at` -> every layer at a point, nearest-valid fallback
  within ``max_radius_px`` cells when the point sits on a masked cell (SoilGrids masks
  cities and lakes), plus ``release_id``;
* :meth:`ContextExtractor.batch` -> ``ctx_<layer>`` columns for a DataFrame (each
  distinct coordinate sampled once);
* :meth:`ContextExtractor.legacy_context` -> exactly the dict
  ``app/backend/recommend.py:extract_context`` returns (same 11 fields, same
  rounding, same 120-cell fallback), so the backend can read a release without
  changing the engine.

Datasets are opened per call (as ``recommend.py`` does), so an extractor is safe to
share across threads.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import rasterio
from rasterio.windows import Window

from .core import LEGACY_LAYERS_DIR, REPO_ROOT

#: recommend.py STACK: layer file -> context key (wrap, never fork: same names and order).
LEGACY_STACK = {"precip_annual": "Rainfall", "temp_mean_annual": "temp_mean_annual",
                "precip_seasonality": "precip_seasonality", "elevation": "Altitude_r", "slope": "slope",
                "soil_clay": "soil_clay", "land_cover": "land_cover",
                "lgp_days": "lgp_days", "soil_ph": "soil_ph", "soil_soc": "soil_soc"}
#: The legacy training feature columns that come from the stack (the 13 legacy features minus the 5
#: practice/crop/indicator columns), and the three explanation-only extras of the dataset.
TRAINING_CONTEXT = {"Rainfall": "precip_annual", "Altitude_r": "elevation", "temp_mean_annual": "temp_mean_annual",
                    "precip_seasonality": "precip_seasonality", "slope": "slope", "soil_clay": "soil_clay",
                    "land_cover": "land_cover", "aez_belt": "aez_belt",
                    "lgp_days": "lgp_days", "soil_ph": "soil_ph", "soil_soc": "soil_soc"}
LEGACY_RADIUS = 120  # recommend.py MAXR
CLI_RADIUS = 80      # extract_features.py MAX_R
AEZ_LOOKUP = REPO_ROOT / "data" / "lookups" / "aez_belt_lookup.csv"


def _isnd(v: Any, nd: Any) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v)) or (nd is not None and v == nd)


def nearest_valid(src: Any, lon: float, lat: float, nd: Any, max_r: int) -> Any:
    """Value of the nearest valid cell within ``max_r`` cells (extract_features.py / recommend.py rule)."""
    try:
        row, col = src.index(lon, lat)
    except Exception:  # noqa: BLE001
        return None
    H, W = src.height, src.width
    if not (0 <= row < H and 0 <= col < W):
        return None
    r0, r1 = max(0, row - max_r), min(H, row + max_r + 1)
    c0, c1 = max(0, col - max_r), min(W, col + max_r + 1)
    block = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0))
    if nd is not None:
        valid = (block != nd) & ~np.isnan(block) if block.dtype.kind == "f" else (block != nd)
    else:
        valid = ~np.isnan(block) if block.dtype.kind == "f" else np.ones(block.shape, bool)
    if not valid.any():
        return None
    rr, cc = np.where(valid)
    d2 = (rr - (row - r0)) ** 2 + (cc - (col - c0)) ** 2
    return block[rr[int(np.argmin(d2))], cc[int(np.argmin(d2))]].item()


def load_aez_lookup(path: Path = AEZ_LOOKUP) -> dict[int, str]:
    """Belt code -> belt name (``aez_belt_lookup.csv``, the lookup recommend.py reads)."""
    out: dict[int, str] = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[int(r["value_OBJECTID"])] = r["Agro_zone"]
    return out


class ContextExtractor:
    """Point and batch access to the layers of a release (or of a legacy layer folder)."""

    def __init__(self, release_dir: Path | str, max_radius_px: int = CLI_RADIUS,
                 aez_lookup: dict[int, str] | None = None):
        self.dir = Path(release_dir)
        if not self.dir.is_dir():
            raise FileNotFoundError(f"geodata release folder {self.dir} not found")
        self.max_radius_px = int(max_radius_px)
        self.manifest: dict[str, Any] | None = None
        mpath = self.dir / "manifest.json"
        if mpath.exists():
            self.manifest = json.loads(mpath.read_text(encoding="utf-8"))
            self.release_id: str | None = self.manifest["release_id"]
            self.layers: dict[str, Path] = {lid: self.dir / e["file"] for lid, e in self.manifest["layers"].items()
                                            if e.get("status") == "built" and e.get("file")}
            self.kinds = {lid: e.get("kind", "continuous") for lid, e in self.manifest["layers"].items()}
        else:
            self.release_id = None
            self.layers = {p.stem: p for p in sorted(self.dir.glob("*.tif")) if not p.name.startswith("stack_")}
            self.kinds = {lid: ("categorical" if lid in ("aez_belt", "land_cover") else "continuous")
                          for lid in self.layers}
        missing = [str(p) for p in self.layers.values() if not p.exists()]
        if missing:
            raise FileNotFoundError(f"release {self.dir} lists missing layer files: {missing}")
        self._aez = aez_lookup

    # ------------------------------------------------------------ helpers
    @classmethod
    def for_release(cls, release: str, geodata_dir: Path | str = REPO_ROOT / "geodata", **kw: Any) -> "ContextExtractor":
        """Extractor for ``ET/2026.1`` under ``geodata_dir``."""
        return cls(Path(geodata_dir) / release, **kw)

    @property
    def aez_lookup(self) -> dict[int, str]:
        if self._aez is None:
            self._aez = load_aez_lookup()
        return self._aez

    def layer_ids(self) -> list[str]:
        return list(self.layers)

    def extended_ids(self) -> list[str]:
        """Layers beyond the legacy 11 (served under ``context.extended``)."""
        return [lid for lid in self.layers if lid not in LEGACY_STACK and lid != "aez_belt"]

    def sample(self, points: Sequence[tuple[float, float]], layers: Iterable[str] | None = None,
               max_radius_px: int | None = None) -> list[dict[str, Any]]:
        """Raw values (Python scalars, ``None`` when nothing valid within the radius) at ``(lon, lat)`` points.

        The rule of ``extract_features.sample_points``: ``src.sample`` first, the
        nearest valid cell when that is nodata.
        """
        r = self.max_radius_px if max_radius_px is None else int(max_radius_px)
        rows: list[dict[str, Any]] = [{} for _ in points]
        for lid in (list(layers) if layers is not None else self.layer_ids()):
            if lid not in self.layers:
                continue
            with rasterio.open(self.layers[lid]) as src:
                nd = src.nodata
                vals = [v[0] for v in src.sample(points)]
                for i, val in enumerate(vals):
                    if _isnd(val, nd) or (lid == "aez_belt" and val == 0):
                        val = nearest_valid(src, points[i][0], points[i][1], nd, r)
                    rows[i][lid] = None if val is None else (val.item() if hasattr(val, "item") else val)
        return rows

    # ------------------------------------------------------------ public API
    def at(self, lat: float, lon: float) -> dict[str, Any]:
        """Every layer at a point (raw values; ``land_cover`` and ``aez_belt`` as codes) plus ``release_id``."""
        out = self.sample([(float(lon), float(lat))])[0]
        out["release_id"] = self.release_id
        return out

    def batch(self, df: Any, lat_col: str = "lat", lon_col: str = "lon", layers: Iterable[str] | None = None,
              max_radius_px: int | None = None, prefix: str = "ctx_") -> Any:
        """``ctx_<layer>`` columns for every row of ``df`` (NaN coordinates give nulls)."""
        import pandas as pd

        lids = list(layers) if layers is not None else self.layer_ids()
        lat = pd.to_numeric(df[lat_col], errors="coerce")
        lon = pd.to_numeric(df[lon_col], errors="coerce")
        ok = lat.notna() & lon.notna()
        pts = sorted(set(zip(lon[ok].astype(float), lat[ok].astype(float))))
        vals = dict(zip(pts, self.sample(pts, lids, max_radius_px)))
        out = pd.DataFrame(index=df.index)
        for lid in lids:
            out[f"{prefix}{lid}"] = [vals[(float(x), float(y))].get(lid) if k else None
                                     for x, y, k in zip(lon, lat, ok)]
            out[f"{prefix}{lid}"] = pd.to_numeric(out[f"{prefix}{lid}"], errors="coerce")
        return out

    def legacy_context(self, lat: float, lon: float, with_extended: bool = True) -> dict[str, Any]:
        """``recommend.extract_context(lat, lon)`` read from this release.

        Same keys, values and rounding as the engine (``land_cover`` int, others
        ``round(float, 3)``, belt name through the lookup, 120-cell fallback). With
        ``with_extended`` the dict also carries ``release`` and ``extended`` (the new
        layers, raw values), which the engine ignores.
        """
        ctx: dict[str, Any] = {}
        pt = [(float(lon), float(lat))]
        raw = self.sample(pt, list(LEGACY_STACK) + ["aez_belt"], max_radius_px=LEGACY_RADIUS)[0]
        for fn, col in LEGACY_STACK.items():
            val = raw.get(fn)
            ctx[col] = None if val is None else (int(val) if col == "land_cover" else round(float(val), 3))
        v = raw.get("aez_belt")
        ctx["aez_belt"] = self.aez_lookup.get(int(v)) if v else None
        if with_extended:
            ctx["release"] = self.release_id
            ext = self.sample(pt, self.extended_ids(), max_radius_px=LEGACY_RADIUS)[0] if self.extended_ids() else {}
            ctx["extended"] = {k: (round(float(x), 4) if isinstance(x, float) else x) for k, x in ext.items()}
        return ctx


def default_legacy_dir() -> Path:
    """The current, unversioned stack."""
    return LEGACY_LAYERS_DIR
