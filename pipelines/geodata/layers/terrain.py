"""Terrain layers from Copernicus GLO-30 (brief E3 B1 and B2).

Legacy (moved from ``pipelines/features/get_terrain.py``, unchanged in substance):

* ``elevation``: every 1x1 degree tile warped bilinear onto the 250 m grid and
  composited in tile order;
* ``slope``: latitude-aware ``np.gradient`` of that 250 m elevation, percent.

New (B2), from one pass over the same tiles:

1. per tile, at 30 m: the slope (latitude-aware gradient), ``tan b`` and the RUSLE
   S-factor ``(sin b / 0.0896) ** 1.3``; the DEM, ``tan b`` and S are averaged onto a
   3 arc-second (~90 m) grid snapped to the tile seams (``Grid.aligned``);
2. country-wide at 90 m with WhiteboxTools: FillDepressions (flats given a gradient),
   D8Pointer, D8FlowAccumulation (cells x cell area = km2), ExtractStreams;
3. ``flow_accumulation`` (km2), ``twi = ln(a / tan b)``, ``slope_length_factor``
   (Moore and Burch 1986: ``(As/22.13)^0.4 x S``, ``As`` capped at 300 m),
   ``tpi`` (elevation minus the ~1 km window mean) and ``dist_to_stream_m``
   (Euclidean distance to cells with upstream area >= 1 km2);
4. aggregation to 250 m: mean for LS, TPI, TWI; min for distance; max for upstream area.

Why 90 m routing: D8 over Ethiopia at 30 m is 2.3e9 cells (about 9 GB per float
array, several arrays at once); at 90 m it is 2.6e8 cells and fits a 32 GB machine.
Local slope keeps its 30 m resolution through ``tan b`` and S. Recorded in
``docs/decisions/geodata_v2.md``.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

from ..core import BuildContext, GeodataError, LayerUnavailable, cache_root, read_band
from ..grid import Grid
from .climate_worldclim import to_grid

logger = logging.getLogger("geodata.terrain")

GROUP = "terrain"
LEGACY = ("elevation", "slope")
DERIVED = ("slope_length_factor", "tpi", "twi", "flow_accumulation", "dist_to_stream_m")
LAYERS = LEGACY + DERIVED
SOURCE = "glo30_dem"
ND = -9999.0
S3 = "https://copernicus-dem-30m.s3.amazonaws.com"
M_PER_DEG = 111320.0


# ------------------------------------------------------------ moved logic (get_terrain.py)
def tile_name(lat: int, lon: int) -> str:
    """GLO-30 tile name of the 1x1 degree cell with lower-left corner (lat, lon)."""
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    return "Copernicus_DSM_COG_10_%s%02d_00_%s%03d_00_DEM" % (ns, abs(lat), ew, abs(lon))


def tile_url(lat: int, lon: int) -> tuple[str, str]:
    """(name, URL) of a GLO-30 tile (get_terrain.py)."""
    name = tile_name(lat, lon)
    return name, "%s/%s/%s.tif" % (S3, name, name)


def tiles_for(grid: Grid) -> list[tuple[int, int]]:
    """Candidate tiles in the order get_terrain.py visits them (the composite order)."""
    l, b, r, t = grid.bounds
    lat_lo, lat_hi = int(math.floor(b)), int(math.floor(t))
    lon_lo, lon_hi = int(math.floor(l)), int(math.floor(r))
    return [(la, lo) for la in range(lat_lo, lat_hi + 1) for lo in range(lon_lo, lon_hi + 1)]


def warp_tile(dest: str | Path, H: int, W: int, transform: Any, crs: Any) -> np.ndarray:
    """One tile warped bilinear onto the full grid, -9999 outside (get_terrain.py)."""
    tmp = np.full((H, W), ND, dtype="float32")
    with rasterio.open(dest) as src:
        reproject(source=rasterio.band(src, 1), destination=tmp,
                  src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                  dst_transform=transform, dst_crs=crs, dst_nodata=ND,
                  resampling=Resampling.bilinear)
    return tmp


def slope_percent(elev: np.ndarray, transform: Any) -> np.ndarray:
    """Slope in percent, latitude-aware cell size on a geographic grid (get_terrain.py)."""
    H = elev.shape[0]
    res = transform.a
    lat0 = transform.f
    z = np.where(elev > ND, elev, np.nan)
    dzdy, dzdx = np.gradient(z)
    dy_m = res * M_PER_DEG
    lats = lat0 + (np.arange(H) + 0.5) * (-res)
    dx_m = (res * M_PER_DEG * np.cos(np.radians(lats)))[:, None]
    gx = dzdx / dx_m
    gy = dzdy / dy_m
    slope_pct = np.sqrt(gx * gx + gy * gy) * 100.0
    return np.where(np.isnan(slope_pct), ND, slope_pct).astype("float32")


# ------------------------------------------------------------ new: 30 m local terms
def tan_slope(z: np.ndarray, transform: Any) -> np.ndarray:
    """tan(slope) at native resolution (NaN-aware, latitude-aware; rows may have |e| != |a|)."""
    H = z.shape[0]
    resx, resy = abs(transform.a), abs(transform.e)
    lats = transform.f + (np.arange(H) + 0.5) * transform.e
    dzdy, dzdx = np.gradient(z)
    gx = dzdx / (resx * M_PER_DEG * np.cos(np.radians(lats)))[:, None]
    gy = dzdy / (resy * M_PER_DEG)
    return np.sqrt(gx * gx + gy * gy).astype("float32")


def s_factor(tanb: np.ndarray) -> np.ndarray:
    """RUSLE slope-steepness term of Moore and Burch (1986): (sin b / 0.0896) ** 1.3."""
    sinb = tanb / np.sqrt(1.0 + tanb.astype("float64") ** 2)
    return ((sinb / 0.0896) ** 1.3).astype("float32")


def add_to_mosaic(mosaic: np.ndarray, grid: Grid, src: np.ndarray, src_transform: Any, src_crs: Any,
                  resampling: Resampling = Resampling.average) -> None:
    """Warp ``src`` (NaN nodata) into the window of ``mosaic`` it covers; valid cells overwrite."""
    h, w = src.shape
    l, t = src_transform.c, src_transform.f
    r, b = l + w * src_transform.a, t + h * src_transform.e
    win = grid.window_of((l, b, r, t))
    if win is None:
        return
    r0, c0, r1, c1 = win
    sub = np.full((r1 - r0, c1 - c0), np.nan, dtype="float32")
    reproject(source=src, destination=sub, src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
              dst_transform=grid.window_transform(r0, c0), dst_crs=grid.crs, dst_nodata=np.nan,
              resampling=resampling)
    ok = ~np.isnan(sub)
    view = mosaic[r0:r1, c0:c1]
    view[ok] = sub[ok]


# ------------------------------------------------------------ new: 90 m routing products
def cell_geometry(grid: Grid) -> tuple[np.ndarray, np.ndarray, float]:
    """(dx per row in m, cell area per row in km2, dy in m) of a geographic grid."""
    lats = grid.row_lats()
    dy = grid.res * M_PER_DEG
    dx = grid.res * M_PER_DEG * np.cos(np.radians(lats))
    return dx, dx * dy / 1e6, dy


WHITEBOX_PACKAGE = "whitebox==2.3.6"
WHITEBOX_BINARY_URL = "https://www.whiteboxgeo.com/WBT_Windows/WhiteboxTools_win_amd64.zip"
WBT_NODATA = -32768.0
WBT_ROWS_PER_STRIP = 64


def whitebox_exe() -> Path | None:
    """The WhiteboxTools binary, found without importing ``whitebox`` (importing may download it).

    ``WHITEBOX_DIR`` (the folder holding ``whitebox_tools.exe``) wins; otherwise the
    ``WBT`` folder the ``whitebox`` package downloads into, next to the package.
    """
    import importlib.util

    exe = "whitebox_tools.exe" if os.name == "nt" else "whitebox_tools"
    env = os.environ.get("WHITEBOX_DIR")
    cands = [Path(env) / exe, Path(env) / "WBT" / exe] if env else []
    spec = importlib.util.find_spec("whitebox")
    if spec and spec.origin:
        pkg = Path(spec.origin).parent
        cands += [pkg / "WBT" / exe, pkg / exe]
    return next((c for c in cands if c.exists()), None)


def whitebox_tools(allow_download: bool = True) -> Any:
    """The ``whitebox`` package object (binary location and version), or :class:`LayerUnavailable`.

    Tools are not run through it (see :func:`run_wbt`); it locates the binary and reports its version.
    """
    import importlib.util

    if importlib.util.find_spec("whitebox") is None:
        raise LayerUnavailable(f"WhiteboxTools is not installed (python -m pip install {WHITEBOX_PACKAGE})")
    exe = whitebox_exe()
    if exe is None and not allow_download:
        raise LayerUnavailable("the WhiteboxTools binary is missing (--skip-download): download "
                               f"{WHITEBOX_BINARY_URL} and unzip it so that WBT/whitebox_tools.exe sits in the "
                               "whitebox package folder, or set WHITEBOX_DIR to the folder holding it")
    from whitebox import WhiteboxTools  # first use downloads the binary when it is missing

    wbt = WhiteboxTools()
    exe = exe or whitebox_exe()
    if exe is None:
        raise LayerUnavailable(f"the WhiteboxTools binary could not be downloaded: get {WHITEBOX_BINARY_URL} "
                               "and unzip it into the whitebox package folder (WBT/whitebox_tools.exe), "
                               "or set WHITEBOX_DIR")
    wbt.set_whitebox_dir(str(exe.parent))
    wbt.set_verbose_mode(False)
    if hasattr(wbt, "set_compress_rasters"):
        wbt.set_compress_rasters(True)
    return wbt


def whitebox_tool_record(wbt: Any = None) -> dict[str, Any]:
    """Name and versions of the flow-routing tool, for the manifest."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        pkg = version("whitebox")
    except PackageNotFoundError:
        pkg = None
    binary = None
    if wbt is not None:
        try:
            binary = str(wbt.version()).strip().splitlines()[0]
        except Exception:  # noqa: BLE001
            binary = None
    return {"name": "WhiteboxTools", "python_package": f"whitebox {pkg}" if pkg else None, "binary": binary,
            "licence": "MIT", "url": "https://www.whiteboxgeo.com/", "retries": [dict(r) for r in WBT_RETRIES]}


class WhiteboxError(RuntimeError):
    """A WhiteboxTools run that did not produce its output (exit code, error line or missing file)."""

    def __init__(self, tool: str, problems: list[str], output: str):
        self.tool, self.problems, self.output = tool, problems, output
        tail = "\n".join(output.strip().splitlines()[-8:])
        super().__init__(f"WhiteboxTools {tool}: {'; '.join(problems)}" + (f"\n{tail}" if tail else ""))


def _wbt_exe_of(wbt: Any) -> Path:
    """The binary behind a ``WhiteboxTools`` object (its ``exe_path``), else :func:`whitebox_exe`."""
    d, n = getattr(wbt, "exe_path", None), getattr(wbt, "exe_name", None)
    if d and n and (Path(d) / n).exists():
        return Path(d) / n
    exe = whitebox_exe()
    if exe is None:
        raise LayerUnavailable(f"the WhiteboxTools binary is missing: get {WHITEBOX_BINARY_URL} or set WHITEBOX_DIR")
    return exe


_WBT_ERROR = re.compile(r"\b(error|panicked|thread 'main'|could not|cannot|failed|unsupported|not found)\b", re.I)

#: The one WhiteboxTools failure that is retried (E4 Part 0): the binary panics while
#: creating its output file ("thread 'main' panicked ... Error unwrapping 'output'"),
#: seen in 2 of 15 E3 unit runs when the work folder was the user temp folder, where
#: Windows Defender and the indexer lock fresh files. Exactly one retry, logged as a
#: warning and recorded in :data:`WBT_RETRIES` (-> the manifest). Any other error fails
#: at once, as before.
WBT_RETRY_PANIC = "Error unwrapping 'output'"
WBT_RETRIES: list[dict[str, Any]] = []


def _wbt_attempt(exe: Path, args: list[str], workdir: Path, outputs: tuple[str, ...]) -> tuple[str, list[str]]:
    """One subprocess run; returns the captured output and the list of problems found."""
    for name in outputs:
        (workdir / name).unlink(missing_ok=True)
    proc = subprocess.run(args, capture_output=True, text=True, errors="replace", cwd=str(exe.parent))
    out = (proc.stdout or "") + (proc.stderr or "")
    problems: list[str] = []
    if proc.returncode != 0:
        problems.append(f"exit code {proc.returncode}")
    bad = [ln.strip() for ln in out.splitlines() if _WBT_ERROR.search(ln) and not ln.lower().startswith("progress")]
    if bad:
        problems.append(bad[0][:300])
    for name in outputs:
        p = workdir / name
        if not p.exists() or p.stat().st_size == 0:
            problems.append(f"output {name} missing")
            continue
        try:
            with rasterio.open(p) as s:
                s.read(1, window=rasterio.windows.Window(0, 0, 1, 1))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"output {name} unreadable: {exc}")
    return out, problems


def run_wbt(wbt: Any, tool: str, workdir: Path, outputs: tuple[str, ...], **params: Any) -> str:
    """Run one WhiteboxTools tool as a subprocess and return its captured output.

    The ``whitebox`` package's ``run_tool`` returns 0 whenever the process starts and
    shows the binary's error lines only in verbose mode, so a failure is invisible
    (the E3 national run: FillDepressions "finished" in 9 s with no output file).
    Here stdout and stderr are captured and the run fails with :class:`WhiteboxError`
    when the exit code is not 0, an error line appears in the output, or any expected
    output is missing, empty or unreadable. The one known transient panic
    (:data:`WBT_RETRY_PANIC`) is retried exactly once (E4 Part 0).
    """
    exe = _wbt_exe_of(wbt)
    args = [str(exe), f"--run={tool}", f"--wd={workdir}"]
    for k, v in params.items():
        if v is True:
            args.append(f"--{k}")
        elif v is not False and v is not None:
            args.append(f"--{k}={v}")
    args += ["-v=true", "--compress_rasters=True"]
    t0 = time.time()
    out, problems = _wbt_attempt(exe, args, workdir, outputs)
    if problems and WBT_RETRY_PANIC in out:
        record = {"tool": tool, "workdir": str(workdir), "panic": WBT_RETRY_PANIC,
                  "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        WBT_RETRIES.append(record)
        logger.warning("    %s panicked (%s); retrying once", tool, WBT_RETRY_PANIC)
        out, problems = _wbt_attempt(exe, args, workdir, outputs)
        record["recovered"] = not problems
    if problems:
        raise WhiteboxError(tool, problems, out)
    logger.info("    %s done (%.0f s): %s", tool, time.time() - t0, ", ".join(outputs))
    return out


def _write_plain(path: Path, arr: np.ndarray, grid: Grid, nodata: float, rows: int = 512) -> None:
    """Striped, uncompressed, classic (non-Big) float32 GeoTIFF, written in row blocks.

    WhiteboxTools reads its own GeoTIFF subset: strips (not tiles), no floating-point
    predictor, no BigTIFF. Written block by block so the NaN-to-nodata copy never holds
    a second full array.
    """
    if grid.nrows * grid.ncols * 4 >= 4 * 1024 ** 3:
        raise GeodataError(f"{path.name}: {grid.nrows} x {grid.ncols} float32 exceeds the classic TIFF 4 GB "
                           "limit that WhiteboxTools can read; raise terrain.flow_arcsec in sources.yaml")
    prof = dict(driver="GTiff", height=grid.nrows, width=grid.ncols, count=1, dtype="float32", crs=grid.crs,
                transform=grid.transform, nodata=nodata, tiled=False, blockysize=WBT_ROWS_PER_STRIP, BIGTIFF="NO")
    with rasterio.open(path, "w", **prof) as d:
        for r0 in range(0, grid.nrows, rows):
            blk = arr[r0:r0 + rows]
            win = rasterio.windows.Window(0, r0, grid.ncols, blk.shape[0])
            d.write(np.where(np.isnan(blk), nodata, blk).astype("float32", copy=False), 1, window=win)


def _read_nan(path: Path) -> np.ndarray:
    with rasterio.open(path) as s:
        a = s.read(1).astype("float32", copy=False)
        if s.nodata is not None and not np.isnan(s.nodata):
            a[a == s.nodata] = np.nan
    return a


def wbt_work_root() -> Path:
    """Folder for WhiteboxTools scratch files: ``<cache>/_work/wbt`` (E4 Part 0).

    Not the user temp folder: Windows Defender and the search indexer lock fresh files
    there, which is where the E3 flake came from; the cache folder is excluded from
    indexing (see ``pipelines/geodata/README.md``).
    """
    root = cache_root() / "_work" / "wbt"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _workdir(workdir: Path | None) -> tuple[Path, bool]:
    import tempfile

    if workdir is None:
        return Path(tempfile.mkdtemp(prefix="wbt_", dir=str(wbt_work_root()))), True
    Path(workdir).mkdir(parents=True, exist_ok=True)
    return Path(workdir), False


def _cleanup(wd: Path, own: bool, names: tuple[str, ...]) -> None:
    import shutil

    if own:
        shutil.rmtree(wd, ignore_errors=True)
    else:
        for n in names:
            (wd / n).unlink(missing_ok=True)


def d8_upstream_area(dem: np.ndarray, grid: Grid, workdir: Path | None = None, wbt: Any = None,
                     allow_download: bool = True) -> np.ndarray:
    """Upstream area (km2, own cell included) by D8 with WhiteboxTools; NaN outside the DEM.

    FillDepressions (Wang and Liu; ``fix_flats`` gives flats a small gradient), D8Pointer
    and D8FlowAccumulation in cells; cells x the area of a cell in their own row gives
    km2 (a catchment spans a few degrees of latitude, so the area error is under 3%).
    Raises :class:`WhiteboxError` with the binary's own message when a step fails.
    """
    wbt = wbt or whitebox_tools(allow_download)
    wd, own = _workdir(workdir)
    valid = ~np.isnan(dem)
    try:
        _write_plain(wd / "dem.tif", dem, grid, WBT_NODATA)
        run_wbt(wbt, "FillDepressions", wd, ("filled.tif",), dem="dem.tif", output="filled.tif", fix_flats=True)
        run_wbt(wbt, "D8Pointer", wd, ("pointer.tif",), dem="filled.tif", output="pointer.tif")
        run_wbt(wbt, "D8FlowAccumulation", wd, ("acc_cells.tif",), input="pointer.tif", output="acc_cells.tif",
                out_type="cells", pntr=True)
        cells = _read_nan(wd / "acc_cells.tif")
    finally:
        _cleanup(wd, own, ("dem.tif", "filled.tif", "pointer.tif", "acc_cells.tif"))
    _, area, _ = cell_geometry(grid)
    cells *= area.astype("float32")[:, None]  # in place, float32: no 2 GB float64 temporary
    cells[~valid] = np.nan
    return cells


def extract_streams(acc_km2: np.ndarray, grid: Grid, threshold_km2: float, workdir: Path | None = None,
                    wbt: Any = None, allow_download: bool = True) -> np.ndarray:
    """Stream cells (upstream area >= ``threshold_km2``) with WhiteboxTools ExtractStreams."""
    wbt = wbt or whitebox_tools(allow_download)
    wd, own = _workdir(workdir)
    try:
        _write_plain(wd / "acc_km2.tif", acc_km2, grid, WBT_NODATA)
        run_wbt(wbt, "ExtractStreams", wd, ("streams.tif",), flow_accum="acc_km2.tif", output="streams.tif",
                threshold=threshold_km2, zero_background=True)
        with rasterio.open(wd / "streams.tif") as s:
            st = s.read(1)
            nd = s.nodata
        streams = (st > 0) if nd is None or np.isnan(nd) else ((st > 0) & (st != nd))
    finally:
        _cleanup(wd, own, ("acc_km2.tif", "streams.tif"))
    return streams & ~np.isnan(acc_km2)


def specific_catchment_area(acc_km2: np.ndarray, grid: Grid) -> np.ndarray:
    """a = upstream area / flow width (m); flow width = sqrt(dx dy) of the cell."""
    dx, _, dy = cell_geometry(grid)
    width = np.sqrt(dx * dy)[:, None]
    return (acc_km2 * 1e6 / width).astype("float32")


def twi(sca: np.ndarray, tanb: np.ndarray, min_tan: float = 0.001) -> np.ndarray:
    """Topographic wetness index ln(a / tan b) (tan b floored at ``min_tan``)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(sca / np.maximum(tanb, min_tan)).astype("float32")


def ls_factor(sca: np.ndarray, s: np.ndarray, max_sca: float = 300.0) -> np.ndarray:
    """LS = (min(a, max_sca) / 22.13) ** 0.4 x S (Moore and Burch 1986)."""
    return ((np.minimum(sca, max_sca) / 22.13) ** 0.4 * s).astype("float32")


def tpi(dem: np.ndarray, window: int) -> np.ndarray:
    """Elevation minus the NaN-aware mean of the ``window x window`` neighbourhood."""
    from scipy.ndimage import uniform_filter

    valid = ~np.isnan(dem)
    z = np.where(valid, dem, 0.0).astype("float32")
    num = uniform_filter(z, size=window, mode="constant")
    den = uniform_filter(valid.astype("float32"), size=window, mode="constant")
    with np.errstate(divide="ignore", invalid="ignore"):
        out = dem - num / den
    out[~valid] = np.nan
    return out.astype("float32")


def distance_to_streams(streams: np.ndarray, grid: Grid, valid: np.ndarray) -> np.ndarray:
    """Euclidean distance (m) to the nearest stream cell; NaN outside ``valid``.

    The E-W cell size is taken at the grid's middle latitude (error under 2.5% across
    Ethiopia, recorded in geodata_v2.md).
    """
    from scipy.ndimage import distance_transform_edt

    if not streams.any():
        return np.where(valid, np.nan, np.nan).astype("float32")
    mid = 0.5 * (grid.ymin + grid.ymax)
    dy = grid.res * M_PER_DEG
    dx = grid.res * M_PER_DEG * math.cos(math.radians(mid))
    d = distance_transform_edt(~streams, sampling=(dy, dx)).astype("float32")
    d[~valid] = np.nan
    return d


def window_cells(window_m: float, grid: Grid) -> int:
    """Odd window size (cells) closest to ``window_m`` on ``grid``."""
    n = int(round(window_m / (grid.res * M_PER_DEG)))
    return n if n % 2 == 1 else n + 1


# ------------------------------------------------------------ stage 1: the tile pass
def _stage1_paths(work: Path) -> dict[str, Path]:
    d = work / "terrain"
    d.mkdir(parents=True, exist_ok=True)
    return {k: d / f"{k}.tif" for k in ("elev250", "dem90", "tanb90", "s90")} | {"meta": d / "stage1.json"}


def stage1_cached(work: Path) -> bool:
    """True when a complete tile pass (250 m elevation and the 90 m mosaics) is in ``work/terrain``."""
    d = work / "terrain"
    return all((d / f"{k}.tif").exists() for k in ("elev250", "dem90", "tanb90", "s90")) and (d / "stage1.json").exists()


def _write(path: Path, arr: np.ndarray, grid: Grid, nodata: Any) -> None:
    prof = grid.profile("float32", nodata)
    prof.update(compress="deflate", BIGTIFF="IF_SAFER")
    tmp = path.with_suffix(".part.tif")
    with rasterio.open(tmp, "w", **prof) as d:
        d.write(arr.astype("float32", copy=False), 1)
    os.replace(tmp, path)


def tile_pass(ctx: BuildContext, flow_grid: Grid, derived: bool) -> tuple[dict[str, Path], list[dict[str, Any]]]:
    """Visit every tile once: legacy 250 m elevation, and (``derived``) the 90 m mosaics."""
    src = ctx.catalog.source(SOURCE)
    paths = _stage1_paths(ctx.work)
    tiles = tiles_for(ctx.grid)
    sea = float(ctx.settings.get("terrain", {}).get("sea_value", 0.0))
    meta_key = {"grid": ctx.grid.hash(), "flow_grid": flow_grid.hash(), "tiles": len(tiles), "sea": sea,
                "derived": derived}
    if paths["meta"].exists() and all(paths[k].exists() for k in ("elev250",) + (("dem90", "tanb90", "s90") if derived else ())):
        meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
        if {k: meta.get(k) for k in meta_key} == meta_key:
            logger.info("  terrain: reusing the tile-pass intermediates in %s", paths["meta"].parent)
            return paths, meta["inputs"]
    g = ctx.grid
    elev = np.full(g.shape, ND, dtype="float32")
    mos = {k: np.full(flow_grid.shape, np.nan, dtype="float32") for k in ("dem90", "tanb90", "s90")} if derived else {}
    inputs: list[dict[str, Any]] = []
    got, bad, names = 0, [], []
    for i, (la, lo) in enumerate(tiles, 1):
        name = tile_name(la, lo)
        url = src["url_template"].format(ns="N" if la >= 0 else "S", lat=abs(la), ew="E" if lo >= 0 else "W",
                                         lon=abs(lo))
        fname = name + ".tif"
        p = ctx.downloader.fetch(SOURCE, url, fname, absent_ok=True)
        if p is None:
            continue
        try:
            tmp = warp_tile(p, g.nrows, g.ncols, g.transform, g.crs)
        except Exception:  # noqa: BLE001  corrupt tile: refetch once (get_terrain.py)
            p.unlink(missing_ok=True)
            p = ctx.downloader.fetch(SOURCE, url, fname, absent_ok=True)
            try:
                tmp = warp_tile(p, g.nrows, g.ncols, g.transform, g.crs)
            except Exception:  # noqa: BLE001
                bad.append(name)
                continue
        got += 1
        names.append(fname)
        inputs.append(ctx.downloader.input_entry(SOURCE, fname))
        m = tmp > ND
        elev[m] = tmp[m]
        del tmp
        if derived:
            with rasterio.open(p) as s:
                z = s.read(1).astype("float32")
                if s.nodata is not None:
                    z[z == s.nodata] = np.nan
                z[z == sea] = np.nan
                tr, crs = s.transform, s.crs
            tb = tan_slope(z, tr)
            add_to_mosaic(mos["dem90"], flow_grid, z, tr, crs)
            add_to_mosaic(mos["tanb90"], flow_grid, tb, tr, crs)
            add_to_mosaic(mos["s90"], flow_grid, s_factor(tb), tr, crs)
            del z, tb
        if ctx.prune:
            ctx.downloader.prune(SOURCE, [fname])
        if i % 20 == 0:
            logger.info("  %d/%d tiles checked, %d merged", i, len(tiles), got)
    if bad:
        logger.warning("  unreadable tiles: %s", ", ".join(bad))
    logger.info("  merged %d DEM tiles", got)
    _write(paths["elev250"], elev, g, ND)
    for k, arr in mos.items():
        _write(paths[k], arr, flow_grid, np.nan)
    meta = {**meta_key, "inputs": inputs, "unreadable": bad, "n_tiles_merged": got}
    paths["meta"].write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return paths, inputs


# ------------------------------------------------------------ build
def build(ctx: BuildContext, wanted: set[str]) -> None:
    """Build the terrain layers in ``wanted`` that are not already staged."""
    todo = {lid for lid in wanted if lid in LAYERS and not ctx.done(lid)}
    if not todo:
        return
    tset = ctx.settings.get("terrain", {})
    flow_grid = ctx.grid.aligned(float(tset.get("flow_arcsec", 3)) / 3600.0)
    derived = bool(todo & set(DERIVED))
    paths, inputs = tile_pass(ctx, flow_grid, derived)
    summary = _summarise(inputs)
    if todo & set(LEGACY):
        elev = read_band(paths["elev250"])[0]
        if "elevation" in todo:
            ctx.emit("elevation", elev, summary)
        if "slope" in todo:
            ctx.emit("slope", slope_percent(elev, ctx.grid.transform), summary)
        del elev
    if not derived:
        return
    dem = read_band(paths["dem90"])[0]
    valid = ~np.isnan(dem)
    g = ctx.grid
    if "tpi" in todo:  # before routing: a routing failure must not take the TPI down with it
        win = window_cells(float(tset.get("tpi_window_m", 1000)), flow_grid)
        t = tpi(dem, win)
        ctx.emit("tpi", to_grid(t, flow_grid.transform, flow_grid.crs, g, resampling=Resampling.average), summary,
                 notes=f"{win} x {win} window at {flow_grid.res * 3600:.0f} arc-seconds")
        del t
    routing = todo & set(DERIVED) - {"tpi"}
    if not routing:
        return
    logger.info("  flow routing on %d x %d cells (WhiteboxTools)", flow_grid.nrows, flow_grid.ncols)
    wdir = ctx.work / "terrain" / "wbt"
    tool: dict[str, Any] = {"name": "WhiteboxTools"}
    wbt = None
    try:
        wbt = whitebox_tools(allow_download=not ctx.downloader.offline)
        tool = whitebox_tool_record(wbt)
        acc = d8_upstream_area(dem, flow_grid, workdir=wdir, wbt=wbt)
    except (LayerUnavailable, WhiteboxError) as exc:
        logger.error("  flow routing failed: %s", exc)
        for lid in routing:
            ctx.mark(lid, "failed", str(exc), summary)
        return
    finally:
        del dem
    tool = {**tool, "retries": [dict(r) for r in WBT_RETRIES]}  # E4: retried panics go into the manifest
    tool_txt = f"{tool.get('name')} {tool.get('binary') or ''} ({tool.get('python_package') or 'whitebox'})"
    note = (f"30 m slope terms, {flow_grid.res * 3600:.0f} arc-second D8 routing with {tool_txt}: FillDepressions "
            f"(fix_flats), D8Pointer, D8FlowAccumulation; sea cells (GLO-30 == {tset.get('sea_value', 0.0)}) "
            "excluded from routing")
    extra = {"tool": tool}
    if "flow_accumulation" in todo:
        ctx.emit("flow_accumulation", to_grid(acc, flow_grid.transform, flow_grid.crs, g, resampling=Resampling.max),
                 summary, notes=note, extra=extra)
    sca = specific_catchment_area(acc, flow_grid)
    if todo & {"twi", "slope_length_factor"}:
        tanb = read_band(paths["tanb90"])[0]
        if "twi" in todo:
            ctx.emit("twi", to_grid(twi(sca, tanb, float(tset.get("min_tan_slope", 0.001))), flow_grid.transform,
                                    flow_grid.crs, g, resampling=Resampling.average), summary, notes=note,
                     extra=extra)
        del tanb
        if "slope_length_factor" in todo:
            s = read_band(paths["s90"])[0]
            ls = ls_factor(sca, s, float(tset.get("ls_max_sca_m", 300)))
            ctx.emit("slope_length_factor", to_grid(ls, flow_grid.transform, flow_grid.crs, g,
                                                    resampling=Resampling.average), summary, notes=note,
                     extra=extra)
            del s, ls
    del sca
    if "dist_to_stream_m" in todo:
        thr = float(tset.get("stream_threshold_km2", 1.0))
        try:
            streams = extract_streams(acc, flow_grid, thr, workdir=wdir, wbt=wbt)
        except WhiteboxError as exc:
            logger.error("  stream extraction failed: %s", exc)
            ctx.mark("dist_to_stream_m", "failed", str(exc), summary)
            return
        del acc
        d = distance_to_streams(streams, flow_grid, valid)
        ctx.emit("dist_to_stream_m", to_grid(d, flow_grid.transform, flow_grid.crs, g, resampling=Resampling.min),
                 summary, notes=f"streams: WhiteboxTools ExtractStreams at upstream area >= {thr} km2; Euclidean "
                                f"distance in metres (scipy); {note}", extra=extra)


def _summarise(inputs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One manifest input for the whole tile set (count, total bytes, hash of the tile hashes)."""
    import hashlib

    inputs = list(inputs)
    h = hashlib.sha256("".join(sorted(str(i.get("sha256")) for i in inputs)).encode()).hexdigest()
    return [{"source": SOURCE, "files": len(inputs), "bytes": sum(int(i.get("bytes") or 0) for i in inputs),
             "sha256_of_files": h, "url_template": f"{S3}/<tile>/<tile>.tif",
             "downloaded_utc": max((str(i.get("downloaded_utc") or "") for i in inputs), default=None)}]
