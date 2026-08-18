# ERA Ethiopia Dataset — Preprocessing Report

**Use case:** same CSA response-ratio model. This prepares the ERA (Evidence for Resilient
Agriculture) database into the **identical 19-column schema** as `CSA_practices_model_ready.csv`,
ready to merge.
**Input:** `dataset/ERA_Ethiopia_dataset.csv` (14,792 rows × 137 cols)
**Output:** `dataset/ERA_Ethiopia_model_ready.csv` (**7,827 rows × 19 cols, 0 missing**)

## Column mapping (ERA → target schema)

| Target | ERA source | Note |
|---|---|---|
| Study_No_ | `Code` | study code (string, e.g. NJ0128) |
| latitude / longitude | `Latitude` / `Longitude` | |
| CSA_practi | `PrName` | ERA practice taxonomy |
| crop_type / Crop_group | `Product.Simple` | harmonised + grouped |
| Indicator | `Out.SubInd` | mapped to our 10-indicator scope |
| response_ratio | `MeanT / MeanC` | treatment / control means |
| log_response_ratio | `ln(MeanT/MeanC)` | equals ERA's `yi` (verified identical, no sign flip) |
| Rainfall, Altitude_r, slope, temp_mean_annual, precip_seasonality, lgp_days, soil_clay, soil_ph, soil_soc, land_cover | **feature stack** | retrieved from lat/long (not ERA's own MAP/MAT/SOC/pH columns) |

**Verification:** `yi` was confirmed to equal raw `ln(MeanT/MeanC)` for yield, soil loss and
runoff (difference = 0.0000), so ERA's effect size uses the same direction convention as ours;
we compute the ratio directly from `MeanT/MeanC` for exact consistency with the CSA dataset.

## Indicator scoping (Out.SubInd → canonical)

Mapped 7 of the 10 core indicators:
Crop Yield→**yield**, Biomass Yield→**biomass yield**, Net Return→**net income**,
Water Use Efficiency→**water use efficiency**, Soil Organic Matter→**SOM content**,
Erosion→**soil loss**, Runoff→**runoff**.

**No clean ERA equivalent** for **available P** (ERA has only phosphorus *use-efficiencies*,
not soil available P), **bulk density**, or **irrigation amount** (ERA "Water Use" is
ambiguous). These were deliberately NOT forced — those three indicators come only from the
CSA dataset. All other ERA outcomes (Income/Gross margin, Meat/Milk yield, N-efficiencies,
Soil Moisture, CEC, Costs, etc.) are out of scope and dropped.

## Preprocessing steps

1. **Scope filter** → 7 mappable indicators (14,792 → 7,854).
2. **Exact duplicates**: none found (0 removed).
3. **Coordinates**: coerced numeric; none zero/missing; all within the stack extent
   (ERA lat 4.9–14.4, lon 34.6–43.5) → 7,854 kept.
4. **Positive means**: dropped 10 rows with `MeanC ≤ 0` or `MeanT ≤ 0` → 7,844.
5. **Target**: `response_ratio = MeanT/MeanC`, `log_response_ratio = ln(ratio)`.
6. **Outliers**: dropped 17 rows with `response_ratio > 20` (implausible increases from
   near-zero controls); kept genuine large reductions (soil loss/runoff) → 7,827.
7. **crop_type**: harmonised to CSA spellings where overlapping (Fava Bean→Faba bean,
   Common Bean→Common bean, Mung Bean→Mungbean, Peas→Field pea, Indian Pea→Grass pea,
   Durum Wheat→Wheat, Arabica→Coffee, etc.); intercrop/rotation labels kept as-is.
8. **Crop_group**: same grouping scheme as the CSA dataset, with a component-aware classifier
   for intercrops (cereal+legume → Cereal-Legume; multi-crop → Mixed cropping) and added
   groups present only in ERA (Perennial-Cash for coffee, Fruit for banana, Livestock).
9. **Stack features** retrieved by lat/long with nearest-valid-cell fallback; `land_cover`
   as class code. Original ERA climate/soil columns discarded in favour of the consistent stack.
10. **Leakage/unused** ERA columns (MeanC, MeanT, yi, and ~120 others) dropped.
11. **Integrity**: 0 missing values across 7,827 × 19.

## Final dataset

- **Dimensions:** 7,827 × 19; 0 missing. Same columns/order/dtypes as CSA (except `Study_No_`
  is a **string** code here vs integer in CSA).
- **Indicators:** yield 5,583; biomass yield 1,491; net income 183; water use efficiency 177;
  runoff 151; soil loss 146; SOM content 96.
- **Crop_group:** Cereal 4,767; Pulse 953; Root & tuber 649; Vegetable 546; Oilseed 435;
  Forage 231; Cereal-Legume 169; Perennial-Cash 47; Fruit 12; Mixed cropping 11; Livestock 7.

## Assumptions / notes for the merge

1. **Practice vocabularies differ**: ERA `PrName` (Inorganic Fertilizer, Water Harvesting, …)
   is a different taxonomy from the CSA workbook's `CSA_practi` (Graded Fanya Juu, Tied-ridge, …).
   The merged `CSA_practi` will contain both vocabularies — a harmonisation/crosswalk may be
   worthwhile before modelling.
2. **Study_No_ type**: ERA is a string code, CSA is integer. At merge, cast both to string and
   consider a `source` column (ERA / CSA) plus a source-prefixed ID to avoid collisions.
3. Only 7 of 10 indicators are shared; available P, bulk density, irrigation amount are
   CSA-only in the combined data.
4. Geospatial features are consistent across both datasets (same stack), which is the main
   benefit of re-deriving them here rather than using each source's native columns.
