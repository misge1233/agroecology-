# Harness queries (E4 Part 1)

Built from the evidence store (19,753 rows, 17,326 eligible; release `ET/2026.1` context) and the frozen dataset (legacy cells). One query = one `(group, site, outcome_id, crop, comparator_class)` cell; ground truth = pooled oriented `lrr` per practice. Seed 0; query-key hash `17a46034aff7`.

| set | queries with >= 2 practices (pairwise) | >= 3 practices (list) | same, without the comparator key |
|---|---:|---:|---|
| ET | 375 | 185 | 360 / 184 |
| global | 39 | 8 | 46 / 8 |
| post_2024 | 5 | 0 | 5 / 0 |
| legacy_68 | 68 | 68 | n/a (dataset cells) |

## By objective group (ET, pairwise / list)

| objective group | >= 2 | >= 3 | without comparator key >= 2 / >= 3 |
|---|---:|---:|---|
| climate | 0 | 0 | 1 / 0 |
| economics | 71 | 51 | 68 / 47 |
| livestock | 34 | 1 | 30 / 8 |
| productivity | 188 | 109 | 173 / 102 |
| resilience_biodiversity | 3 | 0 | 3 / 0 |
| soil_health | 32 | 16 | 36 / 17 |
| water | 47 | 8 | 49 / 10 |

## Comparator classes (rows that form queries)

| comparator_class | queries |
|---|---:|
| other | 239 |
| no_practice | 105 |
| conventional_tillage | 53 |
| mineral_fertilizer_only | 10 |
| farmer_practice | 7 |

Rows without any comparator text are classed `other`; 39 of the 414 ET/global queries are built only from such rows (the other `other` queries have comparator text that no rule matched).

## Challenges (ET queries; a query counts in every challenge of its outcome)

| challenge | queries |
|---|---:|
| LOW_CROP_PRODUCTIVITY | 178 |
| SOIL_FERTILITY_DECLINE | 153 |
| MOISTURE_STRESS_DROUGHT | 138 |
| SOIL_ACIDITY | 122 |
| FEED_SHORTAGE | 80 |
| LOW_INCOME_MARKET_ACCESS | 50 |
| DEGRADED_HILLSIDES | 31 |
| SOIL_EROSION | 30 |
| GULLY_EROSION | 29 |
| WATERLOGGING_EXCESS_RUNOFF | 29 |
| WATER_SCARCITY_IRRIGATION | 16 |
| DEFORESTATION_FUELWOOD | 2 |
| PESTS_AND_DISEASES | 1 |

## Belt (ET queries, attribute only)

| belt | queries |
|---|---:|
| Moist Weyna Dega | 105 |
| Dry Weyna Dega | 83 |
| Wet Weyna Dega | 62 |
| Moist Dega | 42 |
| Dry Kolla | 28 |
| Wet Dega | 19 |
| Moist Kolla | 17 |
| Dry Dega | 14 |
| Moist High Dega | 2 |
| Wet Kolla | 2 |
| none | 1 |

## Sources, precision, context source

| sources | queries |
|---|---:|
| ERA | 331 |
| HAB | 44 |
| CSA | 39 |

| loc_precision | queries |
|---|---:|
| site | 398 |
| country | 16 |

| ctx_source | queries |
|---|---:|
| release | 374 |
| reported | 40 |

## Ground-truth pooling

| pooling | items |
|---|---:|
| weighted_mean | 902 |
| inverse_variance | 277 |

Items (query x practice): 1,465; practices per query: median 2, max 11; rows per query: median 8.

