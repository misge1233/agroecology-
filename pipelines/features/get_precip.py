#!/usr/bin/env python3
"""
get_precip.py  —  Feature 1 of 10: Annual precipitation.

Run this ONCE on a machine with internet (your PC, or Colab). It:
  1. downloads WorldClim 2.1 monthly precipitation (30s, ~1 km),
  2. sums the 12 months -> annual precipitation (mm),
  3. clips to Ethiopia and aligns to the stack grid (layers/aez_belt.tif),
  4. writes layers/precip_annual.tif.

Afterwards, extract_features.py includes it automatically.

Setup:  pip install rasterio requests numpy
Run:    python get_precip.py
Higher-fidelity alternative (Ethiopia-tuned, 30-yr): python build_stack.py --layer climate --chirps
"""
import zipfile, glob, numpy as np, requests, rasterio
import os, sys
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
from pipelines.geodata.grid import grid_from_raster  # noqa: E402
from pipelines.geodata.layers import climate_worldclim as wc  # noqa: E402  (logic moved there; wrap, never fork)

BASE   = os.path.dirname(os.path.abspath(__file__))
RAW    = os.path.join(BASE, "raw"); os.makedirs(RAW, exist_ok=True)
LAYERS = os.path.join(BASE, "layers")
REF    = os.path.join(LAYERS, "aez_belt.tif")
URL    = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_30s_prec.zip"

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
    z = download(URL, os.path.join(RAW, "wc2.1_30s_prec.zip"))
    zf = zipfile.ZipFile(z); zf.extractall(RAW)
    months = sorted(glob.glob(os.path.join(RAW, "wc2.1_30s_prec_*.tif")))
    if len(months) != 12:
        raise SystemExit("Expected 12 monthly files, found %d" % len(months))

    # sum months -> annual total, then align to the stack grid (pipelines/geodata/layers/climate_worldclim.py)
    annual, src_transform, src_crs = wc.sum_months(months)
    g = grid_from_raster(REF)
    dst = wc.to_grid(annual, src_transform, src_crs, g)
    g = dict(crs=g.crs, transform=g.transform, width=g.ncols, height=g.nrows)
    out = os.path.join(LAYERS, "precip_annual.tif")
    prof = dict(driver="GTiff", height=g["height"], width=g["width"], count=1,
                dtype="float32", crs=g["crs"], transform=g["transform"],
                nodata=-9999.0, compress="lzw", tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(out, "w", **prof) as d:
        d.write(dst, 1)
    valid = dst[dst > -9998]
    print("  wrote layers/precip_annual.tif")
    print("  precip range (mm): %.0f - %.0f, mean %.0f" % (valid.min(), valid.max(), valid.mean()))
    print("Verify: python extract_features.py --lat 9.03 --lon 38.74")

if __name__ == "__main__":
    main()
