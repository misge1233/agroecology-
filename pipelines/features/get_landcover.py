#!/usr/bin/env python3
"""
get_landcover.py  —  Feature 8 (Land): Land cover class.

Source: ESA WorldCover 2021 v200, 10 m, public AWS S3 (no login). Tiles are
3x3 degree COGs with internal overviews, so mode-resampling to our ~250 m grid
reads a coarse overview (fast) rather than full 10 m data.

Output: layers/land_cover.tif  (categorical class code, aligned to grid).
Class codes: 10 tree, 20 shrub, 30 grassland, 40 cropland, 50 built,
             60 bare/sparse, 70 snow/ice, 80 water, 90 wetland, 95 mangrove, 100 moss.

Setup:  pip install rasterio requests numpy
Run:    python get_landcover.py
Verify: python extract_features.py --lat 9.03 --lon 38.74
"""
import os, math, numpy as np, requests, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
os.environ.setdefault("VSI_CACHE", "TRUE")

BASE   = os.path.dirname(os.path.abspath(__file__))
RAW    = os.path.join(BASE, "raw", "worldcover"); os.makedirs(RAW, exist_ok=True)
LAYERS = os.path.join(BASE, "layers")
REF    = os.path.join(LAYERS, "aez_belt.tif")
ND     = 0
S3     = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"

def tile_name(lat, lon):
    ns = "N%02d" % lat if lat >= 0 else "S%02d" % (-lat)
    ew = "E%03d" % lon if lon >= 0 else "W%03d" % (-lon)
    return "ESA_WorldCover_10m_2021_v200_%s%s_Map" % (ns, ew)

def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return True
    try:
        r = requests.get(url, stream=True, timeout=180)
        if r.status_code != 200:
            return False
        with open(dest, "wb") as f:
            for c in r.iter_content(1 << 20):
                f.write(c)
        return True
    except Exception:
        return False

def main():
    if not os.path.exists(REF):
        raise SystemExit("Missing layers/aez_belt.tif (the grid reference).")
    with rasterio.open(REF) as ref:
        crs, transform, W, H = ref.crs, ref.transform, ref.width, ref.height
        b = ref.bounds

    lat0 = int(math.floor(b.bottom / 3) * 3)
    lat1 = int(math.floor(b.top    / 3) * 3)
    lon0 = int(math.floor(b.left   / 3) * 3)
    lon1 = int(math.floor(b.right  / 3) * 3)
    tiles = [(la, lo) for la in range(lat0, lat1 + 1, 3)
                      for lo in range(lon0, lon1 + 1, 3)]
    print("checking %d WorldCover 3-deg tiles..." % len(tiles))

    out = np.full((H, W), ND, dtype="uint8")
    got = 0
    for la, lo in tiles:
        name = tile_name(la, lo)
        dest = os.path.join(RAW, name + ".tif")
        url = "%s/%s.tif" % (S3, name)
        if not download(url, dest):
            print("  (no tile %s)" % name); continue
        got += 1
        with rasterio.open(dest) as src:
            with WarpedVRT(src, crs=crs, transform=transform, width=W, height=H,
                           resampling=Resampling.mode) as vrt:
                a = vrt.read(1)
        m = a > 0
        out[m] = a[m]
        print("  merged %s (%d/%d)" % (name, got, len(tiles)))

    prof = dict(driver="GTiff", height=H, width=W, count=1, dtype="uint8",
                crs=crs, transform=transform, nodata=ND, compress="lzw",
                tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(os.path.join(LAYERS, "land_cover.tif"), "w", **prof) as d:
        d.write(out, 1)
    vals, counts = np.unique(out[out > 0], return_counts=True)
    print("  wrote layers/land_cover.tif  classes present:",
          dict(zip(vals.tolist(), counts.tolist())))
    print("Verify: python extract_features.py --lat 9.03 --lon 38.74")

if __name__ == "__main__":
    main()
