# Data card: CSA (Adimassu et al. CSA compilation)

**Input**: `data/raw/CSA_practices_by_Agroecology.xlsx`, `data/processed/csa_study_references.json`

**Rows read** 3,344 · **rows kept in the store** 3,344 · **rows dropped** 0

## Rows dropped, per rule

| Rule | Rows |
|---|---:|
| rows_dropped_by_loader | 0 |

## Parsing and mapping rules (rows affected)

| Rule | Rows |
|---|---:|
| citation_from_csa_study_references | 3,344 |
| citation_fallback_compilation | 0 |
| loc_site_reported_coordinates | 3,270 |
| loc_zero_or_missing_coordinates_set_null | 74 |
| outcome_raw_blank_indicator | 2 |
| crop_harmonised_by_lookup | 2,471 |
| crop_not_in_lookup_kept_raw_group_null | 509 |
| crop_blank | 364 |
| ctx_rain_or_altitude_zero_set_null | 343 |
| exact_duplicate_of_earlier_row_flagged_in_extra | 178 |
| lrr_computable_both_means_positive | 3,033 |
| lrr_null_mean_missing_or_not_positive | 311 |

## Coverage of key fields (share non-null)

| Field | Share |
|---|---:|
| `doi` | 30.3% |
| `year` | 93.5% |
| `country` | 100.0% |
| `lat` | 97.8% |
| `site_name` | 90.9% |
| `practice_id` | 100.0% |
| `outcome_id` | 100.0% |
| `direction` | 61.3% |
| `crop` | 89.1% |
| `crop_group` | 73.9% |
| `unit` | 99.5% |
| `mean_with` | 100.0% |
| `mean_without` | 100.0% |
| `sd_with` | 0.0% |
| `n_with` | 0.0% |
| `lrr` | 90.7% |
| `var_lrr` | 0.0% |
| `duration_years` | 100.0% |
| `ctx_reported_rain_mm` | 94.6% |
| `ctx_reported_altitude_m` | 90.8% |
| `ctx_reported_soil` | 55.2% |
| `ctx_reported_aez` | 100.0% |
| `evidence_text` | 0.0% |

## Licence and provenance

- Licence tag in the store: `Adimassu-compilation-internal`
- Adimassu et al. compilation workbook (Ethiopian with/without studies), internal to the project.
- Citations from `data/processed/csa_study_references.json` (`build_csa_references.py`).
- No dispersion or sample size in the source.

## Notes

- The workbook reports no dispersion or sample sizes: `sd_*`, `se_*`, `n_*`, `var_lrr` are null and `weight` is the quality-based default.
- `practice_raw` is `CSA_catago` (the frozen `CSA_practices` label of the CSA rows); `CSA_practi` is in `extra`.

## Taxonomy mapping (rules, not yet human-accepted)

| Field | Rows mapped | Share |
|---|---:|---:|
| `practice_id` | 3,344 | 100.0% |
| `outcome_id` | 3,344 | 100.0% |
| `direction` (reviewed) | 2,051 | 61.3% |

## Reconciliation with the frozen dataset (brief B2)

Legacy rules applied to the store's CSA rows, in order:

| Step | Rows removed |
|---|---:|
| out_of_7_indicator_scope | 1,501 |
| exact_duplicate_workbook_row | 67 |
| zero_or_missing_coordinates | 28 |
| outside_stack_extent | 3 |
| mean_not_positive | 110 |
| response_ratio_gt_20 | 7 |
| blank_crop_type (undocumented rule, see module docstring) | 110 |
| merge_duplicates_ignoring_study_id | 104 |

- Frozen dataset (data/processed/CSA_ERA_final_model_ready.csv): **1,414** CSA rows; reproduced: **1,414**.
- Multiset `(study_id, practice_raw, Indicator, crop)` with `lrr` rounded to 1e-9: 0 rows only in the store, 0 only in the frozen file.
- Max |lrr difference| over matched rows: 6.66e-16.
- **Result: EXACT MATCH**

Rows collapsed by the merge-time duplicate rule across *different* studies (the frozen file kept the first study in file order):

| Kept | Dropped | Practice | Crop | Indicator | lrr |
|---|---|---|---|---|---:|
| CSA:CSA_153:2 | CSA:CSA_166:2 | ISFM | Common bean | income | 0.000000 |
| CSA:CSA_153:2 | CSA:CSA_166:3 | ISFM | Common bean | income | 0.000000 |
| CSA:CSA_153:2 | CSA:CSA_166:6 | ISFM | Common bean | income | 0.000000 |
| CSA:CSA_153:2 | CSA:CSA_166:7 | ISFM | Common bean | income | 0.000000 |
| CSA:CSA_60:52 | CSA:CSA_158:56 | Intercropping | Maize | yield | 0.000000 |
| CSA:CSA_60:52 | CSA:CSA_158:59 | Intercropping | Maize | yield | 0.000000 |
| CSA:CSA_60:52 | CSA:CSA_158:62 | Intercropping | Maize | yield | 0.000000 |
| CSA:CSA_60:52 | CSA:CSA_158:63 | Intercropping | Maize | yield | 0.000000 |
| CSA:CSA_60:52 | CSA:CSA_158:66 | Intercropping | Maize | yield | 0.000000 |
| CSA:CSA_60:52 | CSA:CSA_158:69 | Intercropping | Maize | yield | 0.000000 |
| CSA:CSA_60:52 | CSA:CSA_158:72 | Intercropping | Maize | yield | 0.000000 |
| CSA:CSA_18:29 | CSA:CSA_91:12 | Physical SWC measures | Barley | soil loss | -1.029619 |
| CSA:CSA_18:34 | CSA:CSA_91:14 | Physical SWC measures | Barley | yield | -0.693147 |
| CSA:CSA_18:40 | CSA:CSA_31:8 | Physical SWC measures | Field pea | yield | -0.559616 |
| CSA:CSA_18:49 | CSA:CSA_31:4 | Physical SWC measures | Barley | yield | 0.000000 |
| CSA:CSA_18:52 | CSA:CSA_31:5 | Physical SWC measures | Field pea | yield | -0.223144 |
| CSA:CSA_18:61 | CSA:CSA_31:1 | Physical SWC measures | Barley | yield | 0.287682 |
| CSA:CSA_18:68 | CSA:CSA_31:6 | Physical SWC measures | Field pea | soil loss | -1.098612 |
| CSA:CSA_21:17 | CSA:CSA_91:18 | Physical SWC measures | Maize | runoff | -0.241162 |
| CSA:CSA_21:25 | CSA:CSA_31:10 | Physical SWC measures | Maize | yield | -0.980829 |
| CSA:CSA_21:28 | CSA:CSA_31:12 | Physical SWC measures | Maize | yield | -0.693147 |
| CSA:CSA_21:29 | CSA:CSA_91:16 | Physical SWC measures | Maize | runoff | -0.117783 |
| CSA:CSA_23:28 | CSA:CSA_91:21 | Physical SWC measures | Barley | yield | 0.182322 |
| CSA:CSA_23:32 | CSA:CSA_91:24 | Physical SWC measures | Sorghum | soil loss | -1.791759 |
| CSA:CSA_23:34 | CSA:CSA_31:16 | Physical SWC measures | Barley | yield | 0.000000 |
| CSA:CSA_23:40 | CSA:CSA_31:20 | Physical SWC measures | Barley | yield | -0.182322 |
| CSA:CSA_23:46 | CSA:CSA_91:23 | Physical SWC measures | Sorghum | yield | -0.133531 |
| CSA:CSA_23:50 | CSA:CSA_91:26 | Physical SWC measures | Barley | soil loss | -2.302585 |
| CSA:CSA_26:34 | CSA:CSA_91:32 | Physical SWC measures | Sorghum | yield | 0.693147 |
| CSA:CSA_21:61 | CSA:CSA_31:23 | Physical SWC measures | Teff | yield | 0.000000 |
| CSA:CSA_42:3 | CSA:CSA_165:1 | Physical SWC measures | Barley | yield | -0.202941 |

## Outcomes (top 15 by rows)

| outcome_id | Rows |
|---|---:|
| YIELD | 1,041 |
| SOIL_LOSS | 292 |
| RUNOFF | 279 |
| BIOMASS_YIELD | 171 |
| IRRIGATION_AMOUNT | 141 |
| WATER_USE_EFFICIENCY | 124 |
| FEED_DIGESTIBILITY | 102 |
| SOM_CONTENT | 101 |
| SOIL_TOTAL_NITROGEN | 94 |
| AVAILABLE_PHOSPHORUS | 77 |
| WEIGHT_GAIN | 65 |
| SOIL_PH | 54 |
| BULK_DENSITY | 52 |
| GHG_EMISSIONS | 48 |
| INCOME | 43 |
