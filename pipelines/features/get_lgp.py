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
import glob, zipfile, calendar, numpy as np, requests, rasterio
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

# The algorithms live in pipelines/geodata/layers/climate_worldclim.py (moved, not rewritten).
daylength_hours = wc.daylength_hours
thornthwaite_pet = wc.thornthwaite_pet
compute_lgp = wc.compute_lgp


def align_stack(files, crs, transform, W, H):
    """Kept signature; delegates to climate_worldclim.align_stack on the reference grid."""
    return wc.align_stack(files, grid_from_raster(REF))

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
