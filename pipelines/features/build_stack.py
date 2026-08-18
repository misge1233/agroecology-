#!/usr/bin/env python3
r"""
build_stack.py  —  Acquire the CSA core feature layers and align them to the
common grid defined by layers/aez_belt.tif.

WHY THIS RUNS ON YOUR MACHINE, NOT IN THE ASSISTANT SANDBOX
-----------------------------------------------------------
The assistant's sandbox has no network route to the data portals (CHIRPS,
WorldClim, SoilGrids, Copernicus DEM, ESA WorldCover). The AEZ belt band was
already built there (layers/aez_belt.tif) from your local shapefile. Run this
script on a machine with internet + GDAL/rasterio to fetch and align the rest.

Every output is warped to EXACTLY the same grid, CRS, extent and resolution as
aez_belt.tif, so all bands line up cell-for-cell.

Setup:
    pip install rasterio requests numpy
    # GDAL command-line tools recommended (gdalwarp) but not required.

Run:
    python build_stack.py --all
    python build_stack.py --layer soil          # just one group
    python build_stack.py --list                # show layers + status

Some sources need a manual download (portal / login / very large tiling) — those
are marked MANUAL below with the exact URL and the filename to drop in ./raw/.
"""
import argparse, os, sys, glob

BASE   = os.path.dirname(os.path.abspath(__file__))
RAW    = os.path.join(BASE, "raw")
LAYERS = os.path.join(BASE, "layers")
REF    = os.path.join(LAYERS, "aez_belt.tif")     # grid reference band
os.makedirs(RAW, exist_ok=True)
os.makedirs(LAYERS, exist_ok=True)

# ---------------------------------------------------------------- grid helpers
def ref_grid():
    import rasterio
    with rasterio.open(REF) as s:
        return dict(crs=s.crs, transform=s.transform, width=s.width,
                    height=s.height, bounds=s.bounds)

def align_to_grid(src_path, dst_path, resampling="bilinear", dtype=None,
                  src_nodata=None, dst_nodata=-9999):
    """Reproject/clip/resample any raster onto the reference grid (pure rasterio)."""
    import numpy as np, rasterio
    from rasterio.warp import reproject, Resampling
    g = ref_grid()
    rs = getattr(Resampling, resampling)
    with rasterio.open(src_path) as src:
        out_dtype = dtype or ("float32" if src.dtypes[0].startswith("float") else src.dtypes[0])
        dst = np.full((g["height"], g["width"]),
                      dst_nodata if dst_nodata is not None else 0,
                      dtype=out_dtype)
        reproject(
            source=rasterio.band(src, 1), destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            src_nodata=src_nodata if src_nodata is not None else src.nodata,
            dst_transform=g["transform"], dst_crs=g["crs"],
            dst_nodata=dst_nodata, resampling=rs)
        prof = dict(driver="GTiff", height=g["height"], width=g["width"], count=1,
                    dtype=out_dtype, crs=g["crs"], transform=g["transform"],
                    nodata=dst_nodata, compress="lzw", tiled=True)
    with rasterio.open(dst_path, "w", **prof) as d:
        d.write(dst, 1)
    print(f"  -> {os.path.basename(dst_path)}  [{resampling}]")

def download(url, dest):
    if os.path.exists(dest):
        print(f"  cached {os.path.basename(dest)}"); return dest
    import requests
    print(f"  downloading {url}")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest

# ---------------------------------------------------------------- CLIMATE
# WorldClim v2.1 30s (~1 km) bioclim normals 1970-2000 (single zip, all 19 vars).
#   BIO1  = mean annual temperature (x1, degC)
#   BIO12 = annual precipitation (mm)
#   BIO15 = precipitation seasonality (CV, %)
# CHIRPS is the preferred, Ethiopia-tuned precip source; see chirps_annual_mean().
WORLDCLIM_BIO = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_30s_bio.zip"

def build_climate():
    import zipfile
    z = download(WORLDCLIM_BIO, os.path.join(RAW, "wc2.1_30s_bio.zip"))
    zf = zipfile.ZipFile(z)
    def member(bio): return [m for m in zf.namelist() if m.endswith(f"bio_{bio}.tif")][0]
    for bio, out, rs in [(1, "temp_mean_annual.tif", "bilinear"),
                         (12, "precip_annual.tif", "bilinear"),
                         (15, "precip_seasonality.tif", "bilinear")]:
        m = member(bio); raw = os.path.join(RAW, os.path.basename(m))
        if not os.path.exists(raw):
            zf.extract(m, RAW); os.replace(os.path.join(RAW, m), raw)
        align_to_grid(raw, os.path.join(LAYERS, out), resampling=rs, dtype="float32")

def chirps_annual_mean(years=range(1991, 2021)):
    """OPTIONAL better precip: mean of CHIRPS annual totals (~5 km, Ethiopia-tuned).
       Downloads 30 global annual GeoTIFFs and averages them."""
    import numpy as np, rasterio, gzip, shutil
    base = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_annual/tifs/"
    acc = None
    for y in years:
        gz = download(base + f"chirps-v2.0.{y}.tif.gz", os.path.join(RAW, f"chirps.{y}.tif.gz"))
        tif = gz[:-3]
        if not os.path.exists(tif):
            with gzip.open(gz) as fi, open(tif, "wb") as fo: shutil.copyfileobj(fi, fo)
        with rasterio.open(tif) as s:
            a = s.read(1).astype("float32"); a[a < 0] = np.nan
            acc = a if acc is None else acc + a
            prof = s.profile
    mean = acc / len(list(years))
    tmp = os.path.join(RAW, "chirps_annual_mean.tif")
    prof.update(dtype="float32", nodata=np.nan)
    with rasterio.open(tmp, "w", **prof) as d: d.write(mean, 1)
    align_to_grid(tmp, os.path.join(LAYERS, "precip_annual.tif"),
                  resampling="bilinear", dtype="float32")

# LGP — FAO GAEZ v4. MANUAL: portal export.
#   https://gaez.fao.org/  ->  Theme 3 (Agro-climatic resources) -> Length of Growing Period
#   Download the LGP GeoTIFF, save as raw/gaez_lgp.tif
def build_lgp():
    raw = os.path.join(RAW, "gaez_lgp.tif")
    if not os.path.exists(raw):
        print("  MANUAL: download GAEZ v4 LGP GeoTIFF -> raw/gaez_lgp.tif  (https://gaez.fao.org/)")
        return
    align_to_grid(raw, os.path.join(LAYERS, "lgp_days.tif"), resampling="bilinear", dtype="float32")

# ---------------------------------------------------------------- TERRAIN
# Copernicus GLO-30 DEM, public AWS, no auth, 1x1 deg COG tiles.
def build_terrain():
    import numpy as np, rasterio
    from rasterio.merge import merge
    tiles = []
    for lat in range(3, 15):          # Ethiopia lat band
        for lon in range(32, 49):     # Ethiopia lon band
            ns, ew = ("N%02d" % lat), ("E%03d" % lon)
            name = f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"
            url = f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"
            dest = os.path.join(RAW, name + ".tif")
            try:
                download(url, dest); tiles.append(dest)
            except Exception:
                pass   # many tiles are ocean/empty -> skip
    if not tiles:
        print("  no DEM tiles retrieved"); return
    srcs = [rasterio.open(t) for t in tiles]
    mos, tr = merge(srcs)
    prof = srcs[0].profile; prof.update(height=mos.shape[1], width=mos.shape[2], transform=tr)
    dem_raw = os.path.join(RAW, "dem_mosaic.tif")
    with rasterio.open(dem_raw, "w", **prof) as d: d.write(mos)
    for s in srcs: s.close()
    # elevation
    align_to_grid(dem_raw, os.path.join(LAYERS, "elevation.tif"), resampling="bilinear", dtype="float32")
    # slope (percent) via gdaldem if available, else numpy gradient
    slope_raw = os.path.join(RAW, "slope.tif")
    if os.system(f'gdaldem slope "{dem_raw}" "{slope_raw}" -p -s 111120 > /dev/null 2>&1') == 0:
        align_to_grid(slope_raw, os.path.join(LAYERS, "slope.tif"), resampling="bilinear", dtype="float32")
    else:
        print("  gdaldem not found; compute slope from elevation.tif separately")

# ---------------------------------------------------------------- SOIL
# SoilGrids v2 global VRTs (Homolosine). gdalwarp clips+reprojects to grid in one call.
SOILGRIDS = {
    "soil_clay.tif":  "https://files.isric.org/soilgrids/latest/data/clay/clay_0-5cm_mean.vrt",
    "soil_ph.tif":    "https://files.isric.org/soilgrids/latest/data/phh2o/phh2o_0-5cm_mean.vrt",
    "soil_soc.tif":   "https://files.isric.org/soilgrids/latest/data/soc/soc_0-5cm_mean.vrt",
}
def build_soil():
    g = ref_grid(); b = g["bounds"]
    for out, vrt in SOILGRIDS.items():
        dst = os.path.join(LAYERS, out)
        cmd = (f'gdalwarp -t_srs EPSG:4326 -te {b.left} {b.bottom} {b.right} {b.top} '
               f'-ts {g["width"]} {g["height"]} -r bilinear -overwrite '
               f'-of GTiff -co COMPRESS=LZW "/vsicurl/{vrt}" "{dst}"')
        print(f"  {out}: {cmd}")
        if os.system(cmd) != 0:
            print(f"  gdalwarp failed for {out}; ensure GDAL CLI + network. "
                  f"Alternative: ISRIC WCS or manual download of the Ethiopia window.")

# ---------------------------------------------------------------- LAND COVER
# ESA WorldCover 10m, public AWS, 3x3 deg tiles. Aggregated to grid by majority (mode).
def build_landcover(year=2021, version="v200"):
    import rasterio
    from rasterio.merge import merge
    tiles = []
    for lat in range(3, 15, 3):
        for lon in range(33, 48, 3):
            t = f"ESA_WorldCover_10m_{year}_{version}_N%02dE%03d_Map.tif" % (lat, lon)
            url = f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/{version}/{year}/map/{t}"
            dest = os.path.join(RAW, t)
            try:
                download(url, dest); tiles.append(dest)
            except Exception:
                pass
    if not tiles:
        print("  no WorldCover tiles retrieved"); return
    srcs = [rasterio.open(t) for t in tiles]
    mos, tr = merge(srcs)
    prof = srcs[0].profile; prof.update(height=mos.shape[1], width=mos.shape[2], transform=tr)
    lc_raw = os.path.join(RAW, "worldcover_mosaic.tif")
    with rasterio.open(lc_raw, "w", **prof) as d: d.write(mos)
    for s in srcs: s.close()
    align_to_grid(lc_raw, os.path.join(LAYERS, "land_cover.tif"),
                  resampling="mode", dtype="int16", dst_nodata=0)   # categorical -> mode

# ---------------------------------------------------------------- driver
GROUPS = {
    "climate":   build_climate,
    "lgp":       build_lgp,
    "terrain":   build_terrain,
    "soil":      build_soil,
    "landcover": build_landcover,
}
def status():
    want = ["aez_belt", "precip_annual", "temp_mean_annual", "precip_seasonality",
            "lgp_days", "elevation", "slope", "soil_clay", "soil_ph", "soil_soc", "land_cover"]
    print("Layer status (layers/*.tif):")
    for w in want:
        ok = os.path.exists(os.path.join(LAYERS, w + ".tif"))
        print(f"  [{'x' if ok else ' '}] {w}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--layer", choices=list(GROUPS))
    ap.add_argument("--chirps", action="store_true", help="use CHIRPS instead of WorldClim for precip")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list: return status()
    if a.all:
        for name, fn in GROUPS.items():
            print(f"\n=== {name} ==="); fn()
        if a.chirps: print("\n=== chirps precip ==="); chirps_annual_mean()
    elif a.layer:
        GROUPS[a.layer]()
        if a.layer == "climate" and a.chirps: chirps_annual_mean()
    else:
        ap.error("use --all, --layer NAME, or --list")
    print("\nDone. Verify with:  python extract_features.py --lat 9.03 --lon 38.74")

if __name__ == "__main__":
    main()
