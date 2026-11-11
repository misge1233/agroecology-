"""WorldClim 2.1 layers: precip_annual, temp_mean_annual, precip_seasonality, lgp_days
(the legacy four) and pet_hargreaves_annual (new, feeds aridity_index).

The algorithms are the ones of ``pipelines/features/get_precip.py``,
``get_temp.py``, ``get_seasonality.py`` and ``get_lgp.py``, moved here as
grid-parameterised functions; those scripts now import them (wrap, never fork).
One change of *mechanics*, not of values: the global monthly GeoTIFFs are clipped
to the padded country box (native pixels, no resampling) before the same sums,
means and warps run, so the 4.3 GB temperature archive need not be unpacked.
"""
from __future__ import annotations

import calendar  # noqa: F401  (kept from get_lgp.py, documents the day counts)
import hashlib
import logging
import zipfile
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

from ..core import BuildContext, clip_to_bounds
from ..grid import Grid

logger = logging.getLogger("geodata.worldclim")

GROUP = "climate_worldclim"
LAYERS = ("precip_annual", "temp_mean_annual", "precip_seasonality", "lgp_days", "pet_hargreaves_annual")
ND = -9999.0
DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], dtype="float32")
MIDDOY = np.array([15, 45, 74, 105, 135, 162, 198, 228, 258, 288, 318, 344], dtype="float32")


# ------------------------------------------------------------ moved logic (get_precip / get_temp)
def sum_months(months: Sequence[str | Path]) -> tuple[np.ndarray, Any, Any]:
    """Annual total of 12 monthly rasters (get_precip.py): nodata -> NaN, float32 sum."""
    annual = None
    with rasterio.open(months[0]) as s0:
        src_transform, src_crs, src_nodata = s0.transform, s0.crs, s0.nodata
    for m in months:
        with rasterio.open(m) as s:
            a = s.read(1).astype("float32")
            if src_nodata is not None:
                a[a == src_nodata] = np.nan
            annual = a if annual is None else annual + a
    return annual, src_transform, src_crs


def mean_months(months: Sequence[str | Path]) -> tuple[np.ndarray, Any, Any]:
    """Mean of 12 monthly rasters (get_temp.py): nodata -> NaN, float32 mean."""
    acc, n = None, 0
    with rasterio.open(months[0]) as s0:
        src_nodata, src_transform, src_crs = s0.nodata, s0.transform, s0.crs
    for m in months:
        with rasterio.open(m) as s:
            a = s.read(1).astype("float32")
            if src_nodata is not None:
                a[a == src_nodata] = np.nan
            acc = a if acc is None else acc + a
            n += 1
    return acc / n, src_transform, src_crs


def to_grid(src: np.ndarray, src_transform: Any, src_crs: Any, grid: Grid, src_nodata: Any = np.nan,
            resampling: Resampling = Resampling.bilinear, dst_nodata: float = ND) -> np.ndarray:
    """Warp an in-memory array onto the grid (the reproject call of get_precip.py / get_temp.py)."""
    dst = np.full(grid.shape, dst_nodata, dtype="float32")
    reproject(source=src, destination=dst, src_transform=src_transform, src_crs=src_crs,
              src_nodata=src_nodata, dst_transform=grid.transform, dst_crs=grid.crs,
              dst_nodata=dst_nodata, resampling=resampling)
    return dst


# ------------------------------------------------------------ moved logic (get_seasonality / get_lgp)
def align_stack(files: Sequence[str | Path], grid: Grid) -> np.ndarray:
    """Every monthly raster warped bilinear onto the grid, NaN outside (get_lgp.py / get_seasonality.py)."""
    out = np.full((len(files), grid.nrows, grid.ncols), np.nan, dtype="float32")
    for i, f in enumerate(files):
        with rasterio.open(f) as src:
            tmp = np.full(grid.shape, np.nan, dtype="float32")
            reproject(source=rasterio.band(src, 1), destination=tmp,
                      src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                      dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=np.nan,
                      resampling=Resampling.bilinear)
            out[i] = tmp
        logger.info("    aligned %2d/%d", i + 1, len(files))
    return out


def seasonality_cv(aligned: np.ndarray) -> np.ndarray:
    """CV% = 100 x population SD / mean over the 12 aligned months (get_seasonality.py)."""
    mean = np.nanmean(aligned, axis=0)
    std = np.nanstd(aligned, axis=0)  # population std (ddof=0), like BIO15
    with np.errstate(divide="ignore", invalid="ignore"):
        cv = np.where(mean > 0, 100.0 * std / mean, ND).astype("float32")
    return np.where(np.isnan(cv), ND, cv).astype("float32")


def daylength_hours(lat_deg: np.ndarray) -> np.ndarray:
    """N (hours) per month for each latitude row -> shape (12, H) (get_lgp.py)."""
    lat = np.radians(lat_deg)
    N = np.zeros((12, lat.size), dtype="float32")
    for m in range(12):
        decl = np.radians(23.45 * np.sin(np.radians(360.0 * (284 + MIDDOY[m]) / 365.0)))
        x = -np.tan(lat) * np.tan(decl)
        x = np.clip(x, -1.0, 1.0)
        ws = np.arccos(x)
        N[m] = (24.0 / np.pi) * ws
    return N


def thornthwaite_pet(tavg: np.ndarray, N_by_row: np.ndarray, H: int, W: int) -> np.ndarray:
    """Thornthwaite PET (12,H,W) mm/month from monthly mean T (get_lgp.py)."""
    T = np.where(np.isnan(tavg), 0.0, tavg)
    Tpos = np.clip(T, 0, None)
    I = np.sum((Tpos / 5.0) ** 1.514, axis=0)  # noqa: E741  heat index (H,W)
    a = (6.75e-7 * I**3) - (7.71e-5 * I**2) + (1.792e-2 * I) + 0.49239
    pet = np.zeros((12, H, W), dtype="float32")
    Isafe = np.where(I <= 0, np.nan, I)
    for m in range(12):
        Tm = T[m]
        base = np.zeros((H, W), dtype="float32")
        mid = (Tm > 0) & (Tm <= 26.5)
        base[mid] = 16.0 * (10.0 * Tm[mid] / Isafe[mid]) ** a[mid]
        hot = Tm > 26.5
        base[hot] = -415.85 + 32.24 * Tm[hot] - 0.43 * Tm[hot] ** 2
        base = np.nan_to_num(base, nan=0.0, posinf=0.0, neginf=0.0)
        corr = (N_by_row[m][:, None] / 12.0) * (DAYS[m] / 30.0)
        pet[m] = np.clip(base, 0, None) * corr
    return pet


def compute_lgp(precip: np.ndarray, tavg: np.ndarray, lat_deg: np.ndarray) -> np.ndarray:
    """Water-balance LGP in days (get_lgp.py)."""
    H, W = precip.shape[1], precip.shape[2]
    N = daylength_hours(lat_deg)
    pet = thornthwaite_pet(tavg, N, H, W)
    growing = (precip >= 0.5 * pet) & (tavg > 5.0)
    lgp = np.tensordot(DAYS, growing.astype("float32"), axes=([0], [0]))
    lgp = np.clip(lgp, 0, 365).astype("float32")
    valid = ~np.isnan(precip[0]) & ~np.isnan(tavg[0])
    return np.where(valid, lgp, ND).astype("float32")


def lgp_lat_rows(grid: Grid) -> np.ndarray:
    """Row-centre latitudes exactly as get_lgp.py computes them from the reference transform."""
    t = grid.transform
    return t.f + (np.arange(grid.nrows) + 0.5) * (-t.a)


# ------------------------------------------------------------ new: Hargreaves PET
def extraterrestrial_radiation(lat_deg: np.ndarray) -> np.ndarray:
    """FAO-56 eq. 21 Ra (MJ m-2 day-1) at mid-month for each latitude -> (12, H)."""
    phi = np.radians(lat_deg.astype("float64"))
    out = np.zeros((12, phi.size), dtype="float64")
    for m in range(12):
        J = float(MIDDOY[m])
        dr = 1 + 0.033 * np.cos(2 * np.pi * J / 365)
        delta = 0.409 * np.sin(2 * np.pi * J / 365 - 1.39)
        ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
        out[m] = (24 * 60 / np.pi) * 0.0820 * dr * (ws * np.sin(phi) * np.sin(delta)
                                                     + np.cos(phi) * np.cos(delta) * np.sin(ws))
    return out


def hargreaves_month(tmean: np.ndarray, dtr: np.ndarray, ra_row: np.ndarray, days: float) -> np.ndarray:
    """Hargreaves-Samani PET (mm/month): 0.0023 x 0.408 Ra (T + 17.8) sqrt(Tmax - Tmin) x days."""
    return (0.0023 * 0.408 * ra_row[:, None] * (tmean + 17.8) * np.sqrt(np.clip(dtr, 0, None)) * days).astype("float32")


# ------------------------------------------------------------ inputs
def _member_names(zip_path: Path, var: str) -> list[str]:
    with zipfile.ZipFile(zip_path) as zf:
        names = sorted(n for n in zf.namelist() if n.endswith(".tif") and f"_{var}_" in Path(n).name)
    if len(names) != 12:
        raise ValueError(f"{zip_path.name}: expected 12 monthly {var} files, found {len(names)}")
    return names


def monthly_clips(ctx: BuildContext, source: str, var: str) -> tuple[list[Path], dict[str, Any]]:
    """The 12 monthly rasters of a WorldClim archive, clipped to the padded country box (cached)."""
    spec = ctx.catalog.source(source)
    url = spec["url"]
    zname = url.rsplit("/", 1)[-1]
    bounds = ctx.grid.padded_bounds(ctx.pad)
    tag = hashlib.sha1(repr(tuple(round(b, 6) for b in bounds)).encode()).hexdigest()[:8]
    clip_dir = ctx.downloader.folder(source) / "clips"
    expected = [clip_dir / f"{var}_{m:02d}__{ctx.country.code}_{tag}.tif" for m in range(1, 13)]
    rec = ctx.downloader.records(source).get(zname, {})
    if all(p.exists() for p in expected) and rec.get("sha256") and rec.get("clips_tag") == tag:
        return expected, ctx.downloader.input_entry(source, zname)
    zpath = ctx.downloader.fetch(source, url, zname, manual=bool(spec.get("manual")), approx_mb=spec.get("approx_mb"))
    members = _member_names(zpath, var)
    tmpdir = ctx.work / "worldclim_extract"
    tmpdir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as zf:
        for i, (member, dst) in enumerate(zip(members, expected), 1):
            if dst.exists():
                continue
            logger.info("  clipping %s (%d/12)", Path(member).name, i)
            extracted = Path(zf.extract(member, tmpdir))
            clip_to_bounds(str(extracted), bounds, dst)
            extracted.unlink()
    ctx.downloader.record(source, zname, clips_tag=tag, clips=[p.name for p in expected])
    return expected, ctx.downloader.input_entry(source, zname)


def _prune(ctx: BuildContext, source: str) -> None:
    if ctx.prune:
        zname = ctx.catalog.source(source)["url"].rsplit("/", 1)[-1]
        freed = ctx.downloader.prune(source, [zname])
        if freed:
            logger.info("  pruned %s (%.0f MB freed; clips kept)", zname, freed / 1e6)


# ------------------------------------------------------------ build
def build(ctx: BuildContext, wanted: set[str]) -> None:
    """Build the WorldClim layers in ``wanted`` that are not already staged."""
    todo = {lid for lid in wanted if lid in LAYERS and not ctx.done(lid)}
    if not todo:
        return
    g = ctx.grid
    need_prec = todo & {"precip_annual", "precip_seasonality", "lgp_days"}
    need_tavg = todo & {"temp_mean_annual", "lgp_days", "pet_hargreaves_annual"}
    prec_files, prec_in = monthly_clips(ctx, "worldclim_prec_30s", "prec") if need_prec else ([], None)
    tavg_files, tavg_in = monthly_clips(ctx, "worldclim_tavg_30s", "tavg") if need_tavg else ([], None)

    if "precip_annual" in todo:
        logger.info("  precip_annual: summing 12 months")
        annual, tr, crs = sum_months(prec_files)
        ctx.emit("precip_annual", to_grid(annual, tr, crs, g), [prec_in])
        del annual
    if "temp_mean_annual" in todo:
        logger.info("  temp_mean_annual: averaging 12 months")
        mean_t, tr, crs = mean_months(tavg_files)
        ctx.emit("temp_mean_annual", to_grid(mean_t, tr, crs, g), [tavg_in])
        del mean_t

    precip = align_stack(prec_files, g) if todo & {"precip_seasonality", "lgp_days"} else None
    if "precip_seasonality" in todo:
        ctx.emit("precip_seasonality", seasonality_cv(precip), [prec_in])
    tavg = align_stack(tavg_files, g) if todo & {"lgp_days", "pet_hargreaves_annual"} else None
    if "lgp_days" in todo:
        ctx.emit("lgp_days", compute_lgp(precip, tavg, lgp_lat_rows(g)), [prec_in, tavg_in])
    del precip
    if "pet_hargreaves_annual" in todo:
        tmin_files, tmin_in = monthly_clips(ctx, "worldclim_tmin_2.5m", "tmin")
        tmax_files, tmax_in = monthly_clips(ctx, "worldclim_tmax_2.5m", "tmax")
        ra = extraterrestrial_radiation(g.row_lats())
        pet = np.zeros(g.shape, dtype="float32")
        for m in range(12):
            tmn = align_stack([tmin_files[m]], g)[0]
            tmx = align_stack([tmax_files[m]], g)[0]
            pet += hargreaves_month(tavg[m], tmx - tmn, ra[m], float(DAYS[m]))
        pet = np.where(np.isnan(pet), ND, pet).astype("float32")
        ctx.emit("pet_hargreaves_annual", pet, [tavg_in, tmin_in, tmax_in],
                 notes="Tmean from the 30 arc-second normals, Tmax - Tmin from the 2.5 arc-minute normals")
        _prune(ctx, "worldclim_tmin_2.5m")
        _prune(ctx, "worldclim_tmax_2.5m")
    del tavg
    if need_prec:
        _prune(ctx, "worldclim_prec_30s")
    if need_tavg:
        _prune(ctx, "worldclim_tavg_30s")
