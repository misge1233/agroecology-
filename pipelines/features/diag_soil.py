#!/usr/bin/env python3
"""diag_soil.py - report coverage of the soil layers and sample several towns."""
import os, numpy as np, rasterio
BASE = os.path.dirname(os.path.abspath(__file__)); L = os.path.join(BASE, "layers")
PTS = {"Addis":(38.74,9.03), "near-Addis rural":(38.55,8.90),
       "Hawassa":(38.48,7.06), "Bahir Dar":(37.40,11.60), "Mekelle":(39.47,13.49)}
for f in ["soil_clay.tif","soil_ph.tif","soil_soc.tif"]:
    p = os.path.join(L, f)
    if not os.path.exists(p):
        print(f"{f}: MISSING"); continue
    with rasterio.open(p) as s:
        a = s.read(1); nd = s.nodata
        valid = a[a != nd] if nd is not None else a.ravel()
        pct = 100.0 * valid.size / a.size
        print(f"\n{f}: {s.width}x{s.height} crs={s.crs} nodata={nd}")
        if valid.size:
            print(f"  valid {pct:.1f}%  range {valid.min():.2f}-{valid.max():.2f}  median {np.median(valid):.2f}")
        else:
            print("  ALL NODATA (fetch failed)")
        for name,(lon,lat) in PTS.items():
            v = list(s.sample([(lon,lat)]))[0][0]
            print(f"    {name:18s} = {v}")
