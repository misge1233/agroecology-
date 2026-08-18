# Merged Modeling Dataset — Data Dictionary

**File:** `feature_stack/dataset/CSA_ERA_merged_model_ready.csv` — **8,664 rows × 22 columns, 0 missing.**
**Objective:** one pooled regression model `f(practice, context, indicator) → log response ratio`,
used to rank CSA practices per agro-ecological context (the recommender).

## Column roles

| Column | Role | Type | Description / notes |
|---|---|---|---|
| `source` | metadata | categorical | Data origin: CSA (1,414) or ERA (7,250). Keep for diagnostics/stratification; **not a predictor**. |
| `Study_No_` | **group key** | id (string) | Source-prefixed study id. **Use for GroupKFold**, not as a feature. |
| `latitude` | metadata | float | Not a feature — location is already encoded via the stack variables. |
| `longitude` | metadata | float | As above. |
| `CSA_practices` | **feature (candidate / recommendation output)** | categorical | The specific practice being scored. This is what the recommender ranks and returns. High/mixed cardinality (~100 across sources) — encode with target/frequency encoding inside CV folds. |
| `practice_family` | **feature + user scope filter** | categorical (5) | Paper's expert categories (full names): Crop production and management; Livestock production and management; Integrated soil fertility management; Erosion control and water management; Agro-forestry and forest management. The user selects one to scope the request; also a coarse practice signal that helps generalise over rare specific practices. |
| `Crop_group` | **feature** | categorical | Agronomic group (Cereal, Pulse, Vegetable, Root & tuber, …). |
| `crop_type` | feature (optional) | categorical | Specific crop (~90 incl. intercrops). High cardinality — encode carefully or fold rare→`Crop_group`. |
| `Rainfall` | **feature** | float (mm/yr) | Annual precipitation from stack (WorldClim). |
| `Altitude_r` | **feature** | float (m) | Elevation from stack (Copernicus DEM). |
| `slope` | **feature** | float (%) | Slope from stack (DEM-derived). |
| `temp_mean_annual` | **feature** | float (°C) | Mean annual temperature (WorldClim). |
| `precip_seasonality` | **feature** | float (CV %) | Rainfall seasonality (WorldClim BIO15). |
| `lgp_days` | **feature** | float (days) | Length of growing period (water-balance derived). |
| `soil_clay` | **feature** | float (%) | Topsoil clay (SoilGrids). |
| `soil_ph` | **feature** | float (pH) | Topsoil pH (SoilGrids). |
| `soil_soc` | **feature** | float (g/kg) | Topsoil organic carbon (SoilGrids). |
| `land_cover` | **feature** | categorical (code) | ESA WorldCover class code (10/20/…/90) — treat as category, **not numeric**. |
| `aez_belt` | **feature** | categorical (12 present) | 15-zone agro-ecological belt name (context anchor). |
| `Indicator` | **feature** | categorical (7) | Outcome being predicted: yield, biomass yield, income, water use efficiency, SOM content, soil loss, runoff. Pools all outcomes into one model. |
| `response_ratio` | target (raw) | float | `MeanT/MeanC` (treatment ÷ control). Kept for interpretability. |
| `log_response_ratio` | **TARGET** | float | `ln(response_ratio)` — recommended modelling target (symmetric, variance-stabilised). |

## Final model feature set (13, after feature selection)
`CSA_practices`, `practice_family`, `Crop_group`, `crop_type`, `aez_belt`, `Indicator`, `Rainfall`,
`Altitude_r`, `temp_mean_annual`, `precip_seasonality`, `slope`, `soil_clay`, `land_cover`.

**Dropped from model inputs** (kept for the explanation layer): `lgp_days`, `soil_ph`, `soil_soc`.
**Never inputs (metadata/group):** `source`, `Study_No_`, `latitude`, `longitude`, `response_ratio`.
See `feature_selection_report.md` for the rationale.

## Recommender inference flow
1. User enters a location (→ stack features + `aez_belt`) and a goal (`Indicator`), and selects a
   `practice_family` to scope the request.
2. The system enumerates every `CSA_practices` observed within that `practice_family`, builds one
   feature row per candidate (candidate practice + fixed context + indicator), and predicts
   `log_response_ratio` for each.
3. Candidates are ranked by the predicted ratio in the indicator's "better" direction (higher for
   yield/income/…, lower for soil loss/runoff) and the top practice(s) are returned.
So `CSA_practices` is both a model **input** (the candidate scored) and the **recommendation output**;
`practice_family` scopes the candidate list.

## Encoding & scaling guidance
- Low-cardinality categoricals (`practice_family`, `Crop_group`, `aez_belt`, `Indicator`,
  `land_cover`) → one-hot (or native categorical for gradient-boosted trees).
- High-cardinality (`crop_type`, optional `CSA_practices`) → target/frequency encoding **inside CV
  folds** to avoid leakage, or collapse rare levels into `Crop_group`.
- Numerics → standardise only for distance/linear/NN models; not needed for tree ensembles.
- Do target encoding and scaling **within the pipeline**, fit on train folds only.

## Validation
- **GroupKFold (or GroupShuffleSplit) grouped by `Study_No_`** — a study contributes up to 548 rows;
  random splits would leak site information and inflate scores.
- Report metrics **per `Indicator`** (yield is 68% of rows; income/SOM are thin), and check
  performance **by `source`** (ERA skews positive, CSA centres near 0).

## Key modelling notes
1. `practice_family` (5 classes) is the cross-source practice feature that makes the recommender
   able to compare practices from both corpora on equal footing.
2. Source imbalance (ERA 84%) + effect-size shift by source — keep `source` for diagnostics.
3. Target-class imbalance across indicators — weight or evaluate per indicator.
4. Coordinates and IDs are metadata, not features.
