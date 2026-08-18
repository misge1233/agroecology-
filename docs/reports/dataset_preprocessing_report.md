# CSA Practice Dataset — Preprocessing Report

**Use case:** decision-support model predicting the CSA-practice **response ratio**
(`With/without`) from practice + agroecological context + outcome indicator.
**Input:** `dataset/CSA_practices_by_Agroecology.xlsx` (3,344 rows × 21 cols)
**Output:** `dataset/CSA_practices_model_ready.csv` (**1,872 rows × 19 cols**, 0 missing)
**Prepared:** senior data-scientist pass — cleaning only (no feature selection / training).

## Preprocessing steps & reasoning

**1. Scope filter → 10 core indicators (3,344 → 2,113).**
`Indicator` had 162 messy variants. Kept only the 10 indicators defined for the model,
matching case/whitespace-insensitively and normalising to canonical labels:
yield, biomass yield, net income, water use efficiency, available P, SOM content
(higher = better); soil loss, runoff, irrigation amount, bulk density (lower = better).
Reason: these are frequent, have a clear "better" direction, and are unit-free once
expressed as a response ratio, so they pool into one model with `Indicator` as a feature.

**2. Remove exact duplicate records (2,113 → 2,029).**
84 fully-identical rows dropped as data-entry repeats.

**3. Hidden-missing coordinates (2,029 → 2,000) and study-area bounds (→ 1,992).**
`Latitude`/`Longitude` used `0.0` as a placeholder for missing location (29 rows); these
can't be geolocated, so dropped. A further 8 rows fell outside the feature-stack extent
(Ethiopia, lat 3.3–14.9, lon 32.9–48.2) and were removed because stack features can't be
retrieved there.

**4. Target validity — positive means only (1,992 → 1,879).**
The response ratio `With/without` and its log require both group means > 0. Rows with
`With ≤ 0` or `without ≤ 0` (zeros used as missing, and a few negatives — e.g. net-income
losses) were dropped: 113 rows. A ratio is undefined/negative otherwise.

**5. Target engineering.**
`response_ratio = With / without`; `log_response_ratio = ln(response_ratio)`.
The log ratio is the standard, symmetric, variance-stabilising meta-analysis effect size
and is the recommended modelling target; the raw ratio is retained for interpretability.

**6. Outlier handling — direction-aware (1,879 → 1,872).**
Inspected all |log ratio| > 3. Large *reductions* in soil loss/runoff (ratio ≈ 0.025,
i.e. 95–98% less, from stone/soil bunds) are agronomically real and were **kept**. The
7 implausible cases were all >20× *increases* in yield/WUE driven by erroneous near-zero
controls (`without = 1`); these were removed with the rule `response_ratio ≤ 20`.
Asymmetry is intentional and domain-justified.

**7. Categorical normalisation — `crop_type` (67 → 41 clean values).**
Fixed spelling/case variants (mize/maise/maiize→Maize; tef→Teff; weat→Wheat;
barely→Barley; onio→Onion; fingure millet→Finger millet; etc.) and mapped local names
(Ater/Dekeko→Field pea; grass pee→Grass pea). Non-crop land uses present in soil-loss/
runoff studies (cropland, grazing land, forest, exclosure…) were standardised as their
land-use type. Blank crop_type → `Unspecified`.

**8. Feature engineering — `Crop_group`.**
Assigned each standardised crop to an agronomic group: Cereal, Pulse, Oilseed, Vegetable,
Root & tuber, Forage, Cereal-Legume, plus land-use groups for non-crop rows
(Cropland, Grassland-Rangeland, Forest-Woody, Other-Mixed, Unspecified).

**9. Geospatial feature replacement from the feature stack.**
Using each record's lat/long, the following were retrieved from the 250 m Ethiopia
feature stack (nearest-valid-cell fallback for masked urban/water pixels), replacing the
sparse original columns:
`Rainfall ← precip_annual`, `Altitude_r ← elevation`, `slope ← slope`; and new columns
`temp_mean_annual, precip_seasonality, lgp_days, soil_clay, soil_ph, soil_soc, land_cover`
(land_cover as ESA WorldCover class **code**). Reason: the stack values are consistent,
gap-free and reproducible for prediction, whereas the original fields were coarse and
partly missing.

**10. Leakage / unsuitable columns removed.**
`With`, `without` (define the target → leakage), and non-predictive / redundant fields
(`Reference, Region, Soil_type, Agro_zone, CSA_catago, duration_o, Scale, study_site,
unit, CSA_Pilar`) were dropped per the modelling column spec.

**11. Final integrity check.** Confirmed **0 missing values** across all 1,872 × 19 cells.

## Final dataset

- **Dimensions:** 1,872 rows × 19 columns; 0 missing.
- **Identifiers (not features):** `Study_No_`, `latitude`, `longitude`.
- **Features (14):** `CSA_practi`, `Crop_group`, `crop_type`, `Rainfall`, `Altitude_r`,
  `slope`, `temp_mean_annual`, `precip_seasonality`, `lgp_days`, `soil_clay`, `soil_ph`,
  `soil_soc`, `land_cover`, `Indicator`.
- **Target:** `response_ratio` (raw) and **`log_response_ratio`** (recommended modelling target).

Row counts by indicator: yield 914, runoff 248, soil loss 190, irrigation amount 135,
biomass yield 98, water use efficiency 93, available P 67, SOM content 45, bulk density 42,
net income 40.

## Assumptions

1. The 10 core indicators are matched by exact normalised strings; related but distinct
   measures (e.g. "runoff coefficient", "yield legume") were **not** folded in, to avoid
   mixing measurement bases.
2. Both `With` and `without` are treated as positive group means; negative/zero rows are
   invalid for a ratio and dropped (affects net income most).
3. `response_ratio > 20` treated as data error (erroneous ~zero control); large reductions
   kept as real.
4. Non-crop `crop_type` land uses are legitimate contexts for soil-loss/runoff studies and
   are retained via land-use `Crop_group`s; blank crop → `Unspecified`.
5. Geospatial features come from the modelled 250 m stack (WorldClim/SoilGrids/Copernicus/
   ESA/derived), not the original workbook columns; `land_cover` is a class code.
6. `Cereal-Legume` has a single record (maize-bean intercrop) — a rare category to watch
   in modelling (may be merged into Cereal or Pulse if it causes issues).
