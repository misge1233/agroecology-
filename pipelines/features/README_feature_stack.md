# CSA Feature Stack — Ethiopia agroecology-based CSA recommender

Give any lat/long -> get the **AEZ name (1 of 15) + 10 continuous features**, ready
for the CSA practice model. Same routine enriches a training CSV or answers a single
prediction point. Feature rationale: see `../CSA_feature_decision.md`.

## STATUS: complete — all 11 layers built and verified

| Layer | Source | Units |
|---|---|---|
| aez_belt (anchor) | your agroecology_belt shapefile | 15-zone class -> name |
| precip_annual | WorldClim 2.1 (sum of 12 months) | mm/yr |
| temp_mean_annual | WorldClim 2.1 (mean of 12 months) | degC |
| precip_seasonality | WorldClim BIO15 (CV of monthly rain) | % |
| lgp_days | derived water-balance LGP (Thornthwaite PET) | days |
| elevation | Copernicus GLO-30 DEM | m |
| slope | derived from DEM (latitude-aware) | % |
| soil_clay | SoilGrids v2 0-5 cm | % |
| soil_ph | SoilGrids v2 0-5 cm | pH |
| soil_soc | SoilGrids v2 0-5 cm | g/kg |
| land_cover | ESA WorldCover 2021 | class label (Cropland, Built-up, ...) |

Common grid: WGS84 (EPSG:4326), ~250 m (0.00225 deg), 6800 x 5156, Ethiopia
(lon 32.9-48.2, lat 3.3-14.9). Every layer aligns to `layers/aez_belt.tif`.

## Use it (production + training)

```bash
pip install rasterio pandas numpy

# single prediction point -> AEZ name + 10 features
python extract_features.py --lat 9.03 --lon 38.74 --clean

# enrich a whole training CSV (columns lat, lon)
python extract_features.py --csv points.csv --clean --out enriched.csv
```

`--clean` returns exactly: aez_name, precip_annual, temp_mean_annual, precip_seasonality,
lgp_days, elevation, slope, soil_clay, soil_ph, soil_soc, land_cover.
Omit `--clean` to also get the AEZ zonal reference attributes (altitude/temp/rain/LGP class ranges).

**Masked cells:** SoilGrids masks cities and lakes, and the DEM has small gaps; the
sampler automatically falls back to the nearest valid cell within ~20 km, so a real
land point never returns empty. (Verified: Addis, a city, still returns soil values.)

## Files

```
feature_stack/
├── layers/                     the stack (11 aligned GeoTIFFs)
│   ├── aez_belt.tif ... land_cover.tif
│   └── stack_all.vrt           single-file 11-band view (QGIS / per-band read)
├── aez_belt_lookup.csv         AEZ code -> zone name
├── aez_attributes.csv          AEZ zonal reference attributes
├── extract_features.py         lat/long -> features  (with nearest-valid fallback)
├── make_maps.py                render maps (set MAPS_OUT to redirect)
├── maps/
│   ├── aez_belt_map_final.png
│   └── feature_maps_final.png  AEZ + all 10 feature maps
├── enriched_demo_final.csv     worked example (6 towns)
├── get_*.py                    per-feature downloaders (already run)
├── build_stack.py              batch acquire/align helper
└── grid_definition.json
```

## Reproduce / update a layer

Each feature has a standalone downloader that fetches, clips, and aligns to the grid:
`get_precip.py`, `get_temp.py`, `get_seasonality.py`, `get_lgp.py`, `get_terrain.py`
(elevation+slope), `get_soil.py` (clay/ph/soc), `get_landcover.py`. Re-run any one to
refresh that layer; `extract_features.py` and `make_maps.py` pick it up automatically.

## Notes

- `lgp_days` is a derived water-balance LGP; it runs generous where PET is low (high
  altitude). Swap in official FAO GAEZ LGP later via `build_stack.py --layer lgp` if desired.
- `elevation`/`slope` cover ~96% of land (tiny DEM-tile gaps near the NE border);
  the fallback handles points there.
- Next phase: train the CSA practice model on the enriched dataset.
