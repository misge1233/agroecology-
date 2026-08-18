#!/usr/bin/env python3
"""
get_soil.py  —  Features 5,6,7 (Soil): clay content, pH, organic carbon.

Source: SoilGrids v2.0 (ISRIC), 0-5 cm, ~250 m, streamed over the network from
the global cloud-optimized VRTs. No local GDAL command-line tools required -
uses rasterio's WarpedVRT to reproject/clip straight onto the stack grid.

Outputs (aligned to layers/aez_belt.tif):
  layers/soil_clay.tif   clay content, %      (SoilGrids g/kg / 10)
  layers/soil_ph.tif     pH in H2O            (SoilGrids pH*10 / 10)
  layers/soil_soc.tif    soil organic carbon, g/kg (SoilGrids dg/kg / 10)

Setup:  pip install rasterio requests numpy
Run:    python get_soil.py
Verify: python extract_features.py --lat 9.03 --lon 38.74
"""
import os, numpy as np, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling

# help GDAL stream remote CO/VRT tiles efficiently
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.vrt")
os.environ.setdefault("VSI_CACHE", "TRUE")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")

BASE   = os.path.dirname(os.path.abspath(__file__))
LAYERS = os.path.join(BASE, "layers")
REF    = os.path.join(LAYERS, "aez_belt.tif")
ND     = -9999.0
SG     = "https://files.isric.org/soilgrids/latest/data/%s/%s_0-5cm_mean.vrt"

# out name -> (property, scale to conventional units, unit label)
PROPS = {
    "soil_clay.tif": ("clay",  0.1, "percent"),
    "soil_ph.tif":   ("phh2o", 0.1, "pH"),
    "soil_soc.tif":  ("soc",   0.1, "g/kg"),
}

def main():
    if not os.path.exists(REF):
        raise SystemExit("Missing layers/aez_belt.tif (the grid reference).")
    with rasterio.open(REF) as ref:
        crs, transform, W, H = ref.crs, ref.transform, ref.width, ref.height
    oprof = dict(driver="GTiff", height=H, width=W, count=1, dtype="float32",
                 crs=crs, transform=transform, nodata=ND, compress="lzw",
                 tiled=True, blockxsize=256, blockysize=256)

    for out, (prop, scale, unit) in PROPS.items():
        url = SG % (prop, prop)
        print("  fetching %s from SoilGrids (this can take a few minutes)..." % prop)
        with rasterio.open("/vsicurl/" + url) as src:
            with WarpedVRT(src, crs=crs, transform=transform, width=W, height=H,
                           resampling=Resampling.bilinear) as vrt:
                a = vrt.read(1).astype("float32")
                src_nd = src.nodata
        valid = np.ones(a.shape, bool) if src_nd is None else (a != src_nd)
        out_arr = np.where(valid, a * scale, ND).astype("float32")
        with rasterio.open(os.path.join(LAYERS, out), "w", **oprof) as d:
            d.write(out_arr, 1)
        v = out_arr[out_arr > ND]
        print("    wrote layers/%s  (%s)  range %.1f - %.1f, median %.1f" %
              (out, unit, v.min(), v.max(), np.median(v)))
    print("Verify: python extract_features.py --lat 9.03 --lon 38.74")

if __name__ == "__main__":
    main()
