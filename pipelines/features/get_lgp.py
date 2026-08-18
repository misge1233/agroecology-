#!/usr/bin/env python3
"""
get_lgp.py  —  Feature 4 (Climate): Length of Growing Period (LGP), days.

FAO-style water-balance LGP, DERIVED from data already on disk:
  monthly rainfall (raw/wc2.1_30s_prec_*.tif, from get_precip.py) and
  monthly mean temperature (raw/wc2.1_30s_tavg_*.tif, from get_temp.py).
No new download in the normal case.

Method (standard agro-climatic LGP):
  * PET per month via Thornthwaite (from monthly mean T + latitude daylength),
  * a month is "growing" when rainfall >= 0.5 * PET AND mean temp > 5 degC,
  * LGP = sum of days in the growing months (capped at 365).

Output: layers/lgp_days.tif  (aligned to the stack grid).

If you prefer the official FAO GAEZ v4 LGP instead, download it from
https://gaez.fao.org/ (Theme 3, Length of Growing Period), save as
raw/gaez_lgp.tif, and run:  python build_stack.py --layer lgp

Setup:  pip install rasterio requests numpy
Run:    python get_lgp.py
Verify: python extract_features.py --lat 9.03 --lon 38.74
"""
import os, glob, zipfile, calendar, numpy as np, requests, rasterio
from rasterio.warp import reproject, Resampling

BASE   = os.path.dirname(os.path.abspath(__file__))
RAW    = os.path.join(BASE, "raw"); os.makedirs(RAW, exist_ok=True)
LAYERS = os.path.join(BASE, "layers")
REF    = os.path.join(LAYERS, "aez_belt.tif")
ND     = -9999.0
WC     = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_30s_%s.zip"
DAYS   = np.array([31,28,31,30,31,30,31,31,30,31,30,31], dtype="float32")
MIDDOY = np.array([15,45,74,105,135,162,198,228,258,288,318,344], dtype="float32")

def ensure(var):
    files = sorted(glob.glob(os.path.join(RAW, "wc2.1_30s_%s_*.tif" % var)))
    if len(files) == 12:
        print("  reusing 12 cached monthly %s files" % var); return files
    dest = os.path.join(RAW, "wc2.1_30s_%s.zip" % var)
    if not (os.path.exists(dest) and os.path.getsize(dest) > 1e6):
        print("  downloading", WC % var)
        with requests.get(WC % var, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for c in r.iter_content(1 << 20):
                    f.write(c)
    zipfile.ZipFile(dest).extractall(RAW)
    return sorted(glob.glob(os.path.join(RAW, "wc2.1_30s_%s_*.tif" % var)))

def align_stack(files, crs, transform, W, H):
    out = np.full((12, H, W), np.nan, dtype="float32")
    for i, f in enumerate(files):
        with rasterio.open(f) as src:
            tmp = np.full((H, W), np.nan, dtype="float32")
            reproject(source=rasterio.band(src, 1), destination=tmp,
                      src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                      dst_transform=transform, dst_crs=crs, dst_nodata=np.nan,
                      resampling=Resampling.bilinear)
            out[i] = tmp
        print("    aligned %2d/12" % (i + 1))
    return out

def daylength_hours(lat_deg):
    """N (hours) per month for each latitude row -> shape (12, H)."""
    lat = np.radians(lat_deg)                       # (H,)
    N = np.zeros((12, lat.size), dtype="float32")
    for m in range(12):
        decl = np.radians(23.45 * np.sin(np.radians(360.0 * (284 + MIDDOY[m]) / 365.0)))
        x = -np.tan(lat) * np.tan(decl)
        x = np.clip(x, -1.0, 1.0)
        ws = np.arccos(x)                           # sunset hour angle
        N[m] = (24.0 / np.pi) * ws
    return N

def thornthwaite_pet(tavg, N_by_row, H, W):
    """tavg: (12,H,W) monthly mean T. Returns PET (12,H,W) mm/month."""
    T = np.where(np.isnan(tavg), 0.0, tavg)
    Tpos = np.clip(T, 0, None)
    I = np.sum((Tpos / 5.0) ** 1.514, axis=0)       # heat index (H,W)
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
        corr = (N_by_row[m][:, None] / 12.0) * (DAYS[m] / 30.0)   # (H,1) broadcast
        pet[m] = np.clip(base, 0, None) * corr
    return pet

def compute_lgp(precip, tavg, lat_deg):
    H, W = precip.shape[1], precip.shape[2]
    N = daylength_hours(lat_deg)
    pet = thornthwaite_pet(tavg, N, H, W)
    growing = (precip >= 0.5 * pet) & (tavg > 5.0)          # (12,H,W)
    lgp = np.tensordot(DAYS, growing.astype("float32"), axes=([0], [0]))
    lgp = np.clip(lgp, 0, 365).astype("float32")
    valid = ~np.isnan(precip[0]) & ~np.isnan(tavg[0])
    lgp = np.where(valid, lgp, ND).astype("float32")
    return lgp

def main():
    if not os.path.exists(REF):
        raise SystemExit("Missing layers/aez_belt.tif (the grid reference).")
    with rasterio.open(REF) as ref:
        crs, transform, W, H = ref.crs, ref.transform, ref.width, ref.height
    lat_deg = transform.f + (np.arange(H) + 0.5) * (-transform.a)

    print("  preparing monthly precip..."); pfiles = ensure("prec")
    precip = align_stack(pfiles, crs, transform, W, H)
    print("  preparing monthly temperature..."); tfiles = ensure("tavg")
    tavg = align_stack(tfiles, crs, transform, W, H)

    lgp = compute_lgp(precip, tavg, lat_deg)
    prof = dict(driver="GTiff", height=H, width=W, count=1, dtype="float32",
                crs=crs, transform=transform, nodata=ND, compress="lzw",
                tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(os.path.join(LAYERS, "lgp_days.tif"), "w", **prof) as d:
        d.write(lgp, 1)
    v = lgp[lgp > ND]
    print("  wrote layers/lgp_days.tif  range %.0f - %.0f days, median %.0f" %
          (v.min(), v.max(), np.median(v)))
    print("Verify: python extract_features.py --lat 9.03 --lon 38.74")

if __name__ == "__main__":
    main()
