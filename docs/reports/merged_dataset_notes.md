# Merged Modeling Dataset — CSA + ERA

**File:** `dataset/CSA_ERA_merged_model_ready.csv` — **8,664 rows × 20 columns, 0 missing.**
Objective: predict the CSA-practice **response ratio** (`log_response_ratio`) from
practice + agroecological context + indicator, for zone-level recommendations.

## What the merge did
- Concatenated the two model-ready files (identical 19-col schema).
- Added a **`source`** column (CSA / ERA) and prefixed `Study_No_` (`CSA_…`, `ERA_…`)
  so IDs don't collide and the origin is traceable.
- Removed **681 exact duplicates** (identical across all features + target); kept first.
- Sources: **ERA 7,250 (84%) + CSA 1,414 (16%)**.
- Indicators (7): yield 5,910; biomass yield 1,525; runoff 359; soil loss 296;
  water use efficiency 255; income 208; SOM content 111.
- Target: `log_response_ratio` (recommended) and `response_ratio` (raw).

## Things to consider before modeling

**1. Practice vocabularies barely overlap (most important).**
`CSA_practices` has two disjoint taxonomies: 20 CSA categories (Physical SWC measures,
ISFM, In-situ water harvesting…) vs 81 ERA practices (Inorganic Fertilizer, Improved
Varieties, Water Harvesting…), 1,398 of them combined names (e.g. "Inorganic
Fertilizer-Organic Fertilizer"). **Only "Intercropping" is shared.** If encoded as-is the
model can identify `source` from the practice name and can't compare a CSA practice against
an ERA practice in the same zone. **Recommendation:** build a practice crosswalk to a shared
scheme (e.g. map both to the ~10 CSA-category families used in the recommender) before
training. This is the key decision for the recommendation objective.

**2. Source imbalance and target shift.**
ERA is 84% of rows and skews positive (mean log-ratio +0.19, mostly fertilizer/variety
yield gains); CSA centres near 0 (−0.09, more SWC/soil outcomes). `source` is partly a
confounder. Keep the `source` column; consider source-stratified checks and be cautious
about pooling naively.

**3. Repeated sites → use grouped validation.**
Only 348 unique locations; a study contributes a median of 12 (max 548) rows. Random
train/test splits would leak site information. **Use GroupKFold / grouped split by
`Study_No_`** (or by site) so the same study isn't in both train and test.

**4. Identifiers are not features.**
`source`, `Study_No_`, `latitude`, `longitude` are metadata — exclude them from the model
inputs. Location is already encoded via the stack features; feeding raw lat/long risks
memorising sites.

**5. Class imbalance in the target categories.**
`yield` is 68% of rows; `income` and `SOM content` are thin (208 / 111). The model will be
strong on yield/biomass and weak on the rare indicators — weight or report per-indicator.

**6. High-cardinality categoricals + land_cover.**
`crop_type` (~90 values incl. intercrops) and `CSA_practices` need an encoding plan
(target/frequency encoding, or fold rare levels into `Crop_group`). `land_cover` is a
categorical **code** (10/20/…/90), not ordinal — encode as category, don't treat as numeric.

## Suggested feature set (for the next phase)
Predictors: `CSA_practices` (after crosswalk), `Crop_group`, `crop_type`, `Indicator`,
`Rainfall`, `Altitude_r`, `slope`, `temp_mean_annual`, `precip_seasonality`, `lgp_days`,
`soil_clay`, `soil_ph`, `soil_soc`, `land_cover`.
Target: `log_response_ratio`. Group key for CV: `Study_No_`. Keep `source` for analysis.
