# Geodata

## `layers/` — the 11-layer, 250 m Ethiopia feature stack (canonical)

WGS84 · ~250 m (0.00225°) · 6,800 × 5,156 cells · all layers snapped to one grid
(`data/lookups/grid_definition.json`). Total ≈ 730 MB — **kept on disk, excluded
from git** (`.gitignore`).

| Layer | Source | Unit |
|---|---|---|
| `aez_belt.tif` | national AEZ shapefile (`sources/agroecology_belt/`), rasterized | class (15 belts) |
| `precip_annual.tif` | WorldClim 2.1 | mm/yr |
| `temp_mean_annual.tif` | WorldClim 2.1 | °C |
| `precip_seasonality.tif` | WorldClim 2.1 (BIO15) | CV % |
| `lgp_days.tif` | water-balance model (Thornthwaite PET) | days |
| `elevation.tif` | Copernicus GLO-30 DEM | m |
| `slope.tif` | DEM-derived, latitude-aware | % |
| `soil_clay.tif`, `soil_ph.tif`, `soil_soc.tif` | SoilGrids v2 (0–5 cm) | %, pH, g/kg |
| `land_cover.tif` | ESA WorldCover 2021 | class code |
| `stack_all.vrt` | virtual stack over all layers | — |

## Rebuilding from scratch

Each layer is produced by a script in `pipelines/features/` (`get_precip.py`,
`get_temp.py`, `get_seasonality.py`, `get_lgp.py`, `get_terrain.py`,
`get_soil.py`, `get_landcover.py`, `add_aez_belt.py`), then aligned with
`build_stack.py` and QA'd with `final_qa.py`. Raw WorldClim archives
(`wc2.1_30s_prec.zip`, `wc2.1_30s_tavg.zip`, ~5.3 GB) are **not** stored in this
repo — download from https://worldclim.org/data/worldclim21.html into a scratch
directory before running the precip/temp scripts.

## `sources/`

Vector/raster inputs kept for provenance: the 15-belt agroecology shapefile
(anchor of the whole system), the 32-class AEZ shapefile, agroclimatic zone
raster, and the WRB soil grid.
