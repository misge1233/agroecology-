#!/usr/bin/env python3
"""
Extract CSA feature-stack values for lat/long point(s).

Thin CLI over ``pipelines.geodata.extract.ContextExtractor`` (brief E3 C1): samples
every layer of a geodata release (``--release ET/2026.1``) or of a layer folder
(``--layers DIR``; default: ``LAYERS_DIR``, else ``./layers``, else the repo's
``geodata/layers``) and joins the AEZ zonal attribute table (aez_attributes.csv).
land_cover is returned as a readable label. If a point lands on a masked / nodata
cell (SoilGrids masks cities and lakes), it falls back to the NEAREST valid cell
within ~20 km.

Usage:
    python extract_features.py --lat 9.03 --lon 38.74
    python extract_features.py --lat 9.03 --lon 38.74 --clean
    python extract_features.py --csv points.csv --clean --out enriched.csv
    python extract_features.py --release ET/2026.1 --lat 9.03 --lon 38.74 --clean

Requires: rasterio, pandas, numpy
"""
import argparse, csv, os, sys
from pathlib import Path

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(BASE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from pipelines.geodata.extract import CLI_RADIUS, ContextExtractor  # noqa: E402  (wrap, never fork)

MAX_R = CLI_RADIUS   # nearest-valid search radius in pixels (~20 km at 250 m)


def _default_layer_dir():
    """LAYERS_DIR, else ./layers (the historical location), else the repo's canonical geodata/layers."""
    env = os.environ.get("LAYERS_DIR")
    if env:
        return env if os.path.isabs(env) else os.path.join(REPO, "app", "backend", env)
    local = os.path.join(BASE, "layers")
    return local if os.path.isdir(local) else os.path.join(REPO, "geodata", "layers")


def _default_attrs():
    local = os.path.join(BASE, "aez_attributes.csv")
    return local if os.path.exists(local) else os.path.join(REPO, "data", "lookups", "aez_attributes.csv")


LAYER_DIR = _default_layer_dir()
ATTRS = _default_attrs()

FEATURES10 = ["precip_annual", "temp_mean_annual", "precip_seasonality", "lgp_days",
              "elevation", "slope", "soil_clay", "soil_ph", "soil_soc", "land_cover"]

# ESA WorldCover class codes -> labels
LANDCOVER = {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
             50: "Built-up", 60: "Bare/sparse vegetation", 70: "Snow and ice",
             80: "Permanent water", 90: "Herbaceous wetland", 95: "Mangroves",
             100: "Moss and lichen"}


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


def sample_points(points, layer_dir=None):
    """Sample every layer at (lon, lat) points; AEZ attributes and land-cover labels joined."""
    ext = ContextExtractor(layer_dir or LAYER_DIR, max_radius_px=MAX_R)
    if not ext.layer_ids():
        sys.exit("No .tif layers found in %s" % (layer_dir or LAYER_DIR))
    aez_attrs = load_aez_attributes()
    raw = ext.sample(points)
    rows = [dict(lon=lon, lat=lat) for lon, lat in points]
    for r, vals in zip(rows, raw):
        for name in ext.layer_ids():
            val = vals.get(name)
            if name == "aez_belt":
                if val is not None and int(val) in aez_attrs:
                    r.update(aez_attrs[int(val)])
                    r["aez_name"] = aez_attrs[int(val)]["aez_zone"]
                else:
                    r["aez_name"] = None
            elif name == "land_cover":
                r["land_cover"] = None if val is None else LANDCOVER.get(int(val), int(val))
            else:
                r[name] = val
        if ext.release_id:
            r["release_id"] = ext.release_id
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
    ap.add_argument("--layers", help="layer folder (default: %s)" % LAYER_DIR)
    ap.add_argument("--release", help="geodata release, e.g. ET/2026.1 (under geodata/)")
    a = ap.parse_args()
    layer_dir = os.path.join(REPO, "geodata", *a.release.split("/")) if a.release else a.layers

    if a.csv:
        import pandas as pd
        df = pd.read_csv(a.csv)
        pts = list(zip(df[a.lon_col].astype(float), df[a.lat_col].astype(float)))
        recs = sample_points(pts, layer_dir)
        if a.clean:
            recs = [clean_row(r) for r in recs]
        else:
            recs = [{k: v for k, v in r.items() if k not in ("lon", "lat")} for r in recs]
        out = pd.concat([df.reset_index(drop=True), pd.DataFrame(recs)], axis=1)
        dest = a.out or "enriched.csv"; out.to_csv(dest, index=False)
        print("Wrote %d rows -> %s" % (len(out), dest))
    elif a.lat is not None and a.lon is not None:
        r = sample_points([(a.lon, a.lat)], layer_dir)[0]
        r = clean_row(r) if a.clean else {k: v for k, v in r.items() if k not in ("lon", "lat")}
        for k, v in r.items():
            print("%-18s: %s" % (k, v))
    else:
        ap.error("Provide --lat/--lon or --csv")


if __name__ == "__main__":
    main()
