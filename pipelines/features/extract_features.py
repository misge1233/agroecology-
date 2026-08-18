#!/usr/bin/env python3
"""
Extract CSA feature-stack values for lat/long point(s).

Samples every single-band GeoTIFF in ./layers/ at the coordinate(s) and joins
the AEZ zonal attribute table (aez_attributes.csv). land_cover is returned as a
readable label. If a point lands on a masked / nodata cell (SoilGrids masks
cities and lakes), it falls back to the NEAREST valid cell within ~20 km.

Usage:
    python extract_features.py --lat 9.03 --lon 38.74
    python extract_features.py --lat 9.03 --lon 38.74 --clean
    python extract_features.py --csv points.csv --clean --out enriched.csv

Requires: rasterio, pandas, numpy
"""
import argparse, csv, glob, os, sys
import numpy as np
import rasterio
from rasterio.windows import Window

BASE      = os.path.dirname(os.path.abspath(__file__))
LAYER_DIR = os.path.join(BASE, "layers")
ATTRS     = os.path.join(BASE, "aez_attributes.csv")
MAX_R     = 80   # nearest-valid search radius in pixels (~20 km at 250 m)

FEATURES10 = ["precip_annual", "temp_mean_annual", "precip_seasonality", "lgp_days",
              "elevation", "slope", "soil_clay", "soil_ph", "soil_soc", "land_cover"]

# ESA WorldCover class codes -> labels
LANDCOVER = {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
             50: "Built-up", 60: "Bare/sparse vegetation", 70: "Snow and ice",
             80: "Permanent water", 90: "Herbaceous wetland", 95: "Mangroves",
             100: "Moss and lichen"}


def _isnd(v, nd):
    return v is None or (isinstance(v, float) and np.isnan(v)) or (nd is not None and v == nd)


def load_aez_attributes():
    m = {}
    if os.path.exists(ATTRS):
        with open(ATTRS) as f:
            for row in csv.DictReader(f):
                code = int(row["aez_code"]); rec = {}
                for k, v in row.items():
                    if k == "aez_code":
                        continue
                    try:
                        rec[k] = float(v) if ("." in v or v.lstrip("-").isdigit()) else v
                    except ValueError:
                        rec[k] = v
                m[code] = rec
    return m


def _nearest_valid(src, lon, lat, nd):
    try:
        row, col = src.index(lon, lat)
    except Exception:
        return None
    H, W = src.height, src.width
    if not (0 <= row < H and 0 <= col < W):
        return None
    r0, r1 = max(0, row - MAX_R), min(H, row + MAX_R + 1)
    c0, c1 = max(0, col - MAX_R), min(W, col + MAX_R + 1)
    block = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0))
    if nd is not None:
        valid = (block != nd) & ~np.isnan(block) if block.dtype.kind == "f" else (block != nd)
    else:
        valid = ~np.isnan(block) if block.dtype.kind == "f" else np.ones(block.shape, bool)
    if not valid.any():
        return None
    rr, cc = np.where(valid)
    d2 = (rr - (row - r0)) ** 2 + (cc - (col - c0)) ** 2
    return block[rr[int(np.argmin(d2))], cc[int(np.argmin(d2))]].item()


def sample_points(points):
    layers = sorted(p for p in glob.glob(os.path.join(LAYER_DIR, "*.tif"))
                    if not os.path.basename(p).startswith("stack_"))
    if not layers:
        sys.exit("No .tif layers found in %s" % LAYER_DIR)
    aez_attrs = load_aez_attributes()
    rows = [dict(lon=lon, lat=lat) for lon, lat in points]
    for path in layers:
        name = os.path.splitext(os.path.basename(path))[0]
        with rasterio.open(path) as src:
            nd = src.nodata
            vals = [v[0] for v in src.sample(points)]
            for i, (r, val) in enumerate(zip(rows, vals)):
                if _isnd(val, nd):
                    val = _nearest_valid(src, points[i][0], points[i][1], nd)
                if name == "aez_belt":
                    if val is not None and int(val) in aez_attrs:
                        r.update(aez_attrs[int(val)])
                        r["aez_name"] = aez_attrs[int(val)]["aez_zone"]
                    else:
                        r["aez_name"] = None
                elif name == "land_cover":
                    r["land_cover"] = None if val is None else LANDCOVER.get(int(val), int(val))
                else:
                    r[name] = None if val is None else (val.item() if hasattr(val, "item") else val)
    return rows


def clean_row(r):
    out = {"aez_name": r.get("aez_name")}
    for f in FEATURES10:
        out[f] = r.get(f)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float); ap.add_argument("--lon", type=float)
    ap.add_argument("--csv"); ap.add_argument("--lat-col", default="lat")
    ap.add_argument("--lon-col", default="lon"); ap.add_argument("--out")
    ap.add_argument("--clean", action="store_true",
                    help="return only AEZ name + the 10 features")
    a = ap.parse_args()

    if a.csv:
        import pandas as pd
        df = pd.read_csv(a.csv)
        pts = list(zip(df[a.lon_col].astype(float), df[a.lat_col].astype(float)))
        recs = sample_points(pts)
        if a.clean:
            recs = [clean_row(r) for r in recs]
        else:
            recs = [{k: v for k, v in r.items() if k not in ("lon", "lat")} for r in recs]
        out = pd.concat([df.reset_index(drop=True), pd.DataFrame(recs)], axis=1)
        dest = a.out or "enriched.csv"; out.to_csv(dest, index=False)
        print("Wrote %d rows -> %s" % (len(out), dest))
    elif a.lat is not None and a.lon is not None:
        r = sample_points([(a.lon, a.lat)])[0]
        r = clean_row(r) if a.clean else {k: v for k, v in r.items() if k not in ("lon", "lat")}
        for k, v in r.items():
            print("%-18s: %s" % (k, v))
    else:
        ap.error("Provide --lat/--lon or --csv")


if __name__ == "__main__":
    main()
