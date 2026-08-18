#!/usr/bin/env python3
"""
get_terrain.py  —  Features 3 & 4 (Terrain): Elevation + Slope.

Run ONCE on a machine with internet. It:
  1. downloads Copernicus GLO-30 DEM tiles (~30 m, public AWS, no login),
  2. reprojects/composites them onto the stack grid  -> layers/elevation.tif (m),
  3. computes slope (latitude-aware)                 -> layers/slope.tif (percent).

Memory-safe: each tile is warped straight onto the 250 m grid and composited,
so no giant full-resolution mosaic is held in RAM.

Setup:  pip install rasterio requests numpy
Run:    python get_terrain.py
Verify: python extract_features.py --lat 9.03 --lon 38.74
"""
import os, math, time, numpy as np, requests, rasterio
from rasterio.warp import reproject, Resampling

BASE   = os.path.dirname(os.path.abspath(__file__))
RAW    = os.path.join(BASE, "raw", "dem"); os.makedirs(RAW, exist_ok=True)
LAYERS = os.path.join(BASE, "layers")
REF    = os.path.join(LAYERS, "aez_belt.tif")
ND     = -9999.0
S3     = "https://copernicus-dem-30m.s3.amazonaws.com"

def tile_url(lat, lon):
    name = "Copernicus_DSM_COG_10_N%02d_00_E%03d_00_DEM" % (lat, lon)
    return name, "%s/%s/%s.tif" % (S3, name, name)

def download(url, dest, retries=4):
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return True
    for attempt in range(retries):
        try:
            r = requests.get(url, stream=True, timeout=120)
            if r.status_code == 404:
                return False                      # tile genuinely absent (ocean)
            if r.status_code != 200:
                time.sleep(2 * (attempt + 1)); continue
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                for c in r.iter_content(1 << 20):
                    f.write(c)
            os.replace(tmp, dest)
            return True
        except Exception:
            time.sleep(2 * (attempt + 1))         # transient error -> retry
    return False


def warp_tile(dest, H, W, transform, crs):
    tmp = np.full((H, W), ND, dtype="float32")
    with rasterio.open(dest) as src:
        reproject(source=rasterio.band(src, 1), destination=tmp,
                  src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                  dst_transform=transform, dst_crs=crs, dst_nodata=ND,
                  resampling=Resampling.bilinear)
    return tmp


def main():
    if not os.path.exists(REF):
        raise SystemExit("Missing layers/aez_belt.tif (the grid reference).")
    with rasterio.open(REF) as ref:
        crs, transform = ref.crs, ref.transform
        W, H = ref.width, ref.height
        b = ref.bounds

    lat_lo, lat_hi = int(math.floor(b.bottom)), int(math.floor(b.top))
    lon_lo, lon_hi = int(math.floor(b.left)),   int(math.floor(b.right))
    tiles = [(la, lo) for la in range(lat_lo, lat_hi + 1)
                      for lo in range(lon_lo, lon_hi + 1)]
    print("checking %d candidate DEM tiles..." % len(tiles))

    elev = np.full((H, W), ND, dtype="float32")
    got, bad = 0, []
    for i, (la, lo) in enumerate(tiles, 1):
        name, url = tile_url(la, lo)
        dest = os.path.join(RAW, name + ".tif")
        if not download(url, dest):
            continue                      # ocean / nonexistent tile
        try:
            tmp = warp_tile(dest, H, W, transform, crs)
        except Exception:                 # corrupt cached tile -> delete, refetch, retry once
            try:
                os.remove(dest)
            except OSError:
                pass
            if download(url, dest):
                try:
                    tmp = warp_tile(dest, H, W, transform, crs)
                except Exception:
                    bad.append(name); continue
            else:
                bad.append(name); continue
        got += 1
        m = tmp > ND
        elev[m] = tmp[m]
        if i % 20 == 0:
            print("  %d/%d checked, %d tiles merged" % (i, len(tiles), got))
    if bad:
        print("  re-fetched/repaired; still unreadable: %d (%s)" %
              (len(bad), ", ".join(bad[:5]) + (" ..." if len(bad) > 5 else "")))
    print("merged %d DEM tiles" % got)

    prof = dict(driver="GTiff", height=H, width=W, count=1, dtype="float32",
                crs=crs, transform=transform, nodata=ND, compress="lzw",
                tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(os.path.join(LAYERS, "elevation.tif"), "w", **prof) as d:
        d.write(elev, 1)
    ev = elev[elev > ND]
    print("  wrote layers/elevation.tif  range %.0f - %.0f m" % (ev.min(), ev.max()))

    # slope (percent), latitude-aware cell size on the geographic grid
    res = transform.a                                   # degrees per pixel
    lat0 = transform.f                                  # top latitude
    z = np.where(elev > ND, elev, np.nan)
    dzdy, dzdx = np.gradient(z)                          # per-pixel rise
    dy_m = res * 111320.0
    lats = lat0 + (np.arange(H) + 0.5) * (-res)
    dx_m = (res * 111320.0 * np.cos(np.radians(lats)))[:, None]
    gx = dzdx / dx_m
    gy = dzdy / dy_m
    slope_pct = np.sqrt(gx * gx + gy * gy) * 100.0
    slope_pct = np.where(np.isnan(slope_pct), ND, slope_pct).astype("float32")
    with rasterio.open(os.path.join(LAYERS, "slope.tif"), "w", **prof) as d:
        d.write(slope_pct, 1)
    sv = slope_pct[slope_pct > ND]
    print("  wrote layers/slope.tif  range %.1f - %.1f %%  (median %.1f)" %
          (sv.min(), sv.max(), np.median(sv)))
    print("Verify: python extract_features.py --lat 9.03 --lon 38.74")

if __name__ == "__main__":
    main()
