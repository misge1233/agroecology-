# CSA Feature List — Decision & Justification

_Ethiopia agroecology-based CSA practice recommender · feature stack_
_Decided: 2026-07-22 · Author role: CSA practice scientist_
_Companion to: CSA_feature_stack_plan.md_

## Purpose

Fix the geospatial features to build into the raster feature stack, so any lat/long
returns a ready feature row for (a) enriching the training dataset and (b) live
prediction. Features are chosen on two criteria at once:

1. **Importance** — does it change *which* CSA practice is recommended (evidence from
   Adimassu et al. 2023/2024, the two project papers)?
2. **Accessibility** — can it be extracted for any Ethiopian lat/long from a free,
   documented, national/global raster source?

Label/anchor: the **15 agroecology belt** (existing `agroecology_belt` shapefile),
rasterized into the stack as a categorical band.

## Selection logic (why continuous layers, not just the belt)

The belt is defined from altitude × rainfall and is categorical — every point in a
belt gets the same value. The practices in the papers, however, are differentiated
*within* a belt by slope, soil and drainage. So the stack keeps the belt as the
anchor **and** adds the continuous layers that vary inside it. That within-belt
signal is the entire reason for building the stack.

## CORE feature set (build first — high importance + high accessibility)

| # | Feature | Source | Native res | Units | Type | Resampling | Tier | Why it drives a CSA practice |
|---|---|---|---|---|---|---|---|---|
| 1 | Annual precipitation | CHIRPS | ~5.5 km | mm/yr | continuous | bilinear | 1 | Primary moisture driver; dry (<900 mm) → water harvesting/moisture conservation, wet (>1400 mm) → drainage. Defines the moisture regime. |
| 2 | Mean annual temperature | WorldClim BIO1 | ~1 km | °C | continuous | bilinear | 1 | Thermal belt co-definer; sets crop/variety adaptation and heat stress. |
| 3 | Precipitation seasonality (CV) | WorldClim BIO15 | ~1 km | % | continuous | bilinear | 1 | Rainfall variability → risk-reducing practices, drought-tolerant varieties, insurance (Dry Kolla/Berha). |
| 4 | Length of growing period (LGP) | FAO GAEZ v4 (or derived CHIRPS+PET) | ~9 km | days | continuous | bilinear | 1 | Season length; short LGP (0–60 d) → drought-adapted short-season practices, long LGP (180–300 d) → double cropping/intensification. |
| 5 | Elevation | SRTM / MERIT DEM | ~30–90 m | m | continuous | bilinear | 1 | Belt definer (Berha→Wurch) and within-belt gradient. |
| 6 | Slope | DEM-derived | ~30–90 m | % | continuous | bilinear | 2 | The single biggest split for soil-water works: steep → bench/hillside terrace, bunds, fanya juu; flat → tillage/BBF. |
| 7 | Soil texture / clay content | SoilGrids | 250 m | % clay | continuous | bilinear | 2 | High clay flags Vertisols → BBF/BBM & drainage; light texture → moisture conservation. |
| 8 | Soil pH (H2O) | SoilGrids | 250 m | pH | continuous | bilinear | 2 | Acidity → liming + 4R, acid-tolerant crops (wet highland zones); alkalinity → salt management. |
| 9 | Soil organic carbon | SoilGrids | 250 m | g/kg | continuous | bilinear | 2 | Fertility status → ISFM emphasis (compost/vermicompost, biochar, 4R). |
| 10 | Land cover / land use | ESA WorldCover | 10 m | class | categorical | nearest | 2 | Gates which practice family applies: cropland → CPM/ISFM, grazing → LPM/rangeland, forest → FAF. |
| — | AEZ belt (anchor) | agroecology_belt shapefile (rasterized) | vector | class | categorical | nearest | label | The expert-recommendation key from the papers; stratifier/anchor. |

## EXTENDED set (add when core is validated — high value, slightly lower ease)

| # | Feature | Source | Native res | Type | Why add it |
|---|---|---|---|---|---|
| 11 | Topographic Wetness Index (TWI) | DEM-derived | ~30–90 m | continuous | Where water concentrates → drainage, waterways, gully control; complements slope for waterlogging. |
| 12 | Soil depth / depth to bedrock | SoilGrids (BDTICM) | 250 m | continuous | Rooting depth and terracing feasibility. |
| 13 | Soil salinity / salt-affected class | FAO Global Salt-Affected Soils map (GSSmap) | ~1 km | categorical | Salt-affected lowlands (Dry Kolla) → leaching, salt-loving crops. Lower accessibility, so extended not core. |
| 14 | NDVI mean + trend | MODIS MOD13Q1 | 250 m | continuous | Vegetation productivity and degradation signal → restoration, exclosure, agroforestry. Dynamic (needs a date). |
| 15 | Soil erosion risk (RUSLE) | Global RUSLE layer (Borrelli et al. 2017) or computed | ~250 m–1 km | continuous | Justifies erosion-control intensity (terraces, bunds, exclosure). Partly derivable from #1/#5/#7. |

## Deliberately excluded / deferred

- **Aridity index / PET** — largely captured by #1 + #3 + #4; skip to avoid redundancy.
- **Max temperature of warmest month (heat stress)** — correlated with #2; add only if experts want an explicit heat-stress term.
- **Distance to rivers, groundwater availability** — relevant to irrigation/watering-point
  practices but data are coarse/uncertain for Ethiopia; revisit if irrigation practices
  become a modeling focus.
- **Socio-economic layers (market access, population, farm size)** — affect adoption, not
  biophysical suitability; treat as user-supplied non-spatial inputs at prediction time.
- **`/additional` folder (32-AEZ, agroclimatic raster)** — categorical echo of the climate
  axis, redundant with the belt label and continuous climate; kept only as validation.

## Redundancy / modeling notes

- The belt label and features #1, #2, #5 are correlated by construction. That is expected
  and fine: the belt anchors the recommendation, the continuous layers add sub-belt
  resolution. If a model shows instability from collinearity, drop the belt from the
  *feature* inputs and keep it only as a stratifier.
- Features #6, #7, #11, #15 partly overlap (all erosion/drainage related); keep all in the
  stack, let feature selection during modeling prune them.
- Common grid target: **~250 m, WGS84 (EPSG:4326)**, snapped origin. Finer sources
  (DEM, land cover) aggregated to 250 m; coarser climate resampled up (native resolution
  recorded so resampled climate is not read as true 250 m detail).

## Final decision

Build the **10-feature CORE stack + rasterized AEZ belt** first. It reproduces essentially
all of the practice-differentiating logic in the papers (moisture, temperature, season
length, terrain, soil fertility/drainage, land use) from free, lat/long-extractable
sources. Add the 5 EXTENDED features in a second pass once the core is validated against
the training dataset.
