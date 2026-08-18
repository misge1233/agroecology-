#!/usr/bin/env python3
"""
get_temp.py  —  Feature 2 of 10: Mean annual temperature.

Run ONCE on a machine with internet. It:
  1. downloads WorldClim 2.1 monthly mean temperature (30s, ~1 km),
  2. averages the 12 months -> mean annual temperature (degC),
  3. clips to Ethiopia and aligns to the stack grid (layers/aez_belt.tif),
  4. writes layers/temp_mean_annual.tif.

Setup:  pip install rasterio requests numpy
Run:    python get_temp.py
Verify: python extract_features.py --lat 9.03 --lon 38.74
"""
import os, zipfile, glob, numpy as np, requests, rasterio
from rasterio.warp import reproject, Resampling

BASE   = os.path.dirname(os.path.abspath(__file__))
RAW    = os.path.join(BASE, "raw"); os.makedirs(RAW, exist_ok=True)
LAYERS = os.path.join(BASE, "layers")
REF    = os.path.join(LAYERS, "aez_belt.tif")
URL    = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_30s_tavg.zip"

def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1e6:
        print("  cached", os.path.basename(dest)); return dest
    print("  downloading", url)
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for c in r.iter_content(1 << 20):
                f.write(c)
    return dest

def main():
    if not os.path.exists(REF):
        raise SystemExit("Missing layers/aez_belt.tif (the grid reference).")
    z = download(URL, os.path.join(RAW, "wc2.1_30s_tavg.zip"))
    zipfile.ZipFile(z).extractall(RAW)
    months = sorted(glob.glob(os.path.join(RAW, "wc2.1_30s_tavg_*.tif")))
    if len(months) != 12:
        raise SystemExit("Expected 12 monthly files, found %d" % len(months))

    # average the 12 monthly means -> mean annual temperature
    acc, n = None, 0
    with rasterio.open(months[0]) as s0:
        src_nodata = s0.nodata
    for m in months:
        with rasterio.open(m) as s:
            a = s.read(1).astype("float32")
            if src_nodata is not None:
                a[a == src_nodata] = np.nan
            acc = a if acc is None else acc + a
            n += 1
    mean_t = acc / n
    tmp = os.path.join(RAW, "temp_mean_global.tif")
    with rasterio.open(months[0]) as s0:
        prof = s0.profile
    prof.update(dtype="float32", nodata=np.nan, compress="lzw")
    with rasterio.open(tmp, "w", **prof) as d:
        d.write(mean_t, 1)

    with rasterio.open(REF) as ref:
        g = dict(crs=ref.crs, transform=ref.transform, width=ref.width, height=ref.height)
    dst = np.full((g["height"], g["width"]), -9999.0, dtype="float32")
    with rasterio.open(tmp) as src:
        reproject(source=rasterio.band(src, 1), destination=dst,
                  src_transform=src.transform, src_crs=src.crs, src_nodata=np.nan,
                  dst_transform=g["transform"], dst_crs=g["crs"], dst_nodata=-9999.0,
                  resampling=Resampling.bilinear)
    out = os.path.join(LAYERS, "temp_mean_annual.tif")
    prof = dict(driver="GTiff", height=g["height"], width=g["width"], count=1,
                dtype="float32", crs=g["crs"], transform=g["transform"],
                nodata=-9999.0, compress="lzw", tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(out, "w", **prof) as d:
        d.write(dst, 1)
    v = dst[dst > -9998]
    print("  wrote layers/temp_mean_annual.tif")
    print("  temperature range (degC): %.1f - %.1f, mean %.1f" % (v.min(), v.max(), v.mean()))
    print("Verify: python extract_features.py --lat 9.03 --lon 38.74")

if __name__ == "__main__":
    main()
