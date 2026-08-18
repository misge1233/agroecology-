#!/usr/bin/env python3
r"""
build_zonal_attributes.py  —  v0 feature stack (offline, real & cited).

Attaches the AEZ-defining biophysical attributes to every point via the AEZ belt.
Values are the zonal class ranges from Hurni et al. (2016), Soil & Water
Conservation in Ethiopia (the classification used by Adimassu et al. 2023/2024,
Table 1). Each point in a belt inherits that belt's class attributes.

Outputs:
  aez_attributes.csv        the full zonal attribute table (the RAT / lookup)
  layers/stack_zonal.tif     multiband raster (midpoints + codes), aligned to grid

This is the Path-A baseline: lat/long -> AEZ -> defining climate/elevation/LGP.
Continuous within-belt layers are added later by build_stack.py (needs internet).
"""
import os, csv, numpy as np, rasterio

BASE   = os.path.dirname(os.path.abspath(__file__))
LAYERS = os.path.join(BASE, "layers")
AEZ    = os.path.join(LAYERS, "aez_belt.tif")
LOOKUP = os.path.join(BASE, "aez_belt_lookup.csv")

# belt (thermal/altitude): (alt_min, alt_max, temp_min, temp_max, thermal_code)
BELT = {
    "Berha":      (0,    500,  27.5, 35.0, 1),
    "Kolla":      (500,  1500, 25.0, 30.0, 2),
    "Weyna Dega": (1500, 2300, 18.0, 25.0, 3),
    "Dega":       (2300, 3200, 12.0, 18.0, 4),
    "High Dega":  (3200, 3700, 7.5,  12.0, 5),
    "Wurch":      (3700, 4500, 3.0,  7.5,  6),
}
# moisture: (rain_min, rain_max, lgp_min, lgp_max, moisture_code)
MOIST = {
    "Dry":   (300,  900,  0,   60,  1),
    "Moist": (900,  1400, 60,  180, 2),
    "Wet":   (1400, 2200, 180, 300, 3),
}

def parse(name):
    for m in ("Dry", "Moist", "Wet"):
        if name.startswith(m):
            return m, name[len(m) + 1:]
    raise ValueError(name)

def mid(a, b):
    return round((a + b) / 2, 2)

def main():
    zones = {}
    with open(LOOKUP) as f:
        for r in csv.DictReader(f):
            zones[int(r["value_OBJECTID"])] = r["Agro_zone"]

    rows, attr = [], {}
    for code, name in sorted(zones.items()):
        moist, belt = parse(name)
        amn, amx, tmn, tmx, tcode = BELT[belt]
        rmn, rmx, lmn, lmx, mcode = MOIST[moist]
        rec = dict(aez_code=code, aez_zone=name, moisture_regime=moist, thermal_belt=belt,
                   alt_min_m=amn, alt_max_m=amx, alt_mid_m=mid(amn, amx),
                   temp_min_c=tmn, temp_max_c=tmx, temp_mid_c=mid(tmn, tmx),
                   rain_min_mm=rmn, rain_max_mm=rmx, rain_mid_mm=mid(rmn, rmx),
                   lgp_min_days=lmn, lgp_max_days=lmx, lgp_mid_days=mid(lmn, lmx),
                   moisture_code=mcode, thermal_code=tcode)
        rows.append(rec)
        attr[code] = rec

    with open(os.path.join(BASE, "aez_attributes.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("aez_attributes.csv:", len(rows), "zones")

    with rasterio.open(AEZ) as s:
        a = s.read(1)
        prof = s.profile
    bands = ["alt_mid_m", "temp_mid_c", "rain_mid_mm", "lgp_mid_days", "moisture_code", "thermal_code"]
    ND = -9999.0
    out = np.full((len(bands), a.shape[0], a.shape[1]), ND, dtype="float32")
    for bi, b in enumerate(bands):
        remap = np.full(max(attr) + 1, ND, dtype="float32")
        for code, rec in attr.items():
            remap[code] = rec[b]
        mask = a > 0
        out[bi][mask] = remap[a[mask]]
    prof.update(count=len(bands), dtype="float32", nodata=ND, compress="lzw",
                tiled=True, blockxsize=256, blockysize=256)
    dst = os.path.join(LAYERS, "stack_zonal.tif")
    with rasterio.open(dst, "w", **prof) as d:
        d.write(out)
        for i, b in enumerate(bands, 1):
            d.set_band_description(i, b)
    print("stack_zonal.tif bands:", bands)

if __name__ == "__main__":
    main()
