#!/usr/bin/env python3
"""
get_seasonality.py  —  Feature (Climate): Precipitation seasonality / CV (WorldClim BIO15).

Precipitation seasonality = coefficient of variation of the 12 monthly rainfall
totals. REUSES the monthly precipitation files already fetched by get_precip.py
(raw/wc2.1_30s_prec_*.tif) -> normally NO new download.

Memory-safe: each monthly raster is resampled onto the ~250 m Ethiopia grid
FIRST, then CV is computed across the 12 small aligned arrays (~2 GB peak),
instead of stacking twelve global rasters (~44 GB).

  CV% = 100 * std(12 months) / mean(12 months)   per grid cell

Setup:  pip install rasterio requests numpy
Run:    python get_seasonality.py
Verify: python extract_features.py --lat 9.03 --lon 38.74
"""
import os, zipfile, glob, numpy as np, requests, rasterio
from rasterio.warp import reproject, Resampling

BASE   = os.path.dirname(os.path.abspath(__file__))
RAW    = os.path.join(BASE, "raw"); os.makedirs(RAW, exist_ok=True)
LAYERS = os.path.join(BASE, "layers")
REF    = os.path.join(LAYERS, "aez_belt.tif")
URL    = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_30s_prec.zip"
ND     = -9999.0

def ensure_months():
    months = sorted(glob.glob(os.path.join(RAW, "wc2.1_30s_prec_*.tif")))
    if len(months) == 12:
        print("  reusing 12 cached monthly precip files (no download)")
        return months
    dest = os.path.join(RAW, "wc2.1_30s_prec.zip")
    if not (os.path.exists(dest) and os.path.getsize(dest) > 1e6):
        print("  downloading", URL)
        with requests.get(URL, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for c in r.iter_content(1 << 20):
                    f.write(c)
    zipfile.ZipFile(dest).extractall(RAW)
    return sorted(glob.glob(os.path.join(RAW, "wc2.1_30s_prec_*.tif")))

def main():
    if not os.path.exists(REF):
        raise SystemExit("Missing layers/aez_belt.tif (the grid reference).")
    months = ensure_months()
    if len(months) != 12:
        raise SystemExit("Expected 12 monthly precip files, found %d" % len(months))

    with rasterio.open(REF) as ref:
        crs, transform, W, H = ref.crs, ref.transform, ref.width, ref.height

    # resample each month to the grid FIRST (small), then stack
    aligned = np.full((12, H, W), np.nan, dtype="float32")
    for i, m in enumerate(months):
        with rasterio.open(m) as src:
            tmp = np.full((H, W), np.nan, dtype="float32")
            reproject(source=rasterio.band(src, 1), destination=tmp,
                      src_transform=src.transform, src_crs=src.crs,
                      src_nodata=src.nodata, dst_transform=transform, dst_crs=crs,
                      dst_nodata=np.nan, resampling=Resampling.bilinear)
            aligned[i] = tmp
        print("  aligned month %2d/12" % (i + 1))

    mean = np.nanmean(aligned, axis=0)
    std  = np.nanstd(aligned, axis=0)            # population std (ddof=0), like BIO15
    with np.errstate(divide="ignore", invalid="ignore"):
        cv = np.where(mean > 0, 100.0 * std / mean, ND).astype("float32")
    cv = np.where(np.isnan(cv), ND, cv).astype("float32")

    out = os.path.join(LAYERS, "precip_seasonality.tif")
    prof = dict(driver="GTiff", height=H, width=W, count=1, dtype="float32",
                crs=crs, transform=transform, nodata=ND, compress="lzw",
                tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(out, "w", **prof) as d:
        d.write(cv, 1)
    v = cv[cv > ND]
    print("  wrote layers/precip_seasonality.tif  CV%% range %.0f - %.0f, median %.0f" %
          (v.min(), v.max(), np.median(v)))
    print("Verify: python extract_features.py --lat 9.03 --lon 38.74")

if __name__ == "__main__":
    main()
