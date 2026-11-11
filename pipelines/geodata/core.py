"""Shared pieces of the geodata pipeline: the source catalogue, hashing, COG writing,
warping helpers and the build context every layer module receives.

``sources.yaml`` is read once into a :class:`Catalog`; a layer module asks the
:class:`BuildContext` for cached inputs (through :mod:`pipelines.geodata.download`),
computes arrays on the :class:`~pipelines.geodata.grid.Grid` and hands them to
:meth:`BuildContext.emit`, which writes ``<layer>.tif`` (COG, LZW, overviews) and a
``<layer>.layer.json`` sidecar into the release staging folder. The sidecars become
the per-layer entries of ``manifest.json``.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml

from .grid import Grid

logger = logging.getLogger("geodata")

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[1]
SOURCES_YAML = PKG_DIR / "sources.yaml"
GEODATA_ROOT = REPO_ROOT / "geodata"
LEGACY_LAYERS_DIR = GEODATA_ROOT / "layers"


def cache_root() -> Path:
    """Download cache: ``GEODATA_CACHE`` if set (e.g. another drive), else ``pipelines/geodata/cache``."""
    env = os.environ.get("GEODATA_CACHE")
    return Path(env) if env else PKG_DIR / "cache"


# ------------------------------------------------------------------ machine resources
DISK_WARN_GB = 15.0


def peak_memory_mb() -> dict[str, float | None]:
    """Peak working set and peak committed memory (MB) of this process.

    Windows: ``GetProcessMemoryInfo`` (PeakWorkingSetSize, PeakPagefileUsage, the commit
    charge that a full pagefile refuses); POSIX: ``getrusage`` ``ru_maxrss`` (no commit figure).
    """
    if os.name == "nt":
        import ctypes
        import ctypes.wintypes as wt

        class _PMC(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        try:
            k32 = ctypes.windll.kernel32
            fn = getattr(k32, "K32GetProcessMemoryInfo", None) or ctypes.windll.psapi.GetProcessMemoryInfo
            fn.argtypes = [wt.HANDLE, ctypes.POINTER(_PMC), wt.DWORD]
            fn.restype = wt.BOOL
            k32.GetCurrentProcess.restype = wt.HANDLE
            ok = fn(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        except (AttributeError, OSError):
            ok = 0
        if not ok:
            return {"peak_rss_mb": None, "peak_commit_mb": None}
        return {"peak_rss_mb": round(pmc.PeakWorkingSetSize / 2 ** 20, 1),
                "peak_commit_mb": round(pmc.PeakPagefileUsage / 2 ** 20, 1)}
    import resource

    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"peak_rss_mb": round(ru / 2 ** 20 if sys.platform == "darwin" else ru / 1024, 1), "peak_commit_mb": None}


def disk_status(paths: Iterable[Path | str], needed_mb: float, warn_gb: float = DISK_WARN_GB) -> dict[str, Any]:
    """Free space of the drives holding ``paths`` against an estimate of what the run still needs.

    ``low`` lists drives under ``warn_gb``; ``short`` those with less free space than
    ``needed_mb`` (an estimate: downloads still to fetch, layers still to write, the
    terrain temporaries). The caller warns; the run goes on.
    """
    drives: dict[str, dict[str, float]] = {}
    for p in paths:
        q = Path(p).resolve()
        while not q.exists() and q.parent != q:
            q = q.parent
        key = str(q.anchor or q)  # the drive (C:\) or the mount point
        if key in drives:
            continue
        u = shutil.disk_usage(q)
        drives[key] = {"free_gb": round(u.free / 1e9, 1), "total_gb": round(u.total / 1e9, 1)}
    return {"drives": drives, "needed_mb": round(float(needed_mb)), "warn_below_gb": warn_gb,
            "low": [k for k, v in drives.items() if v["free_gb"] < warn_gb],
            "short": [k for k, v in drives.items() if v["free_gb"] * 1000 < needed_mb]}


# ------------------------------------------------------------------ errors
class GeodataError(RuntimeError):
    """Base class of pipeline errors."""


class MissingInput(GeodataError):
    """A cached input is absent and downloading is not allowed (``--skip-download``)."""


class ManualDownloadRequired(GeodataError):
    """A ``manual: true`` source must be dropped into the cache by the owner."""

    def __init__(self, url: str, dest: Path, approx_mb: float | None = None, landing: str | None = None):
        self.url, self.dest, self.approx_mb, self.landing = url, dest, approx_mb, landing
        size = f" (~{approx_mb:,.0f} MB)" if approx_mb else ""
        page = f" [landing page {landing}]" if landing else ""
        super().__init__(f"manual source: download {url}{page}{size} and save it as {dest}, "
                         f"or run `python pipelines/geodata/download.py --source {dest.parent.name}`")


class LayerUnavailable(GeodataError):
    """A layer cannot be built for a stated reason (credentials, no national anchor, ...)."""


# ------------------------------------------------------------------ catalogue
@dataclass(frozen=True)
class LayerSpec:
    """One layer of ``sources.yaml`` (brief A2 keys plus QA keys)."""

    id: str
    group: str
    sources: tuple[str, ...]
    source_name: str
    native_resolution: str
    resampling: str
    dtype: str
    nodata: Any
    unit: str
    update_cadence: str
    required: bool
    manual: bool
    kind: str = "continuous"
    classes: tuple[int, ...] | None = None
    valid_min: float | None = None
    valid_max: float | None = None
    max_nodata_share: float = 0.02
    legacy: bool = False
    method: str = ""
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def categorical(self) -> bool:
        return self.kind == "categorical"

    @property
    def ctx_column(self) -> str:
        """Column name in the evidence store and in ``ContextExtractor.batch``."""
        return f"ctx_{self.id}"


@dataclass(frozen=True)
class Catalog:
    """Parsed ``sources.yaml``."""

    layers: dict[str, LayerSpec]
    sources: dict[str, dict[str, Any]]
    settings: dict[str, Any]
    sha256: str
    path: Path

    def source(self, sid: str) -> dict[str, Any]:
        return self.sources[sid]

    def layer_meta(self, lid: str) -> dict[str, Any]:
        """Manifest fields of a layer: its own keys plus version/licence/citation/url of its sources."""
        spec = self.layers[lid]
        srcs = [self.sources[s] for s in spec.sources if s in self.sources]
        joined = lambda key: "; ".join(dict.fromkeys(str(s[key]) for s in srcs if s.get(key))) or None  # noqa: E731
        return {
            "id": spec.id, "group": spec.group, "sources": list(spec.sources), "source_name": spec.source_name,
            "url": joined("url") or joined("url_template") or joined("path"), "version": joined("version"),
            "licence": joined("licence"), "citation": joined("citation"),
            "native_resolution": spec.native_resolution, "resampling": spec.resampling, "dtype": spec.dtype,
            "nodata": spec.nodata, "unit": spec.unit, "update_cadence": spec.update_cadence,
            "required": spec.required, "manual": any(bool(s.get("manual")) for s in srcs), "kind": spec.kind,
            "classes": list(spec.classes) if spec.classes else None, "valid_min": spec.valid_min,
            "valid_max": spec.valid_max, "legacy": spec.legacy, "method": spec.method,
        }

    def legacy_ids(self) -> list[str]:
        return [k for k, v in self.layers.items() if v.legacy]


def load_catalog(path: Path | str = SOURCES_YAML) -> Catalog:
    """Read and check ``sources.yaml``."""
    path = Path(path)
    text = path.read_bytes()
    data = yaml.safe_load(text.decode("utf-8"))
    defaults = data.get("defaults") or {}
    sources = data.get("sources") or {}
    layers: dict[str, LayerSpec] = {}
    for lid, raw in (data.get("layers") or {}).items():
        d = {**defaults, **(raw or {})}
        for key in ("group", "source_name", "resampling", "unit", "update_cadence"):
            if not d.get(key):
                raise ValueError(f"{path}: layer {lid} has no {key}")
        for s in d.get("sources") or []:
            if s not in sources:
                raise ValueError(f"{path}: layer {lid} names unknown source {s}")
        layers[lid] = LayerSpec(
            id=lid, group=str(d["group"]), sources=tuple(d.get("sources") or ()), source_name=str(d["source_name"]),
            native_resolution=str(d.get("native_resolution", "")), resampling=str(d["resampling"]),
            dtype=str(d["dtype"]), nodata=d["nodata"], unit=str(d["unit"]), update_cadence=str(d["update_cadence"]),
            required=bool(d.get("required", False)), manual=bool(d.get("manual", False)),
            kind=str(d.get("kind", "continuous")),
            classes=tuple(int(c) for c in d["classes"]) if d.get("classes") else None,
            valid_min=d.get("valid_min"), valid_max=d.get("valid_max"),
            max_nodata_share=float(d.get("max_nodata_share", 0.02)), legacy=bool(d.get("legacy", False)),
            method=str(d.get("method", "")), raw=dict(raw or {}),
        )
    return Catalog(layers=layers, sources=sources, settings=data.get("settings") or {},
                   sha256=hashlib.sha256(text).hexdigest(), path=path)


# ------------------------------------------------------------------ hashing
def sha256_file(path: Path | str, chunk: int = 1 << 22) -> str:
    """SHA-256 of a file (streamed)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def data_sha256(array: np.ndarray) -> str:
    """SHA-256 of an array's values (dtype, shape and C-order bytes): equal pixels, equal hash."""
    a = np.ascontiguousarray(array)
    h = hashlib.sha256(f"{a.dtype.str}|{a.shape}|".encode())
    h.update(a.tobytes())
    return h.hexdigest()


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def git_commit(root: Path = REPO_ROOT) -> str | None:
    """Current commit (``None`` outside a work tree); a dirty tree is marked ``+dirty``."""
    import subprocess

    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
                             timeout=20).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True,
                               timeout=60).stdout.strip()
        return (sha + ("+dirty" if dirty else "")) or None
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ raster I/O
def resampling_of(name: str):
    """rasterio Resampling member from a name (``bilinear``, ``nearest``, ``mode``, ``average``, ``min``, ``max``)."""
    from rasterio.enums import Resampling

    return getattr(Resampling, name)


def nodata_mask(array: np.ndarray, nodata: Any) -> np.ndarray:
    """True where ``array`` is nodata (NaN counts as nodata for floats)."""
    m = np.zeros(array.shape, bool)
    if array.dtype.kind == "f":
        m |= np.isnan(array)
    if nodata is not None and not (isinstance(nodata, float) and np.isnan(nodata)):
        m |= array == nodata
    return m


def write_cog(path: Path, array: np.ndarray, grid: Grid, dtype: str, nodata: Any, categorical: bool) -> None:
    """Write a single-band Cloud Optimized GeoTIFF (LZW, predictor, internal overviews)."""
    import rasterio
    from rasterio.shutil import copy as rio_copy

    path = Path(path)
    tmp = path.with_suffix(".tmp.tif")
    prof = grid.profile(dtype, nodata)
    prof.update(compress="deflate")  # scratch copy only
    with rasterio.open(tmp, "w", **prof) as d:
        d.write(array.astype(dtype, copy=False), 1)
    rio_copy(tmp, path, driver="COG", COMPRESS="LZW", PREDICTOR="YES", BLOCKSIZE=512,
             OVERVIEW_RESAMPLING="NEAREST" if categorical else "AVERAGE", BIGTIFF="IF_SAFER")
    tmp.unlink(missing_ok=True)


def read_band(path: Path | str) -> tuple[np.ndarray, dict[str, Any]]:
    """First band and profile of a raster."""
    import rasterio

    with rasterio.open(path) as s:
        return s.read(1), dict(s.profile)


def clip_to_bounds(src_path: str, bounds: tuple[float, float, float, float], dst: Path) -> Path:
    """Copy the window of ``src_path`` covering ``bounds`` (native grid, no resampling) to ``dst``.

    The window is rounded outwards to whole source pixels and intersected with the
    source extent, so warping the clip onto the grid gives the same values as warping
    the global file (the margin in ``settings.pad_deg`` covers every resampling kernel).
    """
    import rasterio
    from rasterio.windows import Window, from_bounds

    with rasterio.open(src_path) as s:
        w = from_bounds(*bounds, transform=s.transform)
        c0, r0 = int(np.floor(w.col_off)), int(np.floor(w.row_off))
        c1, r1 = int(np.ceil(w.col_off + w.width)), int(np.ceil(w.row_off + w.height))
        c0, r0, c1, r1 = max(c0, 0), max(r0, 0), min(c1, s.width), min(r1, s.height)
        win = Window(c0, r0, c1 - c0, r1 - r0)
        a = s.read(1, window=win)
        prof = dict(driver="GTiff", height=a.shape[0], width=a.shape[1], count=1, dtype=a.dtype.name,
                    crs=s.crs, transform=s.window_transform(win), nodata=s.nodata, compress="deflate",
                    tiled=True, blockxsize=256, blockysize=256)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".part.tif")
    with rasterio.open(tmp, "w", **prof) as d:
        d.write(a, 1)
    os.replace(tmp, dst)
    return dst


# ------------------------------------------------------------------ build context
@dataclass
class BuildContext:
    """What a layer module gets: grid, catalogue, downloads, folders, the country mask."""

    country: Any
    grid: Grid
    catalog: Catalog
    downloader: Any
    staging: Path
    work: Path
    mask: np.ndarray | None = None
    prune: bool = False
    rebuild: bool = False
    shared: dict[str, Any] = field(default_factory=dict)
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def settings(self) -> dict[str, Any]:
        return self.catalog.settings

    @property
    def pad(self) -> float:
        return float(self.settings.get("pad_deg", 1.0))

    def spec(self, lid: str) -> LayerSpec:
        return self.catalog.layers[lid]

    def sidecar(self, lid: str) -> Path:
        return self.staging / f"{lid}.layer.json"

    def done(self, lid: str) -> bool:
        """True when ``lid`` is already built in the staging folder (resumed run)."""
        sc = self.sidecar(lid)
        if self.rebuild or not sc.exists():
            return False
        entry = json.loads(sc.read_text(encoding="utf-8"))
        if entry.get("status") != "built":
            return False
        if not (self.staging / entry["file"]).exists():
            return False
        self.entries[lid] = entry
        return True

    def emit(self, lid: str, array: np.ndarray, inputs: Iterable[dict[str, Any]] = (), notes: str = "",
             extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Write ``<lid>.tif`` (COG) and its sidecar; return the manifest entry."""
        spec = self.spec(lid)
        if array.shape != self.grid.shape:
            raise GeodataError(f"{lid}: array shape {array.shape} is not the grid shape {self.grid.shape}")
        arr = array.astype(spec.dtype, copy=False)
        out = self.staging / f"{lid}.tif"
        write_cog(out, arr, self.grid, spec.dtype, spec.nodata, spec.categorical)
        entry = {**self.catalog.layer_meta(lid), "status": "built", "file": out.name,
                 "file_sha256": sha256_file(out), "data_sha256": data_sha256(arr), "bytes": out.stat().st_size,
                 "built_utc": utc_now(), "inputs": _dedupe_inputs(inputs), "notes": notes,
                 "stats": array_stats(arr, spec, self.mask)}
        if extra:
            entry.update(extra)
        self.sidecar(lid).write_text(json.dumps(entry, indent=2, default=str) + "\n", encoding="utf-8")
        self.entries[lid] = entry
        logger.info("  wrote %s (%.1f MB)", out.name, entry["bytes"] / 1e6)
        return entry

    def mark(self, lid: str, status: str, reason: str, inputs: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
        """Record a layer that was not built (``pending``, ``failed``, ``optional-missing``)."""
        entry = {**self.catalog.layer_meta(lid), "status": status, "file": None, "reason": reason,
                 "inputs": _dedupe_inputs(inputs), "built_utc": utc_now()}
        self.sidecar(lid).write_text(json.dumps(entry, indent=2, default=str) + "\n", encoding="utf-8")
        self.entries[lid] = entry
        return entry

    def staged_array(self, lid: str) -> np.ndarray:
        """Read back a layer already written in this run (e.g. the belt mask, PET for aridity)."""
        return read_band(self.staging / f"{lid}.tif")[0]


MAX_LISTED_INPUTS = 24


def _dedupe_inputs(inputs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unique inputs; a source with more than 24 files is summarised (count, bytes, hash of hashes)."""
    seen: dict[str, dict[str, Any]] = {}
    for i in inputs:
        if not i:
            continue
        key = f"{i.get('source')}|{i.get('file') or i.get('url') or i.get('sha256_of_files')}"
        seen.setdefault(key, i)
    by_source: dict[str, list[dict[str, Any]]] = {}
    for i in seen.values():
        by_source.setdefault(str(i.get("source")), []).append(i)
    out: list[dict[str, Any]] = []
    for source, items in by_source.items():
        if len(items) <= MAX_LISTED_INPUTS:
            out.extend(items)
            continue
        h = hashlib.sha256("".join(sorted(str(i.get("sha256")) for i in items)).encode()).hexdigest()
        files = sorted(str(i.get("file")) for i in items)
        out.append({"source": source, "files": len(items), "first": files[0], "last": files[-1],
                    "bytes": sum(int(i.get("bytes") or 0) for i in items), "sha256_of_files": h,
                    "downloaded_utc": max((str(i.get("downloaded_utc") or "") for i in items), default=None)})
    return out


def array_stats(arr: np.ndarray, spec: LayerSpec, mask: np.ndarray | None) -> dict[str, Any]:
    """Summary statistics over the country mask (or the whole grid): valid share, range, quantiles, classes."""
    inside = mask if mask is not None and mask.shape == arr.shape else np.ones(arr.shape, bool)
    nd = nodata_mask(arr, spec.nodata)
    vals = arr[inside & ~nd]
    n_in = int(inside.sum())
    out: dict[str, Any] = {"cells_in_mask": n_in, "valid_in_mask": int(vals.size),
                           "nodata_share_in_mask": round(1 - vals.size / n_in, 6) if n_in else None}
    if vals.size == 0:
        return out
    if spec.categorical:
        codes, counts = np.unique(vals, return_counts=True)
        out["classes"] = {str(int(c)): int(n) for c, n in zip(codes, counts)}
    else:
        v = vals.astype("float64")
        q = np.percentile(v, [1, 5, 25, 50, 75, 95, 99])
        out.update(min=float(v.min()), max=float(v.max()), mean=float(v.mean()), sd=float(v.std()),
                   quantiles={str(p): float(x) for p, x in zip((1, 5, 25, 50, 75, 95, 99), q)})
    return out
