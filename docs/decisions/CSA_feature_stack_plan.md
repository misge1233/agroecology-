# CSA Practice Recommendation — Spatial Feature Layer Plan

_Ethiopia agroecology-based Climate-Smart Agriculture (CSA) recommender_
_Prepared: 2026-07-22 · Status: design agreed, on hold pending final feature list_

## 1. Objective

Build the spatial data layer that supplies **geospatial features from a lat/long point**, so that:

1. **Training** — our existing dataset (which has lat/long) is enriched by sampling features at each point.
2. **Prediction** — a user enters only a lat/long; the system extracts the spatial features automatically, the user adds the remaining non-spatial features, and the (later) ML model returns a CSA practice recommendation.

The ML recommender itself is a **later** phase. The current task is **only** to prepare the feature layer so features are ready to extract. No model work now.

## 2. Architecture decision — Raster Feature Stack (agreed)

A **raster feature stack** is the chosen structure, not a polygon shapefile.

Why:
- Feature sources (DEM, climate, soil grids, land cover) are already rasters — no lossy conversion.
- Point sampling is trivial and **identical** for training-set enrichment and single-point prediction.
- Avoids the false within-zone uniformity of the current 15-polygon AEZ shapefile (every point in a zone would otherwise get the same value; continuous features like slope and soil vary within a zone).
- Modular: add, swap, or re-version a single layer without rebuilding everything.

The current 15-polygon AEZ shapefile is **rasterized into the stack** as one categorical band, so a single sampling call returns the zone label plus all continuous features in one aligned row.

## 3. Design choices to lock before building

| Choice | Decision / recommendation |
|---|---|
| CRS | WGS84 geographic (EPSG:4326) so lat/long samples directly |
| Extent | Clipped to Ethiopia |
| Resolution | Set from the finest meaningful source (likely DEM or soil grid, ~250 m). Resample coarser climate layers up to match. **Record each layer's native resolution** so resampled data is not mistaken for true detail. |
| Grid alignment | Fixed origin / snap so every layer's cells line up exactly |
| Resampling — continuous | Bilinear (elevation, rainfall, pH, etc.) |
| Resampling — categorical | Nearest-neighbour (soil class, land cover, AEZ) to avoid inventing classes |
| Storage | Per-feature aligned single-band GeoTIFFs tied by a VRT (flexible during development); optionally one multi-band GeoTIFF once the feature set is stable |

## 4. Candidate features (from the two AICCRA / Adimassu et al. CSA papers)

The recommendations we will train against are AEZ-level and expert-derived. The papers define zones from altitude + rainfall, but experts chose practices within zones using a second layer of soil/terrain/condition variables. Two tiers result:

**Tier 1 — defines the AEZ (altitude × rainfall; temp & LGP co-vary)**
- Elevation (m)
- Annual rainfall (mm)
- Mean annual temperature (°C)
- Length of growing period, LGP (days)

**Tier 2 — differentiates practices within a zone**
- Slope / terrain (terracing vs bunds vs tillage)
- Soil type / texture (Vertisol vs red clay vs sandy → drainage vs moisture conservation)
- Soil pH / acidity (liming, acid-tolerant crops)
- Soil salinity (leaching, salt-loving crops)
- Soil organic carbon / fertility proxy (ISFM emphasis)
- Land cover / land use (crop vs range vs forest → practice applicability)
- Erosion / degradation index (erosion-control emphasis)
- Rainfall reliability / variability, drought frequency (water harvesting vs drainage)
- Number of cropping seasons (unimodal vs bimodal rainfall)

_Also flagged by the papers to raise with experts: groundwater availability, and commodity/market context._

Candidate source datasets (to confirm per feature): SRTM/ASTER DEM (elevation, slope); CHIRPS / WorldClim (rainfall, temperature, variability); SoilGrids and/or EthioSIS (texture, pH, OC, salinity); national/global land-cover products; Hurni et al. (2016) for the AEZ classification thresholds.

## 5. Coverage gaps / fallback needed

The papers' 9 zones cover ~97% of Ethiopia. **Wurch (>3200 m)** and the **western Moist Berha** lowland are not covered — the system needs a fallback rule for lat/longs that fall in these.

## 5b. Data inputs reviewed and excluded

- **`/additional` folder — excluded.** Contains a 32-class AEZ shapefile and an agroclimatic raster. Both cover only the climate dimension (thermal + moisture) as categorical bins, which is redundant with the 15-belt AEZ label (itself altitude × rainfall) and with the planned continuous climate layers. No soil, terrain, land cover, or degradation content. Kept only as optional reference/validation, not as model features.
- **Zone/label decision — confirmed:** the **15 agroecology belt** (original `agroecology_belt` shapefile) is the recommendation label/zone.

## 6. Feature template (to be filled during the expert discussion)

Decisions should be recorded in this exact form so the build can start immediately:

| Feature name | Source dataset | Native resolution | Units | Continuous / categorical | Resampling method | Tier | Include? (Y/N) |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## 7. Next steps (when feature list is final)

1. Experts finalize the feature list; fill the template in §6.
2. For each chosen feature: acquire source → clip to Ethiopia → reproject to EPSG:4326 → resample onto the common grid.
3. Rasterize the AEZ polygon as a categorical band into the stack.
4. Assemble the aligned stack (GeoTIFFs + VRT).
5. Deliver an extraction routine: input a single lat/long **or** the whole training CSV → output the feature table.
6. (Later phase) Train the ML recommender on the enriched dataset.
