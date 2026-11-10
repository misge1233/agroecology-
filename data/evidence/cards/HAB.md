# Data card: HAB (Habtamu Sewnet extraction database)

**Input**: `data/raw/grist_habtamu/@HabtamuSewnet-MasterData.csv`

**Rows read** 1,617 · **rows kept in the store** 1,617 · **rows dropped** 0

## Rows dropped, per rule

| Rule | Rows |
|---|---:|
| rows_dropped_by_loader | 0 |

## Parsing and mapping rules (rows affected)

| Rule | Rows |
|---|---:|
| study_id_blank_slugged_unknown | 0 |
| doi_normalised | 1,492 |
| doi_non_doi_identifier_to_extra | 40 |
| loc_site_named_no_coordinates | 758 |
| loc_country_only | 859 |
| n_with_not_integer_set_null | 3 |
| n_without_not_integer_set_null | 0 |
| quality_high | 1,095 |
| quality_medium_from_medium_moderate_or_medium_high | 90 |
| quality_nr_reported | 391 |
| quality_unparsed_value_set_nr (shifted cells such as years or scales; raw kept in extra) | 41 |
| slope_percent_parsed | 256 |
| exact_duplicate_of_earlier_row_flagged_in_extra | 7 |
| lrr_computable_both_means_positive | 1,312 |
| lrr_null_mean_missing_or_not_positive | 305 |
| var_lrr_delta_method_sd_and_n | 643 |
| var_lrr_null_sd_zero | 3 |
| Altitude:approx | 26 |
| Altitude:missing | 843 |
| Altitude:number | 28 |
| Altitude:number_with_unit | 386 |
| Altitude:range_midpoint | 307 |
| Altitude:unparsed | 27 |
| Mean_with:missing | 213 |
| Mean_with:number | 1,404 |
| Mean_without:missing | 231 |
| Mean_without:number | 1,386 |
| N_with:missing | 121 |
| N_with:number | 1,496 |
| N_without:missing | 139 |
| N_without:number | 1,478 |
| Precipitation:approx | 28 |
| Precipitation:missing | 384 |
| Precipitation:number | 32 |
| Precipitation:number_with_unit | 723 |
| Precipitation:plus_minus_first | 38 |
| Precipitation:range_midpoint | 270 |
| Precipitation:unparsed | 142 |
| SD_with:missing | 864 |
| SD_with:number | 753 |
| SD_without:missing | 927 |
| SD_without:number | 690 |
| SE_with:missing | 1,035 |
| SE_with:number | 582 |
| SE_without:missing | 1,117 |
| SE_without:number | 500 |
| country_missing | 1 |
| country_unmapped | 8 |
| crop_missing | 7 |
| crop_multiple_named | 380 |
| crop_not_named | 480 |
| crop_single_named | 750 |
| duration_bound_set_null | 77 |
| duration_missing | 5 |
| duration_parsed | 1,214 |
| duration_range_midpoint | 44 |
| duration_unparsed_set_null | 277 |
| multi_country_first_kept | 29 |
| year_from_study_id_suffix | 1,185 |
| year_from_study_period_last_year | 412 |
| year_missing | 20 |
| geocoding_applied_geocoded_llm_unchecked | 381 |
| geocoding_applied_geocoded_llm_checked | 84 |

## Coverage of key fields (share non-null)

| Field | Share |
|---|---:|
| `doi` | 92.3% |
| `year` | 98.8% |
| `country` | 99.4% |
| `lat` | 28.8% |
| `site_name` | 95.9% |
| `practice_id` | 93.6% |
| `outcome_id` | 95.9% |
| `direction` | 86.6% |
| `crop` | 69.9% |
| `crop_group` | 69.9% |
| `unit` | 99.9% |
| `mean_with` | 86.8% |
| `mean_without` | 85.7% |
| `sd_with` | 46.6% |
| `n_with` | 92.3% |
| `lrr` | 81.1% |
| `var_lrr` | 39.8% |
| `duration_years` | 77.8% |
| `ctx_reported_rain_mm` | 67.5% |
| `ctx_reported_altitude_m` | 46.2% |
| `ctx_reported_soil` | 86.6% |
| `ctx_reported_aez` | 95.9% |
| `evidence_text` | 52.4% |

## Licence and provenance

- Licence tag in the store: `partner-unpublished-no-redistribution`
- Habtamu Sewnet's extraction database (Grist), shared for this project only: unpublished partner data, git-ignored, never redistributed (`evidence_rows.*` are git-ignored).
- Archival `.grist` cross-check (sqlite, read-only): MasterData has 1617 rows; CSV has 1617 rows.

## Notes

- Unmapped country values (row counts): 7 European countries (8), (blank) (1)
- Multi-country values, first kept: Sweden, Estonia, Netherlands, Germany (6), Austria, France, Spain, Romania (6), Ethiopia, Kenya, Uganda (6), France, Germany, Switzerland (6), France; United Kingdom; Germany; Spain; Canada (4), Switzerland, Denmark, Germany, Belgium, Italy, Poland, Sweden (1)
- No coordinates in the source: `lat`/`lon` are null, `loc_method = none`. `loc_precision = site` when `Agroecological_Zone` contains a capitalised word that is not a generic climate term (the zone names a place); otherwise `country`. Geocoding is phase E2 (roadmap 5.5).
- `var_lrr` uses the SDs as given; SEs are not converted to SDs for this source (brief B3: 'sd_*, se_*, n_* as given'), so rows with SE and N but no SD have no variance yet.
- `evidence_text` = `Supporting Evidence` and `extraction_locator` = `Extraction Source (Location in PDF)` as the brief specifies. In the sheet these two columns are partly inverted: the locator column often holds a topic label ('Organic amendment') and the evidence column a table reference or a p-value. Kept as given; flagged for Habtamu.

## Taxonomy mapping (rules, not yet human-accepted)

| Field | Rows mapped | Share |
|---|---:|---:|
| `practice_id` | 1,513 | 93.6% |
| `outcome_id` | 1,551 | 95.9% |
| `direction` (reviewed) | 1,400 | 86.6% |

## Counts against the 10 Nov profile

| Count | Expected (profile) | Actual |
|---|---:|---:|
| rows | 1,617 | 1,617 |
| rows with a computable `lrr` | 1,312 | 1,312 |
| rows with `var_lrr` | 646 | 643 |
| Ethiopian rows | 158 | 158 |
| Ethiopian rows with `lrr` | 129 | 129 |
| `.grist` MasterData rows | 1,617 | 1617 |

`var_lrr` is 3 below the profile because 3 rows report SD = 0 for both arms (a zero variance is not usable as an inverse-variance weight; counted as `var_lrr_null_sd_zero`).

## Geocoding (E2, roadmap 5.5)

Review sheet `data/evidence/review/geocoding_review.csv`: 605 studies, every row with a quote (605), quote found verbatim in the source text for 233. Accepted by a reviewer: 58.

| Scope | Studies | Site | District | Country | Site or district |
|---|---:|---:|---:|---:|---:|
| All studies | 605 | 134 | 88 | 383 | 222 (37%) |
| Ethiopian studies | 100 | 22 | 36 | 42 | 58 (58%) |
| Ethiopian DOIs | 14 | 3 | 5 | 6 | 8 (57%) |

Store rows by `loc_method`: none 1,152, geocoded_llm_unchecked 381, geocoded_llm_checked 84. Rows with `geocoded_llm_unchecked` stay out of training (E3/E5 filter) until a reviewer accepts them.

## Countries (top 15)

| country | Rows |
|---|---:|
| ET | 158 |
| CN | 143 |
| IT | 142 |
| ES | 140 |
| US | 100 |
| IN | 86 |
| FR | 63 |
| KE | 60 |
| BR | 46 |
| BE | 42 |
| JP | 39 |
| DE | 38 |
| ZM | 32 |
| ZA | 30 |
| SE | 27 |

## Outcomes mapped (top 15)

| outcome_id | Rows |
|---|---:|
| YIELD | 327 |
| BIODIVERSITY | 179 |
| BIOMASS_YIELD | 81 |
| SOIL_ORGANIC_CARBON | 76 |
| (null) | 66 |
| SOIL_CARBON_STOCKS | 61 |
| SOIL_MOISTURE | 42 |
| PEST_DAMAGE | 34 |
| SOIL_LOSS | 34 |
| SOM_CONTENT | 34 |
| LAND_EQUIVALENT_RATIO | 32 |
| SOIL_TOTAL_NITROGEN | 31 |
| SOIL_FAUNA | 29 |
| SOIL_ORGANIC_CARBON_CHANGE | 28 |
| BULK_DENSITY | 27 |
