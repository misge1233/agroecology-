# Data card: ERA (ERA Ethiopia)

**Input**: `data/raw/ERA_Ethiopia_dataset.csv`

**Rows read** 14,792 · **rows kept in the store** 14,792 · **rows dropped** 0

## Rows dropped, per rule

| Rule | Rows |
|---|---:|
| rows_dropped_by_loader | 0 |

## Parsing and mapping rules (rows affected)

| Rule | Rows |
|---|---:|
| doi_normalised | 14,424 |
| doi_non_doi_identifier_to_extra | 273 |
| country_from_iso3 | 14,792 |
| loc_site_reported_coordinates | 14,792 |
| loc_country_no_coordinates | 0 |
| outcome_raw_from_partial_outcome_name | 45 |
| outcome_raw_from_era_outcome_name | 14,747 |
| error_type_sd | 887 |
| error_type_se_converted_to_sd_with_rep | 2,459 |
| error_type_cv_or_sed_kept_in_extra | 1,017 |
| crop_harmonised_by_lookup | 14,112 |
| crop_not_in_lookup_kept_raw_group_null | 680 |
| duration_gt_50_not_years_set_null | 917 |
| exact_duplicate_of_earlier_row_flagged_in_extra | 0 |
| lrr_computable_both_means_positive | 13,949 |
| lrr_null_mean_missing_or_not_positive | 843 |
| var_lrr_delta_method | 2,955 |
| meanflip_flag_kept_in_extra_not_applied | 1,635 |

## Coverage of key fields (share non-null)

| Field | Share |
|---|---:|
| `doi` | 97.5% |
| `year` | 100.0% |
| `country` | 100.0% |
| `lat` | 100.0% |
| `site_name` | 100.0% |
| `practice_id` | 100.0% |
| `outcome_id` | 100.0% |
| `direction` | 100.0% |
| `crop` | 100.0% |
| `crop_group` | 95.4% |
| `unit` | 98.4% |
| `mean_with` | 100.0% |
| `mean_without` | 96.4% |
| `sd_with` | 22.6% |
| `n_with` | 100.0% |
| `lrr` | 94.3% |
| `var_lrr` | 20.0% |
| `duration_years` | 91.8% |
| `ctx_reported_rain_mm` | 74.4% |
| `ctx_reported_altitude_m` | 85.4% |
| `ctx_reported_soil` | 58.4% |
| `ctx_reported_aez` | 96.5% |
| `evidence_text` | 0.0% |

## Licence and provenance

- Licence tag in the store: `ERA-Dataverse-terms`
- ERA (Evidence for Resilient Agriculture) Ethiopia extract, Harvard Dataverse; terms of the Dataverse record apply (licence tag to be confirmed by the owner).
- `study_id = ERA_<Code>` equals the frozen `Study_No_`; `extraction_locator` = ERA `DataLoc`.
- All 14,792 rows kept, including the 59 outcome codes outside the 7 model indicators.

## Notes

- ERA's own effect size `yi` is present on 14,084 rows; where both exist it equals ln(MeanT/MeanC) within 1e-6 on 13,949 of 13,949 rows (max |diff| 1.07e-08). The store uses ln(MeanT/MeanC).
- `MeanFlip = N` marks rows where ERA notes that lower values are better for the outcome. The store never flips a mean: `lrr` is always ln(mean_with/mean_without) and the outcome taxonomy carries the direction.

## Taxonomy mapping (rules, not yet human-accepted)

| Field | Rows mapped | Share |
|---|---:|---:|
| `practice_id` | 14,792 | 100.0% |
| `outcome_id` | 14,792 | 100.0% |
| `direction` (reviewed) | 14,792 | 100.0% |

## Reconciliation with the frozen dataset (brief B1)

Legacy rules applied to the store's ERA rows, in order:

| Step | Rows removed |
|---|---:|
| out_of_7_indicator_scope | 6,938 |
| mean_not_positive | 10 |
| response_ratio_gt_20 | 17 |
| merge_duplicates_ignoring_study_id | 577 |

- Frozen dataset (data/processed/CSA_ERA_final_model_ready.csv): **7,250** ERA rows; reproduced: **7,250**.
- Multiset `(study_id, practice_raw, Indicator, crop)` with `lrr` rounded to 1e-9: 0 rows only in the store, 0 only in the frozen file.
- Max |lrr difference| over matched rows: 8.88e-16.
- **Result: EXACT MATCH**

Rows collapsed by the merge-time duplicate rule across *different* studies (the frozen file kept the first study in file order):

| Kept | Dropped | Practice | Crop | Indicator | lrr |
|---|---|---|---|---|---:|
| ERA:ERA_NN0448:1 | ERA:ERA_NM0040:1 | Inorganic Fertilizer | Maize | yield | 0.057158 |
| ERA:ERA_NN0448:2 | ERA:ERA_NM0040:2 | Inorganic Fertilizer-Organic Fertilizer | Maize | yield | 0.057158 |
| ERA:ERA_NN0448:3 | ERA:ERA_NM0040:3 | Inorganic Fertilizer-Organic Fertilizer | Maize | yield | 0.201740 |
| ERA:ERA_NN0448:4 | ERA:ERA_NM0040:4 | Inorganic Fertilizer-Organic Fertilizer | Maize | yield | 0.172469 |
| ERA:ERA_NN0448:5 | ERA:ERA_NM0040:5 | Inorganic Fertilizer-Organic Fertilizer | Maize | yield | 0.068208 |
| ERA:ERA_NN0448:6 | ERA:ERA_NM0040:6 | Organic Fertilizer | Maize | yield | 0.111226 |
| ERA:ERA_NN0448:7 | ERA:ERA_NM0040:7 | Inorganic Fertilizer | Maize | yield | 0.013245 |
| ERA:ERA_NN0448:8 | ERA:ERA_NM0040:8 | Inorganic Fertilizer-Organic Fertilizer | Maize | yield | 0.076961 |
| ERA:ERA_NN0448:9 | ERA:ERA_NM0040:9 | Inorganic Fertilizer-Organic Fertilizer | Maize | yield | 0.204300 |
| ERA:ERA_NN0448:9 | ERA:ERA_NM0040:11 | Inorganic Fertilizer-Organic Fertilizer | Maize | yield | 0.204300 |
| ERA:ERA_NN0448:10 | ERA:ERA_NM0040:10 | Inorganic Fertilizer-Organic Fertilizer | Maize | yield | 0.136859 |
| ERA:ERA_NN0448:12 | ERA:ERA_NM0040:12 | Organic Fertilizer | Maize | yield | 0.013245 |
| ERA:ERA_NN0469:52 | ERA:ERA_NN0219:4 | Reduced Tillage | Maize | yield | -0.057708 |
| ERA:ERA_CJ0133:18 | ERA:ERA_CJ0148:116 | Inorganic Fertilizer | Potato | yield | 0.693147 |
| ERA:ERA_AN0078:4 | ERA:ERA_LM0305:4 | Water Harvesting | Fodder (Natural Vegetation) | soil loss | -0.864997 |

## Outcomes (top 15 by rows)

| outcome_id | Rows |
|---|---:|
| YIELD | 5,592 |
| BIOMASS_YIELD | 1,498 |
| SOIL_MOISTURE | 1,171 |
| GROSS_RETURN | 833 |
| VARIABLE_COST | 823 |
| GROSS_MARGIN | 710 |
| CROP_RESIDUE_YIELD | 567 |
| MEAT_YIELD | 412 |
| NITROGEN_AGRONOMIC_EFFICIENCY | 322 |
| WEIGHT_GAIN | 317 |
| SOIL_ORGANIC_CARBON | 287 |
| NITROGEN_USE_EFFICIENCY_ARE_PRODUCT | 264 |
| SOIL_TOTAL_NITROGEN | 220 |
| INCOME | 189 |
| WATER_USE_EFFICIENCY | 177 |
