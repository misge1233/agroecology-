# Geodata release ET/2026.1

Built 2026-11-11T10:05:43+00:00 by `pipelines/geodata/refresh.py` (git adb446d3aa5dc99728dfd79a7ad431fa0f0ac06f+dirty). Grid: 6800 x 5156 cells of 0.00225 degrees (EPSG:4326), hash `b4862eae93fb`. `sources.yaml` hash `7e81d754802c`. QA: **pass**.

**Immutable.** Never edit this folder; a rebuild writes a new release id. Large files are git-ignored; `manifest.json`, `qa_report.json`, this README and the diffs are in git.

| Layer | Status | Source | Version | Unit | Resampling | Cadence | Required | Size | QA |
|---|---|---|---|---|---|---|---|---|---|
| `aez_belt` | built | National agro-ecological belt shapefile | MoA/EIAR belt map, as received 2025 | belt code (data/lookups/aez_belt_lookup.csv) | rasterize (cell centre; outer rings only, as the legacy stack) | static | yes | 0.9 MB | pass |
| `precip_annual` | built | WorldClim 2.1 | 2.1 (1970-2000 normals) | mm/yr | bilinear | static | yes | 109.6 MB | pass |
| `temp_mean_annual` | built | WorldClim 2.1 | 2.1 (1970-2000 normals) | degC | bilinear | static | yes | 102.2 MB | pass |
| `precip_seasonality` | built | WorldClim 2.1 (BIO15 definition) | 2.1 (1970-2000 normals) | percent (CV of monthly rainfall) | bilinear | static | yes | 120.5 MB | pass |
| `lgp_days` | built | WorldClim 2.1 (derived water balance) | 2.1 (1970-2000 normals) | days | bilinear | static | yes | 4.7 MB | pass |
| `elevation` | built | Copernicus DEM GLO-30 | GLO-30 (2021 release) | m | bilinear | static | yes | 144.5 MB | pass |
| `slope` | built | Copernicus DEM GLO-30 (derived) | GLO-30 (2021 release) | percent | none (computed on the grid) | static | yes | 186.3 MB | pass |
| `soil_clay` | built | SoilGrids v2.0, clay 0-5 cm | 2.0 | percent | bilinear | occasional | yes | 76.8 MB | pass |
| `soil_ph` | built | SoilGrids v2.0, pH(H2O) 0-5 cm | 2.0 | pH | bilinear | occasional | yes | 37.1 MB | pass |
| `soil_soc` | built | SoilGrids v2.0, organic carbon 0-5 cm | 2.0 | g/kg | bilinear | occasional | yes | 87.8 MB | pass |
| `land_cover` | built | ESA WorldCover 2021 (landcover_2021) | v200 (2021) | WorldCover class code | mode | annual | yes | 5.8 MB | pass |
| `slope_length_factor` | built | Copernicus DEM GLO-30 (derived) | GLO-30 (2021 release) | dimensionless (RUSLE LS) | average (90 m -> 250 m) | static | no | 185.8 MB | pass |
| `tpi` | built | Copernicus DEM GLO-30 (derived) | GLO-30 (2021 release) | m | average (90 m -> 250 m) | static | no | 201.4 MB | pass |
| `twi` | built | Copernicus DEM GLO-30 (derived) | GLO-30 (2021 release) | dimensionless | average (90 m -> 250 m) | static | no | 177.2 MB | pass |
| `flow_accumulation` | built | Copernicus DEM GLO-30 (derived) | GLO-30 (2021 release) | km2 (upstream area) | max (90 m -> 250 m) | static | no | 182.6 MB | pass |
| `dist_to_stream_m` | built | Copernicus DEM GLO-30 (derived) | GLO-30 (2021 release) | m | min (90 m -> 250 m) | static | no | 143.1 MB | pass |
| `soil_sand` | built | SoilGrids v2.0, sand 0-30 cm | 2.0 | percent | bilinear | occasional | no | 102.3 MB | pass |
| `soil_bulk_density` | built | SoilGrids v2.0, bulk density (bdod) 0-30 cm | 2.0 | g/cm3 | bilinear | occasional | no | 99.6 MB | pass |
| `soil_cec` | built | SoilGrids v2.0, cation exchange capacity 0-30 cm | 2.0 | cmol(c)/kg | bilinear | occasional | no | 103.0 MB | pass |
| `soil_nitrogen` | built | SoilGrids v2.0, total nitrogen 0-30 cm | 2.0 | g/kg | bilinear | occasional | no | 148.6 MB | pass |
| `soil_awc` | built | SoilGrids v2.0 (derived, Saxton and Rawls 2006) | 2.0 | mm/m (volumetric water between 33 and 1500 kPa) | none (computed on the grid) | occasional | no | 142.3 MB | pass |
| `soil_depth_bedrock` | built | SoilGrids250m 2017, absolute depth to bedrock (BDRICM) | 2017-03-10 | cm | bilinear | occasional | no | 16.5 MB | pass |
| `rain_mean_1991_2020` | built | CHIRPS v2.0 | 2.0 | mm/yr | bilinear | annual | no | 65.6 MB | pass |
| `rain_cv_interannual` | built | CHIRPS v2.0 | 2.0 | percent | bilinear | annual | no | 66.6 MB | pass |
| `dry_season_length_months` | built | CHIRPS v2.0 | 2.0 | months | bilinear (monthly climatology), then counted on the grid | annual | no | 1.2 MB | pass |
| `pet_hargreaves_annual` | built | WorldClim 2.1 (derived, Hargreaves 1985) | 2.1 (1970-2000 normals) | mm/yr | bilinear | static | no | 110.9 MB | pass |
| `aridity_index` | built | CHIRPS v2.0 / WorldClim 2.1 (derived) | 2.0; 2.1 (1970-2000 normals) | dimensionless (P / PET, UNEP classes) | none (computed on the grid) | annual | no | 119.9 MB | pass |
| `cropland_fraction_1km` | built | ESA WorldCover 2021 (derived) | v200 (2021) | fraction (0-1) | block count (27 x 27 pixels = one grid cell), then a 1 km box | annual | no | 82.2 MB | pass |
| `travel_time_to_city_min` | built | Malaria Atlas Project accessibility to cities 2015 | 2015 (v1.0) | minutes | bilinear | occasional | no | 125.4 MB | pass |
| `ndvi_trend` | pending | MODIS MOD13Q1 NDVI | 061 | NDVI per year | bilinear | annual | no |  |  |
| `koppen_class` | built | Beck et al. 2018 Koppen-Geiger, present | V1 (2018) | Koppen-Geiger class code (legend in pipelines/geodata/layers/koppen.py) | nearest | static | no | 1.0 MB | pass |
| `overlay_hotspot_coldspot` | pending | Omo-Gibe Living Landscape hotspot/coldspot raster (countries/ET.yaml overlays.omo_gibe) |  | class code | nearest | occasional | no |  |  |
| `overlay_typology` | pending | Omo-Gibe Living Landscape typology raster (countries/ET.yaml overlays.omo_gibe) |  | class code | nearest | occasional | no |  |  |
| `mask_omo_gibe` | pending | footprint of the Omo-Gibe overlay rasters |  | 1 inside the basin extent | nearest | occasional | no |  |  |

## Not built

- `ndvi_trend` (pending): LP DAAC and AppEEARS downloads need a NASA Earthdata login; the brief excludes credentials
- `overlay_hotspot_coldspot` (pending): no GeoTIFF at countries/ET.yaml overlays.omo_gibe.rasters.hotspot_coldspot = 'data/raw/hotspot and coldspot/'
- `overlay_typology` (pending): no GeoTIFF at countries/ET.yaml overlays.omo_gibe.rasters.typology = 'data/raw/Typology/'
- `mask_omo_gibe` (pending): no overlay raster present

## Licences

- CC BY 4.0
- CC0 1.0 / public domain (Climate Hazards Center; owner to confirm)
- CC0 1.0 / public domain (Climate Hazards Center; owner to confirm); WorldClim 2.1 terms (free for research and non-commercial use; owner to confirm); WorldClim 2.1 terms (owner to confirm)
- Copernicus DEM licence (free, attribution: (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA)
- NASA EOSDIS open data (no restriction)
- WorldClim 2.1 terms (free for research and non-commercial use; owner to confirm)
- WorldClim 2.1 terms (free for research and non-commercial use; owner to confirm); WorldClim 2.1 terms (owner to confirm)
- national data; internal use (owner to confirm)

Read it with `pipelines.geodata.extract.ContextExtractor("geodata/ET/2026.1")` or point the backend at it with `GEODATA_RELEASE=ET/2026.1`.
