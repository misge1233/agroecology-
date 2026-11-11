# Context from geodata release ET/2026.1

Written by `pipelines/evidence/add_context.py` (brief E3 C3). Rows with `loc_precision` site or district and `loc_method` other than `geocoded_llm_unchecked` get every `ctx_<layer>` of the release (nearest valid cell within 120 cells, the rule of `recommend.py`).

- rows in the store: 19,753
- eligible: 18,146; written: 18,096; outside the country mask (kept null): 50
- not eligible: country/none precision 742, unchecked LLM geocode 381, no coordinates 484
- written by source: CSA 3,220, ERA 14,792, HAB 84

## Reconciliation with the frozen dataset (7,250 legacy ERA rows)

7,250 rows at 239 coordinates; tolerance 0.001. Result: **DIFFERENCES (listed below)**.

| Feature | Layer | Max abs diff | Rows over tolerance | Rows null |
|---|---|---|---|---|
| `Rainfall` | `precip_annual` | 6.05e-05 | 0 | 0 |
| `Altitude_r` | `elevation` | 3.93e+00 | 6240 | 0 |
| `temp_mean_annual` | `temp_mean_annual` | 9.35e-07 | 0 | 0 |
| `precip_seasonality` | `precip_seasonality` | 6.84e-06 | 0 | 0 |
| `slope` | `slope` | 2.23e+00 | 5670 | 0 |
| `soil_clay` | `soil_clay` | 7.11e-15 | 0 | 0 |

## Written values (rows with context)

| Column | n | min | median | max |
|---|---|---|---|---|
| `ctx_aez_belt` | 18,096 | 2 | 7 | 15 |
| `ctx_precip_annual` | 18,096 | 413.2 | 1005 | 1932 |
| `ctx_temp_mean_annual` | 18,096 | 7.261 | 18.66 | 28.7 |
| `ctx_precip_seasonality` | 18,096 | 35.72 | 87.68 | 132.5 |
| `ctx_lgp_days` | 18,096 | 31 | 245 | 365 |
| `ctx_elevation` | 18,096 | 437.2 | 1934 | 4038 |
| `ctx_slope` | 18,096 | 0 | 3.716 | 59.66 |
| `ctx_soil_clay` | 18,096 | 20.6 | 37.7 | 58.5 |
| `ctx_soil_ph` | 18,096 | 4.9 | 6.6 | 8.5 |
| `ctx_soil_soc` | 18,096 | 10.7 | 33.1 | 80.5 |
| `ctx_land_cover` | 18,096 | 10 | 40 | 90 |
| `ctx_slope_length_factor` | 18,096 | 0 | 1.379 | 30.44 |
| `ctx_tpi` | 18,096 | -142.8 | 0.3649 | 77.01 |
| `ctx_twi` | 18,096 | 5.237 | 8.288 | 15 |
| `ctx_flow_accumulation` | 18,096 | 0.01677 | 0.1535 | 5013 |
| `ctx_dist_to_stream_m` | 18,096 | 0 | 260.7 | 1374 |
| `ctx_soil_sand` | 18,096 | 10.47 | 25.9 | 55.37 |
| `ctx_soil_bulk_density` | 18,096 | 0.9833 | 1.257 | 1.632 |
| `ctx_soil_cec` | 18,096 | 18.15 | 37.05 | 71.38 |
| `ctx_soil_nitrogen` | 18,096 | 0.85 | 1.877 | 4.533 |
| `ctx_soil_awc` | 18,096 | 92.94 | 138.3 | 171.2 |
| `ctx_soil_depth_bedrock` | 18,096 | 129 | 200 | 200 |
| `ctx_rain_mean_1991_2020` | 18,096 | 372.3 | 1047 | 1918 |
| `ctx_rain_cv_interannual` | 18,096 | 6.6 | 12.21 | 24.58 |
| `ctx_dry_season_length_months` | 18,096 | 1 | 5 | 10 |
| `ctx_pet_hargreaves_annual` | 18,096 | 1094 | 1715 | 2186 |
| `ctx_aridity_index` | 18,096 | 0.2078 | 0.6352 | 1.247 |
| `ctx_cropland_fraction_1km` | 18,096 | 0 | 0.5896 | 1 |
| `ctx_travel_time_to_city_min` | 18,096 | 0 | 11.7 | 689.2 |
| `ctx_koppen_class` | 18,096 | 2 | 9 | 29 |
